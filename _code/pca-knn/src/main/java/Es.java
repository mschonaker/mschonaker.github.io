import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;

public class Es {

    static final ObjectMapper MAPPER = new ObjectMapper();
    static final HttpClient HTTP = HttpClient.newHttpClient();

    public static String url;

    static HttpResponse<String> send(String method, String path, String body, String contentType)
            throws Exception {
        HttpRequest.Builder b = HttpRequest.newBuilder(URI.create(url + path))
                .method(method, body == null
                        ? HttpRequest.BodyPublishers.noBody()
                        : HttpRequest.BodyPublishers.ofString(body));
        if (contentType != null) {
            b.header("Content-Type", contentType);
        }
        return HTTP.send(b.build(), HttpResponse.BodyHandlers.ofString());
    }

    public static JsonNode json(String method, String path, String body, String contentType)
            throws Exception {
        HttpResponse<String> res = send(method, path, body, contentType);
        if (res.statusCode() >= 300) {
            throw new IllegalStateException(path + " -> " + res.body());
        }
        return MAPPER.readTree(res.body());
    }

    public static void createVectorIndex(String index, int dims, String indexType) throws Exception {
        send("DELETE", "/" + index, null, null);
        String options = indexType == null ? "" : ",\"index_options\":{\"type\":\"" + indexType + "\"}";
        String body = "{\"mappings\":{\"properties\":{"
                + "\"id\":{\"type\":\"long\"},"
                + "\"embedding\":{\"type\":\"dense_vector\",\"dims\":" + dims
                + ",\"index\":true,\"similarity\":\"cosine\"" + options + "}}}}";
        json("PUT", "/" + index, body, "application/json");
    }

    public static void bulk(String index, String ndjson) throws Exception {
        JsonNode res = json("POST", "/_bulk", ndjson, "application/x-ndjson");
        if (res.path("errors").asBoolean()) {
            throw new IllegalStateException("bulk errors in " + index + ": "
                    + res.toString().substring(0, Math.min(500, res.toString().length())));
        }
    }

    public static long storeSizeBytes(String index) throws Exception {
        return json("GET", "/" + index + "/_stats/store", null, null)
                .path("indices").path(index).path("total").path("store")
                .path("size_in_bytes").asLong();
    }

    public static long tookMillis(JsonNode searchResponse) {
        return searchResponse.path("took").asLong();
    }
}
