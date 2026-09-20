import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.HashSet;
import java.util.List;
import java.util.Set;

// Measures every experiment index against exact 384-dim ground truth.
// For each query: recall@10, ES took, client-side wall time, and index store size.
public class Eval {

    static final ObjectMapper MAPPER = new ObjectMapper();
    static final int K = 10;
    static final int CANDIDATES = 100;

    record Variant(String index, int dims, String pcaFile) {
    }

    static final Variant[] VARIANTS = {
        new Variant("products_hnsw", 384, null),
        new Variant("products_bbq", 384, null),
        new Variant("products_pca128", 128, "pca128.txt"),
        new Variant("products_pca64", 64, "pca64.txt"),
        new Variant("products_pca32", 32, "pca32.txt"),
        new Variant("products_pca128bbq", 128, "pca128.txt"),
        new Variant("products_flat384", 384, null),
        new Variant("products_flat128", 128, "pca128.txt"),
        new Variant("products_flat32", 32, "pca32.txt"),
    };

    static List<String> readQueries() throws Exception {
        return Files.readAllLines(Path.of("queries.txt")).stream()
                .map(String::trim).filter(s -> !s.isEmpty()).toList();
    }

    // exact top-10 by cosine over stored 384-dim float vectors (brute force scan)
    static Set<String> groundTruth(Embedder embedder, String query) throws Exception {
        float[] vec = embedder.embed(query);
        ObjectNode body = MAPPER.createObjectNode();
        body.put("size", K);
        body.put("_source", false);
        ObjectNode ss = body.putObject("query").putObject("script_score");
        ss.putObject("query").putObject("match_all");
        ObjectNode script = ss.putObject("script");
        script.put("source", "cosineSimilarity(params.q, 'embedding') + 1.0");
        script.putObject("params").set("q", MAPPER.valueToTree(vec));

        JsonNode res = Es.json("POST", "/products_hnsw/_search", body.toString(), "application/json");
        Set<String> ids = new HashSet<>();
        for (JsonNode hit : res.path("hits").path("hits")) {
            ids.add(hit.path("_id").asText());
        }
        return ids;
    }

    static float[] queryVector(Embedder embedder, Pca pca, String query) throws Exception {
        float[] vec = embedder.embed(query);
        return pca == null ? vec : pca.project(vec);
    }

    public static void main(String[] args) throws Exception {
        Es.url = System.getProperty("es.url", "http://localhost:9200");
        List<String> queries = readQueries();

        try (Embedder embedder = new Embedder(
                System.getProperty("embedder.model-path", "model.onnx"),
                System.getProperty("embedder.tokenizer-path", "tokenizer.json"))) {

            List<Set<String>> truth = new ArrayList<>();
            for (String q : queries) {
                truth.add(groundTruth(embedder, q));
            }

            System.out.println("index, dims, recall@10, mean_took_ms, mean_wall_ms, store_mb");
            for (Variant v : VARIANTS) {
                Pca pca = v.pcaFile == null ? null : Pca.load(Path.of(v.pcaFile));

                // warmup
                runOne(v, pca, embedder, queries.get(0));

                double recallSum = 0, tookSum = 0, wallSum = 0;
                for (int i = 0; i < queries.size(); i++) {
                    long t0 = System.nanoTime();
                    JsonNode res = runOne(v, pca, embedder, queries.get(i));
                    wallSum += (System.nanoTime() - t0) / 1e6;
                    tookSum += res.path("took").asDouble();

                    Set<String> got = new HashSet<>();
                    for (JsonNode hit : res.path("hits").path("hits")) {
                        got.add(hit.path("_id").asText());
                    }
                    Set<String> both = new HashSet<>(got);
                    both.retainAll(truth.get(i));
                    recallSum += both.size() / (double) K;
                }
                int q = queries.size();
                long storeMb = Es.storeSizeBytes(v.index) / 1_048_576;
                System.out.printf("%s, %d, %.3f, %.1f, %.1f, %d%n",
                        v.index, v.dims, recallSum / q, tookSum / q, wallSum / q, storeMb);
            }
        }
    }

    static JsonNode runOne(Variant v, Pca pca, Embedder embedder, String query) throws Exception {
        float[] qvec = queryVector(embedder, pca, query);
        ObjectNode body = MAPPER.createObjectNode();
        body.put("size", K);
        body.put("_source", false);
        ObjectNode knn = body.putObject("knn");
        knn.put("field", "embedding");
        knn.put("k", K);
        knn.put("num_candidates", CANDIDATES);
        knn.set("query_vector", MAPPER.valueToTree(qvec));
        return Es.json("POST", "/" + v.index + "/_search", body.toString(), "application/json");
    }
}
