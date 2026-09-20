import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import com.sun.net.httpserver.HttpExchange;
import com.sun.net.httpserver.HttpServer;

import java.io.OutputStream;
import java.net.InetSocketAddress;
import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.HashMap;
import java.util.LinkedHashMap;
import java.util.Map;

// Minimal comparison server: same query against every experiment index.
//   GET /            -> page with an index selector and a search box
//   GET /api/search  -> ?index=<name>&q=<text>&n=10, embedded + projected per index
public class SearchServer {

    static final ObjectMapper MAPPER = new ObjectMapper();

    record Variant(String index, int dims, String pcaFile, String label) {
    }

    static final Variant[] VARIANTS = {
        new Variant("products_hnsw", 384, null, "384 dims - float HNSW (exact-ish)"),
        new Variant("products_bbq", 384, null, "384 dims - BBQ (ES default)"),
        new Variant("products_pca128", 128, "pca128.txt", "128 dims - PCA"),
        new Variant("products_pca64", 64, "pca64.txt", "64 dims - PCA"),
        new Variant("products_pca32", 32, "pca32.txt", "32 dims - PCA"),
        new Variant("products_pca128bbq", 128, "pca128.txt", "128 dims - PCA + BBQ"),
    };

    record Product(String name, String brand, String price, String categories) {
    }

    static java.util.List<Product> catalog = new java.util.ArrayList<>();
    static Map<String, Variant> byName = new HashMap<>();
    static Embedder embedder;
    static Map<String, Pca> pcaCache = new HashMap<>();

    public static void main(String[] args) throws Exception {
        Es.url = System.getProperty("es.url", "http://localhost:9200");
        int port = Integer.getInteger("port", 8090);
        String dataFile = args.length > 0 ? args[0] : "../es-knn-quarkus/data/records.json";

        for (JsonNode rec : MAPPER.readTree(Files.readString(Path.of(dataFile)))) {
            catalog.add(new Product(
                    rec.get("name").asText(),
                    rec.path("brand").asText(""),
                    rec.path("price").asText(""),
                    rec.path("categories").path(0).asText("")));
        }
        embedder = new Embedder(
                System.getProperty("embedder.model-path", "model.onnx"),
                System.getProperty("embedder.tokenizer-path", "tokenizer.json"));
        for (Variant v : VARIANTS) {
            byName.put(v.index, v);
            if (v.pcaFile != null) {
                pcaCache.put(v.index, Pca.load(Path.of(v.pcaFile)));
            }
        }

        HttpServer server = HttpServer.create(new InetSocketAddress(port), 0);
        server.createContext("/", ex -> {
            try {
                respond(ex, page(), "text/html; charset=utf-8");
            } catch (Exception e) {
                respondError(ex, e);
            }
        });
        server.createContext("/api/search", ex -> {
            try {
                respond(ex, search(ex), "application/json");
            } catch (Exception e) {
                respondError(ex, e);
            }
        });
        server.start();
        System.out.println("search server on http://localhost:" + port + " (" + catalog.size() + " products)");
    }

    static void respondError(HttpExchange ex, Exception e) {
        try {
            byte[] body = ("error: " + e).getBytes(StandardCharsets.UTF_8);
            ex.sendResponseHeaders(500, body.length);
            try (OutputStream out = ex.getResponseBody()) {
                out.write(body);
            }
        } catch (Exception ignored) {
        }
        e.printStackTrace();
    }

    static void respond(HttpExchange ex, byte[] body, String contentType) throws Exception {
        ex.getResponseHeaders().add("Content-Type", contentType);
        ex.sendResponseHeaders(200, body.length);
        try (OutputStream out = ex.getResponseBody()) {
            out.write(body);
        }
    }

