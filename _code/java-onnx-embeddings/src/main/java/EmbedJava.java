import ai.djl.huggingface.tokenizers.Encoding;
import ai.djl.huggingface.tokenizers.HuggingFaceTokenizer;
import ai.onnxruntime.OnnxTensor;
import ai.onnxruntime.OrtEnvironment;
import ai.onnxruntime.OrtSession;

import java.nio.LongBuffer;
import java.nio.file.Path;
import java.util.ArrayList;
import java.util.List;
import java.util.Map;

public class EmbedJava implements AutoCloseable {

    private static final int DIM = 384;

    private final OrtEnvironment env;
    private final OrtSession session;
    private final HuggingFaceTokenizer tokenizer;

    public EmbedJava(String modelPath, String tokenizerPath) throws Exception {
        env = OrtEnvironment.getEnvironment();
        session = env.createSession(modelPath);
        tokenizer = HuggingFaceTokenizer.newInstance(Path.of(tokenizerPath));
    }

    public float[] embed(String text) throws Exception {
        return embedBatch(new String[] { text })[0];
    }

    public long[] tokenIds(String text) {
        return tokenizer.encode(text).getIds();
    }

    // Runs one batched inference for many texts. Inputs are padded to the
    // longest text in the batch; mean pooling only averages real tokens,
    // never padding.
    public float[][] embedBatch(String[] texts) throws Exception {
        Encoding[] encodings = tokenizer.batchEncode(texts);

        int maxLen = 0;
        for (Encoding e : encodings) {
            maxLen = Math.max(maxLen, e.getIds().length);
        }

        int batch = encodings.length;
        long[] ids = new long[batch * maxLen];
        long[] mask = new long[batch * maxLen];
        long[] typeIds = new long[batch * maxLen];
        int[] realLen = new int[batch];

        for (int b = 0; b < batch; b++) {
            long[] bIds = encodings[b].getIds();
            long[] bMask = encodings[b].getAttentionMask();
            System.arraycopy(bIds, 0, ids, b * maxLen, bIds.length);
            System.arraycopy(bMask, 0, mask, b * maxLen, bMask.length);
            for (long m : bMask) {
                realLen[b] += (int) m;
            }
        }

        float[][] out = new float[batch][DIM];
        long[] shape = { batch, maxLen };
        try (OnnxTensor inputIds = OnnxTensor.createTensor(env, LongBuffer.wrap(ids), shape);
             OnnxTensor attentionMask = OnnxTensor.createTensor(env, LongBuffer.wrap(mask), shape);
             OnnxTensor tokenTypeIds = OnnxTensor.createTensor(env, LongBuffer.wrap(typeIds), shape);
             OrtSession.Result result = session.run(
                     Map.of("input_ids", inputIds,
                            "attention_mask", attentionMask,
                            "token_type_ids", tokenTypeIds))) {

            float[][][] lastHidden = (float[][][]) result.get("last_hidden_state").orElseThrow().getValue();

            for (int b = 0; b < batch; b++) {
                for (int j = 0; j < DIM; j++) {
                    float sum = 0;
                    for (int i = 0; i < realLen[b]; i++) {
                        sum += lastHidden[b][i][j];
                    }
                    out[b][j] = sum / realLen[b];
                }
            }
        }
        return out;
    }

    @Override
    public void close() throws Exception {
        session.close();
    }

    static double cosine(float[] a, float[] b) {
        double dot = 0, na = 0, nb = 0;
        for (int i = 0; i < a.length; i++) {
            dot += (double) a[i] * b[i];
            na += (double) a[i] * a[i];
            nb += (double) b[i] * b[i];
        }
        return dot / (Math.sqrt(na) * Math.sqrt(nb));
    }

    static List<String> sampleTexts(int n) {
        String[] base = {
            "Wireless Bluetooth headphones with noise cancelling",
            "A lady walks her dog through the park every morning.",
            "Stainless steel insulated water bottle, 750 ml",
            "The stock market went up sharply after the announcement",
            "Running shoes for men, lightweight trail trainers size 42",
            "Espresso coffee machine with integrated milk frother.",
            "Kids educational robot kit with programmable blocks",
            "organic cotton t-shirt crew neck",
            "The weather tomorrow will be partly cloudy",
            "laptop stand adjustable aluminum desk holder",
        };
        List<String> out = new ArrayList<>();
        for (int i = 0; i < n; i++) {
            out.add(base[i % base.length]);
        }
        return out;
    }

    public static void main(String[] args) throws Exception {
        String modelPath = args.length > 0 ? args[0] : "model.onnx";
        String tokenizerPath = args.length > 1 ? args[1] : "tokenizer.json";

        try (EmbedJava demo = new EmbedJava(modelPath, tokenizerPath)) {
            System.out.print("Token IDs: ");
            for (long id : demo.tokenIds("hello world")) {
                System.out.print(id + " ");
            }
            System.out.println();

            float[] hello = demo.embed("hello world");
            System.out.print("Embedding (first 10 dims): ");
            for (int i = 0; i < 10; i++) {
                System.out.printf(i > 0 ? ", %.4f" : "%.4f", hello[i]);
            }
            double norm = 0;
            for (float v : hello) {
                norm += (double) v * v;
            }
            System.out.printf("%nEmbedding norm: %.4f%n", Math.sqrt(norm));

            float[] e1 = demo.embed("The woman is walking.");
            float[] e2 = demo.embed("A lady is walking.");
            float[] e3 = demo.embed("The stock market went up.");
            System.out.printf("%ncosine(\"The woman is walking.\", \"A lady is walking.\") = %.4f%n", cosine(e1, e2));
            System.out.printf("cosine(\"The woman is walking.\", \"The stock market went up.\") = %.4f%n", cosine(e1, e3));

            String extra = System.getProperty("text");
            if (extra != null) {
                float[] e = demo.embed(extra);
                System.out.printf("%nembed(%s): ", extra);
                for (int i = 0; i < 10; i++) {
                    System.out.printf(i > 0 ? ", %.4f" : "%.4f", e[i]);
                }
                System.out.println();
            }

            int rounds = Integer.parseInt(System.getProperty("bench", "0"));
            if (rounds > 0) {
                long start = System.nanoTime();
                for (int i = 0; i < rounds; i++) {
                    demo.embed("A lady is walking.");
                }
                long elapsed = System.nanoTime() - start;
                System.out.printf("%nbench single: %d embeddings in %.2f s (%.2f ms per embedding)%n",
                        rounds, elapsed / 1e9, elapsed / 1e6 / rounds);

                List<String> texts = sampleTexts(rounds);
                start = System.nanoTime();
                float[][] batched = demo.embedBatch(texts.toArray(new String[0]));
                elapsed = System.nanoTime() - start;
                System.out.printf("bench batch:  %d embeddings in %.2f s (%.2f ms per embedding)%n",
                        rounds, elapsed / 1e9, elapsed / 1e6 / rounds);

                float maxDiff = 0;
                for (int i = 0; i < texts.size(); i++) {
                    float[] single = demo.embed(texts.get(i));
                    for (int j = 0; j < DIM; j++) {
                        maxDiff = Math.max(maxDiff, Math.abs(single[j] - batched[i][j]));
                    }
                }
                System.out.printf("max abs difference batch vs single: %.7f%n", maxDiff);
            }
        }
    }
}
