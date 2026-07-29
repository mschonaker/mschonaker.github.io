#!/usr/bin/env bash
set -euo pipefail

NAMESPACE="${1:-default}"

echo "=== Cleanup ==="

echo "Removing Pipe..."
kubectl delete pipe movies-actors-to-es -n "$NAMESPACE" 2>/dev/null || true

echo "Removing Kamelet..."
kubectl delete kamelet movies-actors-source -n "$NAMESPACE" 2>/dev/null || true

echo "Removing deployments..."
kubectl delete -n "$NAMESPACE" -f "$(dirname "$0")/k8s/h2-movies.yaml" 2>/dev/null || true
kubectl delete -n "$NAMESPACE" -f "$(dirname "$0")/k8s/h2-actors.yaml" 2>/dev/null || true
kubectl delete -n "$NAMESPACE" -f "$(dirname "$0")/k8s/elasticsearch.yaml" 2>/dev/null || true

echo "Removing ConfigMaps..."
kubectl delete configmap movies-init-sql -n "$NAMESPACE" 2>/dev/null || true
kubectl delete configmap actors-init-sql -n "$NAMESPACE" 2>/dev/null || true

echo "Removing IntegrationPlatform..."
kubectl delete integrationplatform camel-k -n camel-k 2>/dev/null || true

echo "Removing Camel K operator..."
kubectl delete -k github.com/apache/camel-k/install/overlays/all-namespaces?ref=v2.10.1 --server-side 2>/dev/null || true
kubectl delete namespace camel-k --ignore-not-found 2>/dev/null || true

echo "Stopping Minikube..."
minikube stop 2>/dev/null || true

echo "=== Cleanup complete ==="