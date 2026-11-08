import json
import os
import re
import sqlite3
import subprocess
import time
from collections.abc import AsyncIterator, Iterator
from contextlib import asynccontextmanager, closing
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import HTMLResponse, JSONResponse, StreamingResponse

BASE_URL = os.environ.get("OPENCODE_BASE_URL", "https://opencode.ai/inference/openai/v1")
API_KEY = os.environ.get("OPENCODE_API_KEY", "")
DEFAULT_MODEL = os.environ.get("DEFAULT_MODEL", "qwen3.8-flash")
MAX_STEPS = int(os.environ.get("MAX_STEPS", "6"))
HEADERS = {"Authorization": f"Bearer {API_KEY}"}

BASE_TOOLS = [
    {
        "type": "function",
        "function": {
            "name": "skill_learn",
            "description": "Learn a reusable skill. Give it a name, a short description, and a body. A full SKILL.md document with YAML front matter may be passed in the markdown field.",
            "parameters": {
                "type": "object",
                "properties": {
                    "name": {"type": "string", "description": "Skill name."},
                    "description": {"type": "string", "description": "One-line description."},
                    "content": {"type": "string", "description": "Full skill body in markdown."},
                    "markdown": {"type": "string", "description": "Optional full SKILL.md document with YAML front matter."},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "skill_list",
            "description": "List the name and description of every learned skill.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "skill_load",
            "description": "Load the full content of one learned skill by name.",
            "parameters": {
                "type": "object",
                "properties": {"name": {"type": "string", "description": "The skill name."}},
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "skill_forget",
            "description": "Delete a learned skill by name.",
            "parameters": {
                "type": "object",
                "properties": {"name": {"type": "string", "description": "The skill name."}},
                "required": ["name"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fact_set",
            "description": "Store a durable fact as a key/value pair. Facts are injected into every future request as policy.",
            "parameters": {
                "type": "object",
                "properties": {
                    "key": {"type": "string", "description": "Short fact key."},
                    "value": {"type": "string", "description": "The fact value."},
                },
                "required": ["key", "value"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fact_list",
            "description": "List all stored facts.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fact_get",
            "description": "Get one stored fact by key.",
            "parameters": {
                "type": "object",
                "properties": {"key": {"type": "string", "description": "The fact key."}},
                "required": ["key"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "fact_forget",
            "description": "Delete a stored fact by key.",
            "parameters": {
                "type": "object",
                "properties": {"key": {"type": "string", "description": "The fact key."}},
                "required": ["key"],
            },
        },
    },
]

POLICY = (
    "You have persistent skills and facts that survive across conversations. "
    "Learn a reusable skill with skill_learn when the user teaches a procedure. "
    "Call a skill by name to load its full content before you use it. "
    "Store durable facts with fact_set when the user shares identity or environment details. "
    "Facts are always present in this message as policy. "
    "Do not store transient details of the current request."
)


class Skills:
    def __init__(self, path: Path) -> None:
        self.path = path
        with closing(sqlite3.connect(path)) as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS skills ("
                "name TEXT PRIMARY KEY, description TEXT NOT NULL, "
                "content TEXT NOT NULL, created_at TEXT, updated_at TEXT)"
            )
            conn.commit()

    def _now(self) -> str:
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    def add(self, name: str, description: str, content: str) -> dict[str, Any]:
        now = self._now()
        with closing(sqlite3.connect(self.path)) as conn:
            conn.execute(
                "INSERT INTO skills(name, description, content, created_at, updated_at) "
                "VALUES (?, ?, ?, ?, ?) "
                "ON CONFLICT(name) DO UPDATE SET "
                "description=excluded.description, content=excluded.content, updated_at=excluded.updated_at",
                (name, description, content, now, now),
            )
            conn.commit()
        return {"name": name, "description": description}

    @staticmethod
    def parse_markdown(markdown: str) -> tuple[str | None, str | None, str]:
        text = markdown.strip()
        if not text.startswith("---"):
            return None, None, text
        parts = text.split("---", 2)
        if len(parts) < 3:
            return None, None, text
        name = None
        description = None
        for line in parts[1].splitlines():
            if ":" not in line:
                continue
            key, _, value = line.partition(":")
            key = key.strip().lower()
            value = value.strip().strip('"').strip("'")
            if key == "name":
                name = value
            elif key == "description":
                description = value
        return name, description, parts[2].strip()

    def get(self, name: str) -> dict[str, Any] | None:
        with closing(sqlite3.connect(self.path)) as conn:
            row = conn.execute(
                "SELECT name, description, content FROM skills WHERE name = ?", (name,)
            ).fetchone()
        if row is None:
            return None
        return {"name": row[0], "description": row[1], "content": row[2]}

    def list(self) -> list[dict[str, Any]]:
        with closing(sqlite3.connect(self.path)) as conn:
            rows = conn.execute("SELECT name, description FROM skills ORDER BY name").fetchall()
        return [{"name": row[0], "description": row[1]} for row in rows]

    def delete(self, name: str) -> bool:
        with closing(sqlite3.connect(self.path)) as conn:
            cursor = conn.execute("DELETE FROM skills WHERE name = ?", (name,))
            conn.commit()
            return cursor.rowcount > 0

    def execute(self, name: str, arguments: str | dict[str, Any]) -> str:
        try:
            args = json.loads(arguments) if isinstance(arguments, str) else arguments
        except json.JSONDecodeError as error:
            return json.dumps({"error": str(error)})
        if not isinstance(args, dict):
            return json.dumps({"error": "arguments must be a JSON object"})

        if name == "skill_learn":
            raw_name = str(args.get("name", "")).strip()
            raw_description = str(args.get("description", "")).strip()
            raw_content = str(args.get("content", "")).strip()
            raw_markdown = args.get("markdown")
            if isinstance(raw_markdown, str) and raw_markdown.strip():
                parsed_name, parsed_description, parsed_content = self.parse_markdown(raw_markdown)
                if parsed_name:
                    raw_name = parsed_name
                if parsed_description:
                    raw_description = parsed_description
                if parsed_content:
                    raw_content = parsed_content
            if not raw_name or not raw_description or not raw_content:
                return json.dumps({"error": "name, description, and content are required"})
            return json.dumps(self.add(raw_name, raw_description, raw_content))

        if name == "skill_list":
            return json.dumps({"skills": self.list()})

        if name == "skill_load":
            skill = self.get(str(args.get("name", "")).strip())
            if skill is None:
                return json.dumps({"error": "unknown skill"})
            return json.dumps(skill)

        if name == "skill_forget":
            return json.dumps({"deleted": self.delete(str(args.get("name", "")).strip())})

        skill = self.get(name)
        if skill is not None:
            return json.dumps({"skill": name, "content": skill["content"]})

        return json.dumps({"error": f"unknown tool: {name}"})


class Facts:
    def __init__(self, path: Path) -> None:
        self.path = path
        with closing(sqlite3.connect(path)) as conn:
            conn.execute(
                "CREATE TABLE IF NOT EXISTS facts ("
                "key TEXT PRIMARY KEY, value TEXT NOT NULL, updated_at TEXT)"
            )
            conn.commit()

    def _now(self) -> str:
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    def set(self, key: str, value: str) -> dict[str, Any]:
        now = self._now()
        with closing(sqlite3.connect(self.path)) as conn:
            conn.execute(
                "INSERT INTO facts(key, value, updated_at) VALUES (?, ?, ?) "
                "ON CONFLICT(key) DO UPDATE SET value=excluded.value, updated_at=excluded.updated_at",
                (key, value, now),
            )
            conn.commit()
        return {"key": key, "value": value}

    def get(self, key: str) -> dict[str, Any] | None:
        with closing(sqlite3.connect(self.path)) as conn:
            row = conn.execute("SELECT key, value FROM facts WHERE key = ?", (key,)).fetchone()
        if row is None:
            return None
        return {"key": row[0], "value": row[1]}

    def list(self) -> list[dict[str, Any]]:
        with closing(sqlite3.connect(self.path)) as conn:
            rows = conn.execute("SELECT key, value FROM facts ORDER BY key").fetchall()
        return [{"key": row[0], "value": row[1]} for row in rows]

    def delete(self, key: str) -> bool:
        with closing(sqlite3.connect(self.path)) as conn:
            cursor = conn.execute("DELETE FROM facts WHERE key = ?", (key,))
            conn.commit()
            return cursor.rowcount > 0

    def execute(self, name: str, arguments: str | dict[str, Any]) -> str:
        try:
            args = json.loads(arguments) if isinstance(arguments, str) else arguments
        except json.JSONDecodeError as error:
            return json.dumps({"error": str(error)})
        if not isinstance(args, dict):
            return json.dumps({"error": "arguments must be a JSON object"})

        if name == "fact_set":
            key = str(args.get("key", "")).strip()
            value = str(args.get("value", "")).strip()
            if not key or not value:
                return json.dumps({"error": "key and value are required"})
            return json.dumps(self.set(key, value))

        if name == "fact_list":
            return json.dumps({"facts": self.list()})

        if name == "fact_get":
            fact = self.get(str(args.get("key", "")).strip())
            if fact is None:
                return json.dumps({"error": "unknown fact"})
            return json.dumps(fact)

        if name == "fact_forget":
            return json.dumps({"deleted": self.delete(str(args.get("key", "")).strip())})

        return json.dumps({"error": f"unknown tool: {name}"})


DB_PATH = Path(os.environ.get("KNOWLEDGE_DB", "knowledge.db"))
SKILLS = Skills(DB_PATH)
FACTS = Facts(DB_PATH)

MCP_PROFILE = os.environ.get("MCP_PROFILE", "dev-tools")
MCP_TOOLS_CACHE: list[dict[str, Any]] | None = None
MCP_TOOLS_CACHE_TIME: float = 0.0
MCP_CACHE_TTL: float = 60.0


@asynccontextmanager
async def lifespan(application: FastAPI) -> AsyncIterator[None]:
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=180) as client:
        application.state.zen = client
        yield


app = FastAPI(title="Zen Skills Proxy", lifespan=lifespan)


def _mcp_gateway_args() -> list[str]:
    return ["--gateway-arg", "--profile", "--gateway-arg", MCP_PROFILE]


def discover_mcp_tools() -> list[dict[str, Any]]:
    global MCP_TOOLS_CACHE, MCP_TOOLS_CACHE_TIME
    try:
        result = subprocess.run(
            ["docker", "mcp", "tools", "ls", "--gateway-arg", "--profile", "--gateway-arg", MCP_PROFILE, "--format", "json"],
            capture_output=True, text=True, timeout=30,
        )
        if result.returncode == 0:
            MCP_TOOLS_CACHE = json.loads(result.stdout)
        else:
            MCP_TOOLS_CACHE = []
    except (subprocess.TimeoutExpired, json.JSONDecodeError, Exception):
        MCP_TOOLS_CACHE = []
    MCP_TOOLS_CACHE_TIME = time.time()
    return MCP_TOOLS_CACHE or []


def get_mcp_tools() -> list[dict[str, Any]]:
    global MCP_TOOLS_CACHE, MCP_TOOLS_CACHE_TIME
    now = time.time()
    if MCP_TOOLS_CACHE is None or (now - MCP_TOOLS_CACHE_TIME) > MCP_CACHE_TTL:
        discover_mcp_tools()
        MCP_TOOLS_CACHE_TIME = now
    return MCP_TOOLS_CACHE or []


def invalidate_mcp_tools() -> None:
    global MCP_TOOLS_CACHE, MCP_TOOLS_CACHE_TIME
    MCP_TOOLS_CACHE = None
    MCP_TOOLS_CACHE_TIME = 0.0


def execute_mcp_tool(name: str, arguments: str | dict[str, Any]) -> str:
    try:
        args = json.loads(arguments) if isinstance(arguments, str) else arguments
    except json.JSONDecodeError as error:
        return json.dumps({"error": str(error)})
    if not isinstance(args, dict):
        return json.dumps({"error": "arguments must be a JSON object"})
    cmd = ["docker", "mcp", "tools", "call", name]
    for key, value in args.items():
        if isinstance(value, (dict, list)):
            cmd.append(f"{key}={json.dumps(value)}")
        else:
            cmd.append(f"{key}={value}")
    cmd += _mcp_gateway_args()
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=120)
    except subprocess.TimeoutExpired:
        return json.dumps({"error": "mcp tool timed out"})
    output = (result.stdout or "").strip()
    if not output:
        output = (result.stderr or "").strip()
    if name.startswith("mcp-"):
        invalidate_mcp_tools()
    return json.dumps({"exit_code": result.returncode, "output": output})


def _execute_tool(name: str, arguments: str | dict[str, Any]) -> str:
    if name in {"skill_learn", "skill_list", "skill_load", "skill_forget"}:
        return SKILLS.execute(name, arguments)
    if name in {"fact_set", "fact_list", "fact_get", "fact_forget"}:
        return FACTS.execute(name, arguments)
    if SKILLS.get(name) is not None:
        return SKILLS.execute(name, arguments)
    mcp_names = {tool["name"] for tool in get_mcp_tools()}
    if name in mcp_names:
        return execute_mcp_tool(name, arguments)
    return json.dumps({"error": f"unknown tool: {name}"})


@app.post("/v1/chat/completions")
async def chat_completions(request: Request):
    if not API_KEY:
        return _error("OPENCODE_API_KEY is not set", 500)

    body = await request.json()
    stream = bool(body.pop("stream", False))
    body.pop("stream_options", None)
    incoming = body.pop("messages", [])
    if not isinstance(incoming, list) or not incoming:
        return _error("messages is required", 400)

    client_tools = body.pop("tools", None)
    taken = {tool["function"]["name"] for tool in client_tools or [] if "function" in tool}
    tools = [*(client_tools or []), *[tool for tool in BASE_TOOLS if tool["function"]["name"] not in taken]]
    skill_tools = []
    for skill in SKILLS.list():
        if skill["name"] in taken:
            continue
        skill_tools.append(
            {
                "type": "function",
                "function": {
                    "name": skill["name"],
                    "description": skill["description"],
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        )
    tools = [*tools, *skill_tools]
    mcp_tools = get_mcp_tools()
    mcp_defs = []
    for tool in mcp_tools:
        name = tool.get("name", "")
        if not name or name in taken:
            continue
        parameters = tool.get("inputSchema") or {"type": "object", "properties": {}}
        if not isinstance(parameters, dict) or parameters.get("type") != "object":
            parameters = {"type": "object", "properties": {}}
        mcp_defs.append(
            {
                "type": "function",
                "function": {
                    "name": name,
                    "description": tool.get("description", ""),
                    "parameters": parameters,
                },
            }
        )
    tools = [*tools, *mcp_defs]
    internal = (
        {tool["function"]["name"] for tool in BASE_TOOLS if tool["function"]["name"] not in taken}
        | {skill["name"] for skill in SKILLS.list() if skill["name"] not in taken}
        | {tool["name"] for tool in mcp_tools if tool["name"] not in taken}
    )

    body["model"] = body.get("model") or DEFAULT_MODEL
    if "tool_choice" not in body:
        body["tool_choice"] = "auto"
    messages = [system_message(), *incoming]

    for _ in range(MAX_STEPS):
        response = await request.app.state.zen.post(
            "/chat/completions",
            json={**body, "messages": messages, "tools": tools},
            headers=HEADERS,
        )
        if response.status_code != 200:
            return await _upstream_error(response, request.app.state.zen, body["model"])
        data = response.json()
        message = data["choices"][0]["message"]
        calls = message.get("tool_calls") or []
        if not calls or any(call["function"]["name"] not in internal for call in calls):
            break
        messages.append({"role": "assistant", "content": message.get("content"), "tool_calls": calls})
        for call in calls:
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call["id"],
                    "content": _execute_tool(call["function"]["name"], call["function"]["arguments"]),
                }
            )
    else:
        return _error("tool loop limit reached", 502)

    if not stream:
        return JSONResponse(data)
    return StreamingResponse(_stream(data), media_type="text/event-stream")


@app.get("/v1/models")
async def models(request: Request):
    if not API_KEY:
        return _error("OPENCODE_API_KEY is not set", 500)
    response = await request.app.state.zen.get("/models", headers=HEADERS)
    if response.status_code != 200:
        return await _upstream_error(response, request.app.state.zen)
    return JSONResponse(response.json())


@app.get("/", response_class=HTMLResponse)
async def ui():
    return HTMLResponse(UI_HTML)


@app.get("/health")
async def health():
    return {"ok": True, "default_model": DEFAULT_MODEL, "db": str(DB_PATH)}


@app.get("/skills")
async def list_skills():
    return {"skills": SKILLS.list()}


@app.get("/skills/{name}")
async def get_skill(name: str):
    skill = SKILLS.get(name)
    if skill is None:
        return _error(f"unknown skill: {name}", 404)
    return skill


@app.get("/facts")
async def list_facts():
    return {"facts": FACTS.list()}


@app.get("/mcps")
def list_mcps():
    servers = []
    tools = get_mcp_tools()
    try:
        result = subprocess.run(
            ["docker", "mcp", "profile", "server", "ls", "--filter", f"profile={MCP_PROFILE}", "--format", "json"],
            capture_output=True, text=True, timeout=20,
        )
        if result.returncode == 0:
            data = json.loads(result.stdout)
            if data:
                servers = [s["snapshot"]["server"]["name"] for s in data[0].get("servers", [])]
    except (subprocess.TimeoutExpired, json.JSONDecodeError, KeyError, IndexError):
        pass
    return {
        "profile": MCP_PROFILE,
        "servers": servers,
        "tools": [{"name": t["name"], "description": t.get("description", "")} for t in tools],
    }


def system_message() -> dict[str, str]:
    content = POLICY
    facts = FACTS.list()
    if facts:
        content += "\n\nKnown facts (policy):\n" + "\n".join(
            f"- {fact['key']}: {fact['value']}" for fact in facts
        )
    skills = SKILLS.list()
    if skills:
        content += "\n\nAvailable skills (call by name to load full content):\n" + "\n".join(
            f"- {skill['name']}: {skill['description']}" for skill in skills
        )
    mcp_tools = get_mcp_tools()
    if mcp_tools:
        content += (
            f"\n\nMCP tools are available from the '{MCP_PROFILE}' profile "
            f"({len(mcp_tools)} tools). Use mcp-find to discover servers and mcp-add to enable them."
        )
    return {"role": "system", "content": content}


def _last_user_text(messages: list[dict[str, Any]]) -> str:
    for message in reversed(messages):
        if message.get("role") != "user":
            continue
        content = message.get("content")
        if isinstance(content, str):
            return content
        if isinstance(content, list):
            return " ".join(part.get("text", "") for part in content if part.get("type") == "text")
        return ""
    return ""


def _stream(data: dict[str, Any]) -> Iterator[str]:
    choice = data["choices"][0]
    message = choice["message"]
    created = data.get("created") or int(time.time())
    base = {
        "id": data.get("id") or f"chatcmpl-{created}",
        "object": "chat.completion.chunk",
        "created": created,
        "model": data.get("model", ""),
    }
    delta: dict[str, Any] = {"role": "assistant", "content": message.get("content")}
    if message.get("tool_calls"):
        delta["tool_calls"] = [
            {"index": index, **call} for index, call in enumerate(message["tool_calls"])
        ]
    chunks = (
        {"index": 0, "delta": delta, "finish_reason": None},
        {"index": 0, "delta": {}, "finish_reason": choice.get("finish_reason") or "stop"},
    )
    for chunk in chunks:
        yield f"data: {json.dumps({**base, 'choices': [chunk]})}\n\n"
    yield "data: [DONE]\n\n"


def _error(message: str, status: int) -> JSONResponse:
    return JSONResponse(
        {"error": {"message": message, "type": "proxy_error"}},
        status_code=status,
    )


async def _upstream_error(
    response: httpx.Response, client: httpx.AsyncClient, model: str | None = None
) -> JSONResponse:
    try:
        body = response.json()
    except ValueError:
        body = {"error": {"message": response.text}}
    message = (body.get("error") or {}).get("message") or ""
    if response.status_code == 403 and "Model access is disabled" in message:
        try:
            listing = await client.get("/models", headers=HEADERS)
            names = [item["id"] for item in listing.json()["data"]]
        except (ValueError, KeyError, TypeError, httpx.HTTPError):
            names = []
        available = f" Models on this key: {', '.join(names)}." if names else ""
        body = {
            "error": {
                "type": "model_access_disabled",
                "message": f"The key cannot access model '{model}'.{available}",
            }
        }
    return JSONResponse(body, status_code=response.status_code)


UI_HTML = r"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Zen Skills Proxy</title>
<style>
body { font-family: system-ui, sans-serif; margin: 2rem; color: #222; }
h1 { margin-bottom: .5rem; }
h2 { margin-top: 2rem; }
table { border-collapse: collapse; width: 100%; margin-top: .5rem; }
th, td { border: 1px solid #ddd; padding: .5rem; text-align: left; vertical-align: top; }
th { background: #f5f5f5; }
pre { white-space: pre-wrap; margin: 0; }
.empty { color: #888; font-style: italic; }
</style>
</head>
<body>
<h1>Zen Skills Proxy</h1>
<p>What the model has learned. Data persists in <code>knowledge.db</code>.</p>

<h2>Skills</h2>
<div id="skills"></div>

<h2>Facts</h2>
<div id="facts"></div>

<h2>MCPs (<span id="mcp-profile"></span>)</h2>
<div id="mcps"></div>

<script>
async function load() {
  const skills = await (await fetch('/skills')).json();
  const facts = await (await fetch('/facts')).json();
  const sb = document.getElementById('skills');
  if (!skills.skills.length) sb.innerHTML = '<p class="empty">No skills yet.</p>';
  else {
    let h = '<table><tr><th>Name</th><th>Description</th><th>Content</th></tr>';
    for (const s of skills.skills) {
      const full = await (await fetch('/skills/' + encodeURIComponent(s.name))).json();
      h += '<tr><td>' + esc(s.name) + '</td><td>' + esc(s.description) + '</td><td><pre>' + esc(full.content || '') + '</pre></td></tr>';
    }
    sb.innerHTML = h + '</table>';
  }
  const fb = document.getElementById('facts');
  if (!facts.facts.length) fb.innerHTML = '<p class="empty">No facts yet.</p>';
  else {
    let h = '<table><tr><th>Key</th><th>Value</th></tr>';
    for (const f of facts.facts) h += '<tr><td>' + esc(f.key) + '</td><td>' + esc(f.value) + '</td></tr>';
    fb.innerHTML = h + '</table>';
  }
}
async function loadMcps() {
  const box = document.getElementById('mcps');
  try {
    const data = await (await fetch('/mcps')).json();
    document.getElementById('mcp-profile').textContent = data.profile || '';
    const tools = data.tools || [];
    let html = '<p>Servers: ' + (data.servers || []).map(esc).join(', ') + '</p>';
    html += '<p>' + tools.length + ' tools</p>';
    if (tools.length) {
      html += '<table><tr><th>Name</th><th>Description</th></tr>';
      for (const t of tools) html += '<tr><td>' + esc(t.name) + '</td><td>' + esc(t.description || '') + '</td></tr>';
      html += '</table>';
    }
    box.innerHTML = html;
  } catch (e) {
    box.innerHTML = '<p class="empty">Unable to load MCPs.</p>';
  }
}
function esc(v){ return String(v).replace(/&/g,'&amp;').replace(/</g,'&lt;').replace(/>/g,'&gt;'); }
load();
loadMcps();
setInterval(function(){ load(); loadMcps(); }, 5000);
</script>
</body>
</html>
"""


def run() -> None:
    import uvicorn

    uvicorn.run(
        app,
        host=os.environ.get("HOST", "127.0.0.1"),
        port=int(os.environ.get("PORT", "8788")),
    )


if __name__ == "__main__":
    run()
