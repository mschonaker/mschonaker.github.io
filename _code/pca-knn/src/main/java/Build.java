import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;

import java.nio.file.Files;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.Iterator;
import java.util.List;

// Embeds the catalog once, fits PCA, and builds every experiment index.
//   products_hnsw   384d, float32, index_options=hnsw   (exact, uncompressed)
//   products_bbq    384d, float32, index_options=bbq_hnsw (Elasticsearch default)
//   products_pca128 128d projected, hnsw
//   products_pca64   64d projected, hnsw
//   products_pca32   32d projected, hnsw
public class Build {

    static final ObjectMapper MAPPER = new ObjectMapper();
    static final int[] PCA_DIMS = { 128, 64, 32 };

    public static void main(String[] args) throws Exception {
        Es.url = System.getProperty("es.url", "http://localhost:9200");
        String dataFile = args.length > 0 ? args[0] : "../es-knn-quarkus/data/records.json";
        int embedBatch = Integer.getInteger("embed.batch", 64);

        try (Embedder embedder = new Embedder(
                System.getProperty("embedder.model-path", "model.onnx"),
                System.getProperty("embedder.tokenizer-path", "tokenizer.json"))) {

            List<JsonNode> docs = new ArrayList<>();
            List<String> texts = new ArrayList<>();
            Iterator<JsonNode> records = MAPPER.readTree(Files.readString(Path.of(dataFile))).elements();
            while (records.hasNext()) {
                JsonNode rec = records.next();
                docs.add(rec);
                String name = rec.get("name").asText();
                String desc = rec.path("description").asText("");
                texts.add(desc.isEmpty() ? name : name + ". " + desc);
            }
            int n = docs.size();
            System.out.println("records: " + n);

            float[][] vectors = new float[n][];
            long t0 = System.nanoTime();
            for (int i = 0; i < n; i += embedBatch) {
                String[] batch = texts.subList(i, Math.min(i + embedBatch, n)).toArray(new String[0]);
                float[][] out = embedder.embedBatch(batch);
                System.arraycopy(out, 0, vectors, i, out.length);
            }
            System.out.printf("embedded %d in %.1f s%n", n, (System.nanoTime() - t0) / 1e9);

            long f0 = System.nanoTime();
            Pca full = Pca.fit(vectors, Embedder.DIM);
            System.out.printf("PCA fit in %.1f s%n", (System.nanoTime() - f0) / 1e9);
            for (int k : PCA_DIMS) {
                System.out.printf("variance explained at %d dims: %.3f%n", k, full.explainedVarianceRatio(k));
                sliceAndSave(full, k, Path.of("pca" + k + ".txt"));
            }

            build("products_hnsw", vectors, null, "hnsw");
            build("products_bbq", vectors, null, "bbq_hnsw");
            build("products_pca128", vectors, "pca128.txt", "hnsw");
            build("products_pca64", vectors, "pca64.txt", "hnsw");
            build("products_pca32", vectors, "pca32.txt", "hnsw");
            // the reductions stack: project first, let Elasticsearch quantize the result
            build("products_pca128bbq", vectors, "pca128.txt", "bbq_hnsw");
            // flat = brute force: every score touches every dimension, so
            // dimension count shows its effect on scoring work directly
            build("products_flat384", vectors, null, "flat");
            build("products_flat128", vectors, "pca128.txt", "flat");
            build("products_flat32", vectors, "pca32.txt", "flat");
            System.out.println("build complete");
        }
    }

    static void sliceAndSave(Pca full, int k, Path out) throws Exception {
        double[][] comps = new double[k][];
        System.arraycopy(full.components, 0, comps, 0, k);
        Pca sliced = Pca.reconstruct(full.mean, comps);
        sliced.save(out);
    }

    static void build(String index, float[][] vectors, String pcaFile, String type) throws Exception {
        Pca pca = pcaFile == null ? null : Pca.load(Path.of(pcaFile));
        int dims = pca == null ? Embedder.DIM : pca.components.length;
        Es.createVectorIndex(index, dims, type);

        StringBuilder nd = new StringBuilder();
        for (int i = 0; i < vectors.length; i++) {
            float[] vec = pca == null ? vectors[i] : pca.project(vectors[i]);
            nd.append(action(index, i)).append(doc(vec, i)).append('\n');
            if ((i + 1) % 512 == 0) {
                Es.bulk(index, nd.toString());
                nd.setLength(0);
            }
        }
        if (nd.length() > 0) {
            Es.bulk(index, nd.toString());
        }
        Es.json("POST", "/" + index + "/_refresh", null, null);
        System.out.printf("%s (%dd, %s): %d docs, store %d MB%n",
                index, dims, type, vectors.length, Es.storeSizeBytes(index) / 1_048_576);
    }

    // metadata not stored in _source to keep the experiment about vectors only;
    // the objectID is the position in the catalog, so eval can align hits by _id.
    static String action(String index, int id) {
        ObjectNode a = MAPPER.createObjectNode();
        a.putObject("index").put("_index", index).put("_id", Integer.toString(id));
        return a.toString() + "\n";
    }

    static String doc(float[] vector, int id) {
        ObjectNode d = MAPPER.createObjectNode();
        d.put("id", id);
        ArrayNode v = d.putArray("embedding");
        for (float f : vector) {
            v.add(f);
        }
        return d.toString() + "\n";
    }
}
