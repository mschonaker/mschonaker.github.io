#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NAMESPACE="${1:-default}"

echo "=== CDC Kamelets Demo Setup (PostgreSQL + Debezium) ==="
echo "Namespace: $NAMESPACE"
echo ""

# --------------------------------------------------
# Step 1: Start Minikube with registry
# --------------------------------------------------
echo "=== Step 1: Start Minikube ==="
if ! minikube status &>/dev/null; then
  minikube start --cpus 4 --memory 8192 --addons registry
  echo "Minikube started with registry addon."
else
  echo "Minikube already running."
  minikube addons enable registry 2>/dev/null || true
fi
eval "$(minikube docker-env)"
echo ""

# --------------------------------------------------
# Step 2: Install Camel K Operator
# --------------------------------------------------
echo "=== Step 2: Install Camel K Operator ==="
kubectl create namespace camel-k --dry-run=client -o yaml | kubectl apply -f -
INSTALLED=$(kubectl get deployment camel-k-operator -n camel-k --ignore-not-found -o jsonpath='{.metadata.name}' 2>/dev/null)
if [ -z "$INSTALLED" ]; then
  echo "Installing Camel K operator via Kustomize..."
  kubectl apply -k github.com/apache/camel-k/install/overlays/all-namespaces?ref=v2.10.1 --server-side
  kubectl wait --for=condition=Available deployment/camel-k-operator -n camel-k --timeout=180s
else
  echo "Camel K operator already installed."
fi
echo ""

# --------------------------------------------------
# Step 3: Configure IntegrationPlatform
# --------------------------------------------------
echo "=== Step 3: Configure IntegrationPlatform ==="
REGISTRY_IP=$(kubectl -n kube-system get service registry -o jsonpath='{.spec.clusterIP}')
kubectl apply -n camel-k -f - <<EOF
apiVersion: camel.apache.org/v1
kind: IntegrationPlatform
metadata:
  name: camel-k
spec:
  build:
    registry:
      address: "$REGISTRY_IP:5000"
      insecure: true
EOF
echo ""

# --------------------------------------------------
# Step 4: Create ConfigMaps with init SQL
# --------------------------------------------------
echo "=== Step 4: Create ConfigMaps ==="
kubectl create configmap pg-init-sql \
  --namespace "$NAMESPACE" \
  --from-file="$SCRIPT_DIR/data/init-db.sql" \
  --dry-run=client -o yaml | kubectl apply -f -
echo ""

# --------------------------------------------------
# Step 5: Deploy pre-existing infrastructure
#         (ES cluster + ES sink Kamelet)
# --------------------------------------------------
echo "=== Step 5: Deploy pre-existing infrastructure ==="
kubectl apply -n "$NAMESPACE" -f "$SCRIPT_DIR/k8s/elasticsearch.yaml"
echo "Waiting for Elasticsearch..."
kubectl wait --for=condition=Available deployment/elasticsearch -n "$NAMESPACE" --timeout=180s
kubectl apply -n "$NAMESPACE" -f "$SCRIPT_DIR/../camel-k-movies-actors/kamelets/elasticsearch-index-sink.kamelet.yaml"
echo "Elasticsearch sink Kamelet applied (infrastructure)."
echo ""

# --------------------------------------------------
# Step 6: Deploy PostgreSQL with CDC
# --------------------------------------------------
echo "=== Step 6: Deploy PostgreSQL with CDC ==="
kubectl apply -n "$NAMESPACE" -f "$SCRIPT_DIR/k8s/postgres.yaml"
echo "Waiting for PostgreSQL..."
sleep 5
kubectl wait --for=condition=Available deployment/postgres -n "$NAMESPACE" --timeout=120s
echo ""

# --------------------------------------------------
# Step 7: Apply pipeline Kamelets and Pipe
# --------------------------------------------------
echo "=== Step 7: Apply pipeline Kamelets and Pipe ==="
kubectl apply -n "$NAMESPACE" -f "$SCRIPT_DIR/kamelets/movies-cdc-source.kamelet.yaml"
kubectl apply -n "$NAMESPACE" -f "$SCRIPT_DIR/kamelets/groovy-cdc-processor.kamelet.yaml"
kubectl apply -n "$NAMESPACE" -f "$SCRIPT_DIR/pipes/movies-actors-cdc-pipe.yaml"
echo ""

# --------------------------------------------------
# Step 8: Wait for Pipe to be ready
# --------------------------------------------------
echo "=== Step 8: Wait for Pipe/Integration ==="
echo "Waiting for Pipe to be ready..."
kubectl wait --for=jsonpath='{.status.phase}'=Ready pipe/movies-actors-cdc -n "$NAMESPACE" --timeout=300s 2>/dev/null || true
echo ""

# --------------------------------------------------
# Step 9: Verify
# --------------------------------------------------
echo "=== Step 9: Verify ==="
echo ""
echo "Pods:"
kubectl get pods -n "$NAMESPACE"
echo ""
echo "Pipe status:"
kubectl get pipe -n "$NAMESPACE"
echo ""
echo "Integration status:"
kubectl get integration -n "$NAMESPACE"
echo ""
echo "Elasticsearch indices:"
sleep 15
kubectl exec deploy/elasticsearch -n "$NAMESPACE" -- curl -s http://localhost:9200/_cat/indices 2>/dev/null || echo "ES not ready yet, check later."
echo ""
echo "=== Setup complete! ==="
echo "To check data in Elasticsearch:"
echo "  kubectl exec deploy/elasticsearch -n $NAMESPACE -- curl -s 'http://localhost:9200/movies-actors-joined/_search?pretty'"
echo "To view integration logs:"
echo "  kubectl logs -l camel.apache.org/integration=movies-actors-cdc -n $NAMESPACE"
echo ""
echo "To test deletion propagation:"
echo "  kubectl exec deploy/postgres -n $NAMESPACE -- psql -U postgres -d movies_db -c \"DELETE FROM movies WHERE id = 'tt0111161';\""
echo "  # Then check ES — the document should be gone within seconds"
