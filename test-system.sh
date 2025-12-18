#!/bin/bash
set -e

echo "🧪 Testing Kubernetes Access Monitoring System"
echo "================================================"

echo ""
echo "1. Checking Pods..."
kubectl get pods -n k8s-access-monitor
kubectl get pods -n monitoring

echo ""
echo "2. Checking Services..."
kubectl get svc -n k8s-access-monitor
kubectl get svc -n monitoring

echo ""
echo "3. Checking CronJob..."
kubectl get cronjob -n k8s-access-monitor

echo ""
echo "4. Testing Metrics Exporter..."
kubectl logs -n k8s-access-monitor deployment/k8s-access-monitor -c metrics-exporter --tail=3

echo ""
echo "5. Testing Data Collection..."
kubectl delete job test-collection -n k8s-access-monitor 2>/dev/null || true
kubectl create job test-collection --from=cronjob/k8s-access-monitor-collector -n k8s-access-monitor
sleep 10
echo "Collection logs:"
kubectl logs job/test-collection -n k8s-access-monitor 2>&1 | tail -5

echo ""
echo "6. Checking Prometheus Targets..."
kubectl port-forward svc/prometheus -n monitoring 9090:9090 > /dev/null 2>&1 &
PF_PID=$!
sleep 3
curl -s http://localhost:9090/api/v1/targets 2>/dev/null | jq -r '.data.activeTargets[] | select(.labels.job=="k8s-access-monitor") | "\(.labels.job): \(.health) - \(.lastError // "OK")"' || echo "Prometheus not accessible"
kill $PF_PID 2>/dev/null || true

echo ""
echo "7. Checking Elasticsearch..."
kubectl port-forward svc/elasticsearch -n monitoring 9200:9200 > /dev/null 2>&1 &
ES_PID=$!
sleep 3
curl -s http://localhost:9200/_cluster/health 2>/dev/null | jq -r '.status' || echo "Elasticsearch not accessible"
kill $ES_PID 2>/dev/null || true

echo ""
echo "8. Checking Grafana..."
kubectl get pods -n monitoring | grep grafana | grep Running && echo "✅ Grafana is running" || echo "❌ Grafana not running"

echo ""
echo "✅ Testing complete!"
echo ""
echo "To access services:"
echo "  Grafana:    kubectl port-forward svc/grafana -n monitoring 3000:3000"
echo "  Prometheus: kubectl port-forward svc/prometheus -n monitoring 9090:9090"
echo "  Elasticsearch: kubectl port-forward svc/elasticsearch -n monitoring 9200:9200"

