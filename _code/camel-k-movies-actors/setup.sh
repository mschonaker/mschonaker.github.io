#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
NAMESPACE="${1:-default}"

echo "=== Kamelets Movies-Actors Demo Setup ==="
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

# Point Docker to Minikube's daemon for image builds
eval "$(minikube docker-env)"
echo "Docker pointing to Minikube daemon."
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
  echo "Waiting for operator to be ready..."
  kubectl wait --for=condition=Available deployment/camel-k-operator -n camel-k --timeout=180s
else
  echo "Camel K operator already installed."
fi
echo ""

# --------------------------------------------------
# Step 3: Configure IntegrationPlatform
# --------------------------------------------------
echo "=== Step 3: Configure IntegrationPlatform ==="
# Get registry cluster IP
REGISTRY_IP=$(kubectl -n kube-system get service registry -o jsonpath='{.spec.clusterIP}')
echo "Registry IP: $REGISTRY_IP"

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
kubectl create configmap movies-init-sql \
  --namespace "$NAMESPACE" \
  --from-file="$SCRIPT_DIR/data/movies.sql" \
  --dry-run=client -o yaml | kubectl apply -f -

kubectl create configmap actors-init-sql \
  --namespace "$NAMESPACE" \
  --from-file="$SCRIPT_DIR/data/actors.sql" \
  --dry-run=client -o yaml | kubectl apply -f -
echo ""

# --------------------------------------------------
# Step 5: Build and push H2 Docker image
# --------------------------------------------------
echo "=== Step 5: Build H2 Docker images ==="
# Build movies image
docker build -t h2-movies:latest -f "$SCRIPT_DIR/Dockerfile" "$SCRIPT_DIR"
docker build -t h2-actors:latest -f "$SCRIPT_DIR/Dockerfile" "$SCRIPT_DIR"

# Tag for Minikube registry
docker tag h2-movies:latest "$REGISTRY_IP:5000/h2-movies:latest"
docker tag h2-actors:latest "$REGISTRY_IP:5000/h2-actors:latest"

# Push to Minikube registry (if available)
docker push "$REGISTRY_IP:5000/h2-movies:latest" 2>/dev/null || echo "Note: Push skipped — using local images via imagePullPolicy=IfNotPresent"
docker push "$REGISTRY_IP:5000/h2-actors:latest" 2>/dev/null || echo "Note: Push skipped — using local images via imagePullPolicy=IfNotPresent"
echo ""

# --------------------------------------------------
# Step 6: Deploy pre-existing infrastructure
#         (ES cluster + ES sink Kamelet — deployed
#          once, shared across pipelines)
# --------------------------------------------------
echo "=== Step 6: Deploy pre-existing infrastructure ==="
kubectl apply -n "$NAMESPACE" -f "$SCRIPT_DIR/k8s/elasticsearch.yaml"
echo "Waiting for Elasticsearch..."
kubectl wait --for=condition=Available deployment/elasticsearch -n "$NAMESPACE" --timeout=180s

# Apply the cleaned ES sink Kamelet (infrastructure, not pipeline)
kubectl apply -n "$NAMESPACE" -f "$SCRIPT_DIR/kamelets/elasticsearch-index-sink.kamelet.yaml"
echo "Elasticsearch sink Kamelet applied (infrastructure)."
echo ""

# --------------------------------------------------
# Step 7: Deploy pipeline databases (H2)
# --------------------------------------------------
echo "=== Step 7: Deploy pipeline databases ==="
kubectl apply -n "$NAMESPACE" -f "$SCRIPT_DIR/k8s/h2-movies.yaml"
kubectl apply -n "$NAMESPACE" -f "$SCRIPT_DIR/k8s/h2-actors.yaml"

echo "Waiting for H2 movies..."
kubectl wait --for=condition=Available deployment/h2-movies -n "$NAMESPACE" --timeout=120s
echo "Waiting for H2 actors..."
kubectl wait --for=condition=Available deployment/h2-actors -n "$NAMESPACE" --timeout=120s
echo ""

# --------------------------------------------------
# Step 8: Apply pipeline Kamelets and Pipe
# --------------------------------------------------
echo "=== Step 8: Apply pipeline Kamelets and Pipe ==="
kubectl apply -n "$NAMESPACE" -f "$SCRIPT_DIR/kamelets/movies-source.kamelet.yaml"
kubectl apply -n "$NAMESPACE" -f "$SCRIPT_DIR/kamelets/groovy-join.kamelet.yaml"
kubectl apply -n "$NAMESPACE" -f "$SCRIPT_DIR/pipes/movies-actors-pipe.yaml"
echo ""

# --------------------------------------------------
# Step 9: Wait for Pipe to be ready
# --------------------------------------------------
echo "=== Step 9: Wait for Pipe/Integration ==="
echo "Waiting for Pipe to be ready..."
kubectl wait --for=jsonpath='{.status.phase}'=Ready pipe/movies-actors-to-es -n "$NAMESPACE" --timeout=300s 2>/dev/null || true
echo ""

# --------------------------------------------------
# Step 10: Verify
# --------------------------------------------------
echo "=== Step 10: Verify ==="
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
sleep 10
kubectl exec deploy/elasticsearch -n "$NAMESPACE" -- curl -s http://localhost:9200/_cat/indices 2>/dev/null || echo "ES not ready yet, check later."
echo ""
echo "=== Setup complete! ==="
echo "To check data in Elasticsearch:"
echo "  kubectl exec deploy/elasticsearch -n $NAMESPACE -- curl -s 'http://localhost:9200/movies-actors-joined/_search?pretty'"
echo "To view integration logs:"
echo "  kubectl logs -l camel.apache.org/integration=movies-actors-to-es -n $NAMESPACE"
