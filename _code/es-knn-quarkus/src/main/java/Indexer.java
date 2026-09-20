import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;
import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Iterator;
import java.util.List;

public class Indexer {

    static final ObjectMapper MAPPER = new ObjectMapper();
    static final HttpClient HTTP = HttpClient.newHttpClient();

    static String esUrl;
    static String index;

    static HttpResponse<String> send(String method, String path, String body, String contentType)
            throws Exception {
        HttpRequest.Builder b = HttpRequest.newBuilder(URI.create(esUrl + path))
                .method(method, body == null
                        ? HttpRequest.BodyPublishers.noBody()
                        : HttpRequest.BodyPublishers.ofString(body));
        if (contentType != null) {
            b.header("Content-Type", contentType);
        }
        return HTTP.send(b.build(), HttpResponse.BodyHandlers.ofString());
    }

    static void recreateIndex() throws Exception {
        send("DELETE", "/" + index, null, null);
        ObjectNode body = MAPPER.createObjectNode();
        ObjectNode props = body.putObject("mappings").putObject("properties");
        props.putObject("objectID").put("type", "keyword");
        props.putObject("name").put("type", "text");
        props.putObject("brand").put("type", "keyword");
        props.putObject("price").put("type", "float");
        props.putObject("image").put("type", "keyword");
        props.putObject("categories").put("type", "keyword");
        props.putObject("embedding")
                .put("type", "dense_vector")
                .put("dims", Embedder.DIM)
                .put("index", true)
                .put("similarity", "cosine");
        HttpResponse<String> res = send("PUT", "/" + index, body.toString(), "application/json");
        if (res.statusCode() >= 300) {
            throw new IllegalStateException("index creation failed: " + res.body());
        }
    }

    static String textOf(JsonNode rec) {
        String name = rec.get("name").asText();
        String description = rec.path("description").asText("");
        return description.isEmpty() ? name : name + ". " + description;
    }

    static String docLine(JsonNode rec, float[] vector) {
        ObjectNode action = MAPPER.createObjectNode();
        action.putObject("index").put("_index", index).put("_id", rec.get("objectID").asText());
        ObjectNode doc = MAPPER.createObjectNode();
        doc.put("objectID", rec.get("objectID").asText());
        doc.put("name", rec.get("name").asText());
        doc.put("brand", rec.path("brand").asText(""));
        doc.put("price", rec.path("price").asDouble());
        doc.put("image", rec.path("image").asText(""));
        ArrayNode cats = doc.putArray("categories");
        rec.path("categories").forEach(c -> cats.add(c.asText()));
        ArrayNode v = doc.putArray("embedding");
        for (float f : vector) {
            v.add(f);
        }
        return action.toString() + "\n" + doc.toString() + "\n";
    }

    static void flushBulk(StringBuilder ndjson) throws Exception {
        if (ndjson.length() == 0) {
            return;
        }
        HttpResponse<String> res = send("POST", "/_bulk", ndjson.toString(), "application/x-ndjson");
        if (res.statusCode() >= 300 || res.body().contains("\"errors\":true")) {
            throw new IllegalStateException("bulk failed: "
                    + res.body().substring(0, Math.min(500, res.body().length())));
        }
        ndjson.setLength(0);
    }

    public static void main(String[] args) throws Exception {
        esUrl = System.getProperty("es.url", "http://localhost:9200");
        index = System.getProperty("es.index", "products");
        String dataFile = args.length > 0 ? args[0] : "data/records.json";
        int embedBatch = Integer.getInteger("embed.batch", 64);
        int bulkEvery = Integer.getInteger("bulk.docs", 512);

        try (Embedder embedder = new Embedder(
                System.getProperty("embedder.model-path", "model.onnx"),
                System.getProperty("embedder.tokenizer-path", "tokenizer.json"))) {

            recreateIndex();

            Iterator<JsonNode> records = MAPPER.readTree(Files.readString(Path.of(dataFile))).elements();

            long embedNanos = 0, bulkNanos = 0;
            int count = 0, sinceFlush = 0;
            int sinceReport = 0;
            StringBuilder ndjson = new StringBuilder();
            List<JsonNode> pending = new ArrayList<>();

            long start = System.nanoTime();
            while (records.hasNext()) {
                pending.add(records.next());
                if (pending.size() < embedBatch) {
                    continue;
                }
                long e0 = System.nanoTime();
                count += processBatch(pending, embedder, ndjson);
                embedNanos += System.nanoTime() - e0;
                sinceFlush += pending.size();
                sinceReport += pending.size();
                pending.clear();
                if (sinceFlush >= bulkEvery) {
                    long b0 = System.nanoTime();
                    flushBulk(ndjson);
                    bulkNanos += System.nanoTime() - b0;
                    sinceFlush = 0;
                }
                if (sinceReport >= 2000) {
                    System.out.printf("embedded %d ...%n", count);
                    sinceReport = 0;
                }
            }

            if (!pending.isEmpty()) {
                long e0 = System.nanoTime();
                count += processBatch(pending, embedder, ndjson);
                embedNanos += System.nanoTime() - e0;
            }
            long b0 = System.nanoTime();
            flushBulk(ndjson);
            bulkNanos += System.nanoTime() - b0;
            send("POST", "/" + index + "/_refresh", null, null);

            double totalSec = (System.nanoTime() - start) / 1e9;
            System.out.printf("done: %d docs in %.1f s (%.0f docs/s) | embed %.1f s | bulk %.1f s%n",
                    count, totalSec, count / totalSec, embedNanos / 1e9, bulkNanos / 1e9);
        }
    }

    // embeds pending texts and appends their bulk lines; returns docs processed
    static int processBatch(List<JsonNode> pending, Embedder embedder, StringBuilder ndjson)
            throws Exception {
        String[] texts = new String[pending.size()];
        for (int i = 0; i < pending.size(); i++) {
            texts[i] = textOf(pending.get(i));
        }
        float[][] vectors = embedder.embedBatch(texts);
        for (int i = 0; i < pending.size(); i++) {
            ndjson.append(docLine(pending.get(i), vectors[i]));
        }
        return pending.size();
    }
}