    static byte[] search(HttpExchange ex) throws Exception {
        Map<String, String> params = new HashMap<>();
        String raw = ex.getRequestURI().getRawQuery();
        if (raw != null) {
            for (String pair : raw.split("&")) {
                String[] kv = pair.split("=", 2);
                params.put(URLDecoder.decode(kv[0], StandardCharsets.UTF_8),
                        kv.length > 1 ? URLDecoder.decode(kv[1], StandardCharsets.UTF_8) : "");
            }
        }
        String index = params.getOrDefault("index", "products_hnsw");
        String q = params.getOrDefault("q", "");
        int n = Integer.parseInt(params.getOrDefault("n", "10"));
        Variant v = byName.get(index);
        Pca pca = pcaCache.get(index);

        ObjectNode out = MAPPER.createObjectNode();
        if (v == null || q.isBlank()) {
            out.putArray("hits");
            return out.toString().getBytes(StandardCharsets.UTF_8);
        }

        float[] vec = embedder.embed(q);
        if (pca != null) {
            vec = pca.project(vec);
        }
        ObjectNode body = MAPPER.createObjectNode();
        body.put("size", n);
        body.put("_source", false);
        ObjectNode knn = body.putObject("knn");
        knn.put("field", "embedding");
        knn.put("k", n);
        knn.put("num_candidates", 100);
        knn.set("query_vector", MAPPER.valueToTree(vec));

        long t0 = System.nanoTime();
        JsonNode res = Es.json("POST", "/" + v.index + "/_search", body.toString(), "application/json");
        out.put("took", res.path("took").asLong());
        out.put("wall_ms", Math.round((System.nanoTime() - t0) / 1e6 * 10) / 10.0);
        out.put("dims", v.dims);
        ArrayNode hits = out.putArray("hits");
        for (JsonNode hit : res.path("hits").path("hits")) {
            ObjectNode item = hits.addObject();
            Product p = catalog.get(Integer.parseInt(hit.path("_id").asText()));
            item.put("name", p == null ? "?" : p.name());
            item.put("brand", p == null ? "" : p.brand());
            item.put("price", p == null ? "" : p.price());
            item.put("categories", p == null ? "" : p.categories());
            item.put("score", hit.path("_score").asDouble());
        }
        return out.toString().getBytes(StandardCharsets.UTF_8);
    }

    static byte[] page() {
        StringBuilder options = new StringBuilder();
        for (Variant v : VARIANTS) {
            options.append("<option value=\"").append(v.index()).append("\">").append(v.label()).append("</option>");
        }
        String html = """
                <!DOCTYPE html>
                <html lang="en"><head><meta charset="utf-8"><title>PCA feel test</title>
                <style>
                  body { font-family: system-ui, sans-serif; max-width: 760px; margin: 3rem auto; padding: 0 1rem; }
                  form { display: flex; gap: .5rem; }
                  input[type=search] { flex: 1; padding: .6rem; font-size: 1rem; }
                  select, button { padding: .6rem; font-size: 1rem; }
                  li { margin: .5rem 0; padding: .5rem; border: 1px solid #ddd; border-radius: 6px; list-style: none; }
                  ul { padding: 0; }
                  .meta { color: #666; font-size: .85rem; }
                </style></head><body>
                <h1>PCA feel test</h1>
                <p>Same query, different index variants. Flip the selector and feel where ranking quality goes.</p>
                <form id="f">
                  <select id="ix">%s</select>
                  <input type="search" id="q" placeholder="e.g. quiet keyboard for office work" autofocus>
                  <button type="submit">Search</button>
                </form>
                <p class="meta" id="meta"></p>
                <ul id="results"></ul>
                <script>
                const f = document.getElementById('f');
                f.addEventListener('submit', async (e) => {
                  e.preventDefault();
                  const q = document.getElementById('q').value.trim();
                  if (!q) return;
                  const ix = document.getElementById('ix').value;
                  const list = document.getElementById('results');
                  list.innerHTML = '<li>searching…</li>';
                  const res = await fetch('/api/search?index=' + ix + '&q=' + encodeURIComponent(q) + '&n=10');
                  const data = await res.json();
                  document.getElementById('meta').textContent = data.dims + ' dims · ES took ' + data.took + ' ms · round trip ' + data.wall_ms + ' ms';
                  list.innerHTML = data.hits.map(h =>
                    `<li><b>${h.name}</b><br><span class="meta">${h.brand} · $${h.price} · ${h.categories} · score ${h.score.toFixed(4)}</span></li>`
                  ).join('') || '<li>no results</li>';
                });
                </script></body></html>
                """.formatted(options.toString());
        return html.getBytes(StandardCharsets.UTF_8);
    }
}
