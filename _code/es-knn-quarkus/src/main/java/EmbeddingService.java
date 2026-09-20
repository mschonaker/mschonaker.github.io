import jakarta.annotation.PreDestroy;
import jakarta.enterprise.context.ApplicationScoped;
import org.eclipse.microprofile.config.inject.ConfigProperty;

@ApplicationScoped
public class EmbeddingService {

    @ConfigProperty(name = "embedder.model-path", defaultValue = "model.onnx")
    String modelPath;

    @ConfigProperty(name = "embedder.tokenizer-path", defaultValue = "tokenizer.json")
    String tokenizerPath;

    volatile Embedder embedder;

    synchronized Embedder embedder() {
        if (embedder == null) {
            try {
                embedder = new Embedder(modelPath, tokenizerPath);
            } catch (Exception e) {
                throw new IllegalStateException(
                        "cannot load model/tokenizer from " + modelPath + ", " + tokenizerPath, e);
            }
        }
        return embedder;
    }

    public float[] embed(String text) throws Exception {
        return embedder().embed(text);
    }

    @PreDestroy
    void close() throws Exception {
        if (embedder != null) {
            embedder.close();
        }
    }
}
