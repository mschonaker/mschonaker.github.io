import ai.djl.huggingface.tokenizers.Encoding;
import ai.djl.huggingface.tokenizers.HuggingFaceTokenizer;
import ai.onnxruntime.OnnxTensor;
import ai.onnxruntime.OrtEnvironment;
import ai.onnxruntime.OrtSession;

import java.nio.LongBuffer;
import java.nio.file.Path;
import java.util.Map;

public class Embedder implements AutoCloseable {

    public static final int DIM = 384;

    private final OrtEnvironment env = OrtEnvironment.getEnvironment();
    private final OrtSession session;
    private final HuggingFaceTokenizer tokenizer;

    public Embedder(String modelPath, String tokenizerPath) throws Exception {
        session = env.createSession(modelPath);
        tokenizer = HuggingFaceTokenizer.newInstance(Path.of(tokenizerPath));
    }

    public float[] embed(String text) throws Exception {
        return embedBatch(new String[] { text })[0];
    }

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
}
