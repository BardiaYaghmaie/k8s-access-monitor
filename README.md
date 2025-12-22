# Kubernetes Access Monitoring System

RBAC monitoring system for Kubernetes with Prometheus metrics and Elasticsearch logging.

## Overview

Monitors Kubernetes RBAC permissions for specified users every 5 minutes:
- **Collector** (CronJob): Queries K8s API for user access permissions
- **Metrics Exporter**: Exposes Prometheus metrics for sensitive access
- **Sidecar**: Forwards logs to Elasticsearch
- **Dashboards**: Grafana dashboards for visualization

## Project Structure

```
k8s-access-monitor/
├── src/
│   ├── main.py              # Main collector
│   ├── metrics_exporter.py  # Prometheus metrics
│   └── sidecar.py           # Elasticsearch forwarder
├── helm/k8s-access-monitor/ # Helm chart
├── dashboards/              # Grafana dashboards
├── input.json               # User list to monitor
├── Dockerfile*              # Container images
└── test.py                  # Tests
```

## Setup

### 1. Build Images

```bash
docker build -f Dockerfile -t k8s-access-monitor:latest .
docker build -f Dockerfile.sidecar -t k8s-access-monitor-sidecar:latest .
docker build -f Dockerfile.metrics -t k8s-access-monitor-metrics:latest .

# Load into Kind (for local testing)
kind load docker-image k8s-access-monitor:latest k8s-access-monitor-metrics:latest k8s-access-monitor-sidecar:latest --name <cluster-name>
```

### 2. Deploy Elasticsearch

```bash
kubectl apply -f - <<'EOF'
apiVersion: apps/v1
kind: Deployment
metadata:
  name: elasticsearch
spec:
  replicas: 1
  selector:
    matchLabels:
      app: elasticsearch
  template:
    metadata:
      labels:
        app: elasticsearch
    spec:
      containers:
      - name: elasticsearch
        image: docker.elastic.co/elasticsearch/elasticsearch:7.17.0
        ports:
        - containerPort: 9200
        env:
        - name: discovery.type
          value: single-node
        - name: ES_JAVA_OPTS
          value: "-Xms512m -Xmx512m"
        - name: xpack.security.enabled
          value: "false"
---
apiVersion: v1
kind: Service
metadata:
  name: elasticsearch
spec:
  ports:
  - port: 9200
  selector:
    app: elasticsearch
EOF

kubectl wait --for=condition=ready pod -l app=elasticsearch --timeout=120s
```

### 3. Deploy Grafana with Auto-Imported Dashboards

```bash
# Create dashboard ConfigMaps
kubectl create configmap grafana-dashboards-prometheus \
  --from-file=prometheus-security-dashboard.json=dashboards/prometheus-security-dashboard.json

kubectl create configmap grafana-dashboards-elasticsearch \
  --from-file=elasticsearch-access-dashboard.json=dashboards/elasticsearch-access-dashboard.json

# Deploy Grafana
kubectl apply -f - <<'EOF'
apiVersion: v1
kind: ConfigMap
metadata:
  name: grafana-provisioning-datasources
data:
  datasources.yaml: |
    apiVersion: 1
    datasources:
    - name: Prometheus
      type: prometheus
      access: proxy
      url: http://k8s-access-monitor-metrics:8000
      isDefault: true
    - name: Elasticsearch
      type: elasticsearch
      access: proxy
      url: http://elasticsearch:9200
      database: "k8s-access-logs"
      jsonData:
        timeField: "@timestamp"
        esVersion: "7.10.0"
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: grafana-provisioning-dashboards
data:
  dashboards.yaml: |
    apiVersion: 1
    providers:
    - name: 'prometheus'
      folder: 'Kubernetes Security'
      type: file
      options:
        path: /var/lib/grafana/dashboards/prometheus
    - name: 'elasticsearch'
      folder: 'Kubernetes Security'
      type: file
      options:
        path: /var/lib/grafana/dashboards/elasticsearch
---
apiVersion: apps/v1
kind: Deployment
metadata:
  name: grafana
spec:
  replicas: 1
  selector:
    matchLabels:
      app: grafana
  template:
    metadata:
      labels:
        app: grafana
    spec:
      containers:
      - name: grafana
        image: grafana/grafana:10.0.0
        ports:
        - containerPort: 3000
        env:
        - name: GF_SECURITY_ADMIN_PASSWORD
          value: "admin"
        volumeMounts:
        - name: datasources
          mountPath: /etc/grafana/provisioning/datasources
        - name: dashboard-providers
          mountPath: /etc/grafana/provisioning/dashboards
        - name: dashboards-prometheus
          mountPath: /var/lib/grafana/dashboards/prometheus
        - name: dashboards-elasticsearch
          mountPath: /var/lib/grafana/dashboards/elasticsearch
      volumes:
      - name: datasources
        configMap:
          name: grafana-provisioning-datasources
      - name: dashboard-providers
        configMap:
          name: grafana-provisioning-dashboards
      - name: dashboards-prometheus
        configMap:
          name: grafana-dashboards-prometheus
      - name: dashboards-elasticsearch
        configMap:
          name: grafana-dashboards-elasticsearch
---
apiVersion: v1
kind: Service
metadata:
  name: grafana
spec:
  ports:
  - port: 3000
  selector:
    app: grafana
EOF

kubectl wait --for=condition=ready pod -l app=grafana --timeout=120s
```

### 4. Deploy k8s-access-monitor

```bash
helm upgrade --install k8s-access-monitor ./helm/k8s-access-monitor \
  --set-file mainApp.inputConfig=input.json \
  --set metricsExporter.serviceMonitor.enabled=false \
  --set sidecar.elasticsearch.url=http://elasticsearch:9200
```

## Updating User List

1. Edit `input.json` - add/remove users in the `internals` section:

```json
"internals": {
  "user-uuid": {
    "username": "user.name",
    "groups": ["group1", "group2"],
    "first_name": "First",
    "last_name": "Last"
  }
}
```

2. Redeploy:

```bash
helm upgrade k8s-access-monitor ./helm/k8s-access-monitor \
  --set-file mainApp.inputConfig=input.json \
  --set metricsExporter.serviceMonitor.enabled=false
```

## Accessing Dashboards

```bash
kubectl port-forward svc/grafana 3000:3000
```

Open http://localhost:3000
- **Username**: admin
- **Password**: admin

Dashboards are auto-imported in the "Kubernetes Security" folder:
- **Prometheus Security Dashboard** - Security metrics and alerts
- **Elasticsearch Access Dashboard** - User access logs and history
