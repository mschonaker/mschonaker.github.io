import json
import os
import re
import sqlite3
from contextlib import asynccontextmanager, closing
from pathlib import Path
from typing import Any

import httpx
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse, Response

BASE_URL = os.environ.get("OPENCODE_BASE_URL", "https://opencode.ai/inference/openai/v1")
API_KEY = os.environ.get("OPENCODE_API_KEY", "")
MODEL = os.environ.get("DEFAULT_MODEL", "qwen3.8-flash")
DB = Path(os.environ.get("MEMORY_DB", "memory.db"))
HEADERS = {"Authorization": f"Bearer {API_KEY}"}
POLICY = "Save durable facts with remember. Call recall before you answer a question about the user."


def tool(name: str, description: str, field: str) -> dict[str, Any]:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": description,
            "parameters": {
                "type": "object",
                "properties": {field: {"type": "string"}},
                "required": [field],
            },
        },
    }


TOOLS = [
    tool("remember", "Save one durable fact about the user.", "fact"),
    tool("recall", "Search saved facts with a short keyword query.", "query"),
]
OWNED = {item["function"]["name"] for item in TOOLS}


def run_tool(name: str, raw: str) -> str:
    args = json.loads(raw)
    with closing(sqlite3.connect(DB)) as db:
        db.execute("CREATE TABLE IF NOT EXISTS facts (id INTEGER PRIMARY KEY, text TEXT)")
        if name == "remember":
            cursor = db.execute("INSERT INTO facts(text) VALUES (?)", (args["fact"],))
            db.commit()
            return json.dumps({"id": cursor.lastrowid})
        words = [w for w in re.findall(r"\w+", args["query"].lower()) if len(w) > 1][:8]
        if not words:
            return json.dumps({"facts": []})
        where = " OR ".join("text LIKE ?" for _ in words)
        rows = db.execute(
            f"SELECT id, text FROM facts WHERE {where} LIMIT 5",
            [f"%{word}%" for word in words],
        ).fetchall()
        if len(rows) < 5:
            rows = db.execute("SELECT id, text FROM facts ORDER BY id DESC LIMIT 5").fetchall()
        return json.dumps({"facts": [{"id": row[0], "text": row[1]} for row in rows]})


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with httpx.AsyncClient(base_url=BASE_URL, timeout=180) as client:
        app.state.zen = client
        yield


app = FastAPI(lifespan=lifespan)


def sse(data: dict[str, Any]) -> str:
    choice = data["choices"][0]
    base = {key: data[key] for key in ("id", "created", "model")}
    base["object"] = "chat.completion.chunk"
    delta = {"role": "assistant", "content": choice["message"].get("content")}
    chunks = [
        {**base, "choices": [{"index": 0, "delta": delta, "finish_reason": None}]},
        {**base, "choices": [{"index": 0, "delta": {}, "finish_reason": "stop"}]},
    ]
    return "".join(f"data: {json.dumps(chunk)}\n\n" for chunk in chunks) + "data: [DONE]\n\n"


@app.post("/v1/chat/completions")
async def chat(request: Request):
    body = await request.json()
    stream = body.pop("stream", False)
    body.pop("stream_options", None)
    messages = [{"role": "system", "content": POLICY}, *body.pop("messages", [])]
    client_tools = body.pop("tools", None) or []
    taken = {item["function"]["name"] for item in client_tools}
    tools = [*client_tools, *(item for item in TOOLS if item["function"]["name"] not in taken)]
    body["model"] = body.get("model") or MODEL
    body["tool_choice"] = body.get("tool_choice", "auto")

    for _ in range(6):
        response = await request.app.state.zen.post(
            "/chat/completions",
            json={**body, "messages": messages, "tools": tools},
            headers=HEADERS,
        )
        if response.status_code != 200:
            return JSONResponse(response.json(), status_code=response.status_code)
        data = response.json()
        message = data["choices"][0]["message"]
        calls = message.get("tool_calls") or []
        if not calls or any(call["function"]["name"] not in OWNED for call in calls):
            break
        messages.append({"role": "assistant", "content": message.get("content"), "tool_calls": calls})
        for call in calls:
            messages.append(
                {
                    "role": "tool",
                    "tool_call_id": call["id"],
                    "content": run_tool(call["function"]["name"], call["function"]["arguments"]),
                }
            )
    else:
        return JSONResponse({"error": {"message": "tool loop limit"}}, status_code=502)

    if not stream:
        return JSONResponse(data)
    return Response(sse(data), media_type="text/event-stream")


@app.get("/v1/models")
async def models(request: Request):
    response = await request.app.state.zen.get("/models", headers=HEADERS)
    return JSONResponse(response.json(), status_code=response.status_code)


@app.get("/health")
async def health():
    return {"ok": True, "model": MODEL, "db": str(DB)}


if __name__ == "__main__":
    import uvicorn

    uvicorn.run(app, host="127.0.0.1", port=int(os.environ.get("PORT", "8787")))
