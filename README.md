# Kubernetes Access Monitoring System

Complete RBAC monitoring and analysis system for Kubernetes with Elasticsearch, Prometheus, and Grafana integration.

## Overview

This system monitors Kubernetes RBAC permissions for specified users, collects access data every 5 minutes, stores it in Elasticsearch, and provides visualization through Grafana dashboards. It also exposes Prometheus metrics for sensitive access monitoring.

### Components

- **Main Application**: Collects RBAC data from Kubernetes API every 5 minutes
- **Sidecar Container**: Processes logs and sends to Elasticsearch
- **Metrics Exporter**: Exposes Prometheus metrics for security monitoring
- **Grafana Dashboards**: Auto-provisioned dashboards for visualization

## Prerequisites

- Docker (for building images)
- kubectl (configured to access your cluster)
- Helm 3.0+
- Kind (optional, for local testing)

## Quick Start

### Step 1: Create Kind Cluster (for local testing)

```bash
# Create a new Kind cluster
kind create cluster --name k8s-access-monitor

# Or use existing cluster
kubectl config use-context kind-k8s-access-monitor
```

### Step 2: Build Docker Images

```bash
# Build all three images
docker build -f Dockerfile -t k8s-access-monitor:latest .
docker build -f Dockerfile.sidecar -t k8s-access-monitor-sidecar:latest .
docker build -f Dockerfile.metrics -t k8s-access-monitor-metrics:latest .

# Load images into Kind cluster
kind load docker-image k8s-access-monitor:latest --name k8s-access-monitor
kind load docker-image k8s-access-monitor-sidecar:latest --name k8s-access-monitor
kind load docker-image k8s-access-monitor-metrics:latest --name k8s-access-monitor
```

### Step 3: Deploy Infrastructure

```bash
# Create namespaces
kubectl create namespace monitoring
kubectl create namespace k8s-access-monitor

# Deploy Elasticsearch
kubectl apply -f - <<EOF
apiVersion: apps/v1
kind: Deployment
metadata:
  name: elasticsearch
  namespace: monitoring
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
        image: docker.elastic.co/elasticsearch/elasticsearch:7.10.0
        ports:
        - containerPort: 9200
        env:
        - name: discovery.type
          value: single-node
        - name: "ES_JAVA_OPTS"
          value: "-Xms512m -Xmx512m"
        resources:
          limits:
            memory: 1Gi
            cpu: 500m
---
apiVersion: v1
kind: Service
metadata:
  name: elasticsearch
  namespace: monitoring
spec:
  ports:
  - port: 9200
    targetPort: 9200
  selector:
    app: elasticsearch
EOF

# Wait for Elasticsearch to be ready
kubectl wait --for=condition=ready pod -l app=elasticsearch -n monitoring --timeout=120s
```

### Step 4: Deploy Prometheus

```bash
kubectl apply -f - <<EOF
apiVersion: apps/v1
kind: Deployment
metadata:
  name: prometheus
  namespace: monitoring
spec:
  replicas: 1
  selector:
    matchLabels:
      app: prometheus
  template:
    metadata:
      labels:
        app: prometheus
    spec:
      containers:
      - name: prometheus
        image: prom/prometheus:v2.35.0
        ports:
        - containerPort: 9090
        args:
        - "--config.file=/etc/prometheus/prometheus.yml"
        - "--storage.tsdb.path=/prometheus/"
        - "--web.console.libraries=/etc/prometheus/console_libraries"
        - "--web.console.templates=/etc/prometheus/consoles"
        - "--storage.tsdb.retention.time=200h"
        - "--web.enable-lifecycle"
        volumeMounts:
        - name: prometheus-config
          mountPath: /etc/prometheus/
        - name: prometheus-storage
          mountPath: /prometheus/
      volumes:
      - name: prometheus-config
        configMap:
          name: prometheus-config
      - name: prometheus-storage
        emptyDir: {}
---
apiVersion: v1
kind: Service
metadata:
  name: prometheus
  namespace: monitoring
spec:
  ports:
  - port: 9090
    targetPort: 9090
  selector:
    app: prometheus
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: prometheus-config
  namespace: monitoring
data:
  prometheus.yml: |
    global:
      scrape_interval: 15s
      evaluation_interval: 15s
    scrape_configs:
    - job_name: 'prometheus'
      static_configs:
      - targets: ['localhost:9090']
    - job_name: 'k8s-access-monitor'
      static_configs:
      - targets: ['k8s-access-monitor-metrics.k8s-access-monitor.svc.cluster.local:8000']
      scrape_interval: 15s
EOF

# Wait for Prometheus
kubectl wait --for=condition=ready pod -l app=prometheus -n monitoring --timeout=120s
```

### Step 5: Deploy Grafana with Auto-Provisioning

