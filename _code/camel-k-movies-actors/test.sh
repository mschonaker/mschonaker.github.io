#!/usr/bin/env bash
set -euo pipefail

NAMESPACE="${1:-default}"

echo "=== Verification ==="
echo ""

echo "Pods:"
kubectl get pods -n "$NAMESPACE"
echo ""

echo "Pipe:"
kubectl get pipe -n "$NAMESPACE"
echo ""

echo "Integration:"
kubectl get integration -n "$NAMESPACE" -o wide
echo ""

echo "Elasticsearch indices:"
kubectl exec deploy/elasticsearch -n "$NAMESPACE" -- curl -s "http://localhost:9200/_cat/indices?v" 2>/dev/null || echo "Could not reach ES"
echo ""

echo "Document count in movies-actors-joined:"
COUNT=$(kubectl exec deploy/elasticsearch -n "$NAMESPACE" -- curl -s "http://localhost:9200/movies-actors-joined/_count" 2>/dev/null | python3 -c "import sys,json; print(json.load(sys.stdin).get('count', 'N/A'))" 2>/dev/null || echo "N/A")
echo "Count: $COUNT"
echo ""

echo "Sample documents:"
kubectl exec deploy/elasticsearch -n "$NAMESPACE" -- curl -s "http://localhost:9200/movies-actors-joined/_search?pretty&size=3" 2>/dev/null || echo "Could not query ES"
echo ""

echo "Integration logs (last 20 lines):"
kubectl logs -l camel.apache.org/integration=movies-actors-to-es -n "$NAMESPACE" --tail=20 2>/dev/null || echo "No integration logs found"
echo ""

echo "=== Verification complete ==="