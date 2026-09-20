import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.fasterxml.jackson.databind.node.ArrayNode;
import com.fasterxml.jackson.databind.node.ObjectNode;
import jakarta.inject.Inject;
import jakarta.ws.rs.GET;
import jakarta.ws.rs.Path;
import jakarta.ws.rs.Produces;
import jakarta.ws.rs.QueryParam;
import jakarta.ws.rs.core.MediaType;
import org.eclipse.microprofile.config.inject.ConfigProperty;

import java.net.URI;
import java.net.http.HttpClient;
import java.net.http.HttpRequest;
import java.net.http.HttpResponse;

@Path("/api/search")
public class SearchResource {

    static final ObjectMapper MAPPER = new ObjectMapper();
    static final HttpClient HTTP = HttpClient.newHttpClient();

    @Inject
    EmbeddingService embedder;

    @ConfigProperty(name = "es.url", defaultValue = "http://localhost:9200")
    String esUrl;

    @ConfigProperty(name = "es.index", defaultValue = "products")
    String index;

    @ConfigProperty(name = "search.num-candidates", defaultValue = "100")
    int numCandidates;

    @GET
    @Produces(MediaType.APPLICATION_JSON)
    public String search(@QueryParam("q") String query, @QueryParam("n") Integer n) throws Exception {
        if (query == null || query.isBlank()) {
            return "[]";
        }
        int k = n == null || n <= 0 ? 10 : Math.min(n, 50);
        float[] vector = embedder.embed(query);

        ObjectNode body = MAPPER.createObjectNode();
        body.put("size", k);
        ArrayNode source = body.putArray("_source");
        for (String f : new String[] { "objectID", "name", "brand", "price", "categories", "image" }) {
            source.add(f);
        }
        ObjectNode knn = body.putObject("knn");
        knn.put("field", "embedding");
        knn.put("k", k);
        knn.put("num_candidates", Math.max(numCandidates, k));
        knn.set("query_vector", MAPPER.valueToTree(vector));

        HttpRequest request = HttpRequest.newBuilder(URI.create(esUrl + "/" + index + "/_search"))
                .header("Content-Type", "application/json")
                .POST(HttpRequest.BodyPublishers.ofString(body.toString()))
                .build();
        HttpResponse<String> res = HTTP.send(request, HttpResponse.BodyHandlers.ofString());
        if (res.statusCode() >= 300) {
            throw new IllegalStateException("search failed: " + res.body());
        }

        ArrayNode out = MAPPER.createArrayNode();
        for (JsonNode hit : MAPPER.readTree(res.body()).path("hits").path("hits")) {
            ObjectNode item = out.addObject();
            item.put("score", hit.path("_score").asDouble());
            hit.path("_source").fields().forEachRemaining(e -> item.set(e.getKey(), e.getValue()));
        }
        return out.toString();
    }
}