```bash
# Create Grafana admin secret
kubectl create secret generic grafana-admin \
  --from-literal=password=admin \
  -n monitoring

# Create dashboard provisioning config
kubectl apply -f - <<EOF
apiVersion: v1
kind: ConfigMap
metadata:
  name: grafana-dashboard-provisioning
  namespace: monitoring
data:
  dashboards.yaml: |
    apiVersion: 1
    providers:
    - name: 'default'
      orgId: 1
      folder: ''
      type: file
      disableDeletion: false
      updateIntervalSeconds: 10
      allowUiUpdates: true
      options:
        path: /etc/grafana/provisioning/dashboards
        foldersFromFilesStructure: true
EOF

# Create dashboard ConfigMap
kubectl create configmap grafana-dashboards \
  --from-file=elasticsearch-access-dashboard.json=dashboards/elasticsearch-access-dashboard-unwrapped.json \
  --from-file=prometheus-security-dashboard.json=dashboards/prometheus-security-dashboard-unwrapped.json \
  -n monitoring

# Create datasource provisioning
kubectl apply -f - <<EOF
apiVersion: v1
kind: ConfigMap
metadata:
  name: grafana-datasource-provisioning
  namespace: monitoring
data:
  datasources.yaml: |
    apiVersion: 1
    datasources:
    - name: Elasticsearch
      type: elasticsearch
      access: proxy
      url: http://elasticsearch.monitoring.svc.cluster.local:9200
      database: "k8s-access-logs"
      jsonData:
        index: "k8s-access-logs"
        timeField: "@timestamp"
        esVersion: "7.0.0"
    - name: Prometheus
      type: prometheus
      access: proxy
      url: http://prometheus.monitoring.svc.cluster.local:9090
      isDefault: true
      jsonData:
        timeInterval: "15s"
EOF

# Deploy Grafana
kubectl apply -f - <<EOF
apiVersion: apps/v1
kind: Deployment
metadata:
  name: grafana
  namespace: monitoring
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
        image: grafana/grafana:8.5.0
        ports:
        - containerPort: 3000
        env:
        - name: GF_SECURITY_ADMIN_PASSWORD
          valueFrom:
            secretKeyRef:
              name: grafana-admin
              key: password
        - name: GF_USERS_ALLOW_SIGN_UP
          value: "false"
        volumeMounts:
        - name: grafana-storage
          mountPath: /var/lib/grafana
        - name: dashboard-provisioning
          mountPath: /etc/grafana/provisioning/dashboards
        - name: dashboards
          mountPath: /etc/grafana/provisioning/dashboards/default
        - name: datasource-provisioning
          mountPath: /etc/grafana/provisioning/datasources
      volumes:
      - name: grafana-storage
        emptyDir: {}
      - name: dashboard-provisioning
        configMap:
          name: grafana-dashboard-provisioning
      - name: dashboards
        configMap:
          name: grafana-dashboards
      - name: datasource-provisioning
        configMap:
          name: grafana-datasource-provisioning
---
apiVersion: v1
kind: Service
metadata:
  name: grafana
  namespace: monitoring
spec:
  ports:
  - port: 3000
    targetPort: 3000
  selector:
    app: grafana
EOF

# Wait for Grafana
kubectl wait --for=condition=ready pod -l app=grafana -n monitoring --timeout=120s
```

### Step 6: Deploy Application

```bash
# Install via Helm
cd helm/k8s-access-monitor
helm install k8s-access-monitor . \
  --namespace k8s-access-monitor \
  --create-namespace

# Update ConfigMap with full user list
cd ../..
kubectl create configmap k8s-access-monitor-config \
  --from-file=input.json=input.json \
  -n k8s-access-monitor \
  --dry-run=client -o yaml | kubectl apply -f -

# Restart deployment to pick up new ConfigMap
kubectl rollout restart deployment/k8s-access-monitor -n k8s-access-monitor

# Wait for deployment to be ready
kubectl wait --for=condition=ready pod -l app.kubernetes.io/name=k8s-access-monitor -n k8s-access-monitor --timeout=120s
```

## Access Dashboards

```bash
# Port forward to Grafana
kubectl port-forward svc/grafana -n monitoring 3000:3000

# Open http://localhost:3000 in browser
# Login: admin / admin
# Dashboards:
#   - Kubernetes Security Monitoring - Prometheus (✅ Working)
#   - Kubernetes Access Monitoring - Elasticsearch (⚠️ Has errors - panels show "TypeError: e.split is not a function")
```

**Note**: The Elasticsearch dashboard has compatibility issues with Grafana 8.5.0 Elasticsearch plugin. The Prometheus dashboard works correctly. The Elasticsearch dashboard may need manual panel configuration in Grafana UI.

## Architecture

```
┌─────────────────┐    ┌─────────────────┐    ┌─────────────────┐
│   CronJob       │    │   Deployment    │    │   Prometheus    │
│                 │    │                 │    │                 │
│ • Main App      │    │ • Sidecar       │    │ • Metrics       │
│ • Collects RBAC │    │ • Log Processor │    │ • Security      │
│ • Runs every 5m │    │ • Elasticsearch │    │ • Alerts        │
└─────────────────┘    └─────────────────┘    └─────────────────┘
         │                       │                       │
         └───────────────────────┼───────────────────────┘
                                 │
                    ┌─────────────────┐
                    │   Grafana       │
                    │                 │
                    │ • Access Dash   │
                    │ • Security Dash │
                    │ • Auto-imported │
                    └─────────────────┘
```

## Metrics

Two Prometheus metrics are exposed:

1. **k8s_namespace_sensitive_access_users_count**
   - Labels: `namespace`, `verb`, `resource`
   - Example: `k8s_namespace_sensitive_access_users_count{namespace="kube-system", verb="create", resource="pods"} 4`

2. **k8s_cluster_wide_sensitive_access_users_count**
   - Labels: `resource`, `verb`
   - Example: `k8s_cluster_wide_sensitive_access_users_count{resource="secrets", verb="delete"} 2`
