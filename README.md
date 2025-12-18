# Kubernetes Access Monitoring System

Complete RBAC monitoring and analysis system for Kubernetes with Elasticsearch, Prometheus, and Grafana integration.

## Quick Start

### Prerequisites
- Kubernetes cluster (or Kind for local testing)
- kubectl configured
- Docker
- Helm 3.0+

### 1. Build Docker Images

```bash
# Build all images
docker build -f Dockerfile -t k8s-access-monitor:latest .
docker build -f Dockerfile.sidecar -t k8s-access-monitor-sidecar:latest .
docker build -f Dockerfile.metrics -t k8s-access-monitor-metrics:latest .

# If using Kind, load images
kind load docker-image k8s-access-monitor:latest --name <cluster-name>
kind load docker-image k8s-access-monitor-sidecar:latest --name <cluster-name>
kind load docker-image k8s-access-monitor-metrics:latest --name <cluster-name>
```

### 2. Deploy Infrastructure

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

# Deploy Prometheus
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

# Create Grafana secret
kubectl create secret generic grafana-admin \
  --from-literal=password=admin \
  -n monitoring
```

### 3. Deploy Application

```bash
# Install via Helm
cd helm/k8s-access-monitor
helm install k8s-access-monitor . \
  --namespace k8s-access-monitor \
  --create-namespace

# Update ConfigMap with full user list
kubectl create configmap k8s-access-monitor-config \
  --from-file=input.json=../../input.json \
  -n k8s-access-monitor \
  --dry-run=client -o yaml | kubectl apply -f -
```

### 4. Verify Deployment

```bash
# Check pods
kubectl get pods -n k8s-access-monitor
kubectl get pods -n monitoring

# Check CronJob
kubectl get cronjob -n k8s-access-monitor

# Manually trigger collection
kubectl create job test-run --from=cronjob/k8s-access-monitor-collector -n k8s-access-monitor
kubectl logs job/test-run -n k8s-access-monitor

# Check metrics
kubectl port-forward svc/k8s-access-monitor-metrics -n k8s-access-monitor 8000:8000
curl http://localhost:8000/metrics
```

### 5. Access Dashboards

```bash
# Grafana
kubectl port-forward svc/grafana -n monitoring 3000:3000
# Open http://localhost:3000
# Username: admin, Password: admin

# Prometheus
kubectl port-forward svc/prometheus -n monitoring 9090:9090
# Open http://localhost:9090

# Elasticsearch
kubectl port-forward svc/elasticsearch -n monitoring 9200:9200
curl http://localhost:9200/_cluster/health
```

## Configuration

### Update User List

Edit `input.json` and update the ConfigMap:

```bash
kubectl create configmap k8s-access-monitor-config \
  --from-file=input.json=input.json \
  -n k8s-access-monitor \
  --dry-run=client -o yaml | kubectl apply -f -
```

### Customize Helm Values

Edit `helm/k8s-access-monitor/values.yaml`:

```yaml
mainApp:
  schedule: "*/5 * * * *"  # Collection frequency

sidecar:
  elasticsearch:
    url: "http://elasticsearch.monitoring.svc.cluster.local:9200"
    index: "k8s-access-logs"
```

Then upgrade:

```bash
helm upgrade k8s-access-monitor ./helm/k8s-access-monitor -n k8s-access-monitor
```

## Architecture

- **CronJob**: Runs every 5 minutes, collects RBAC data, writes to file and stdout, sends to Elasticsearch
- **Deployment**: 
  - **Sidecar**: Processes logs and sends to Elasticsearch
  - **Metrics Exporter**: Exposes Prometheus metrics on port 8000
- **Monitoring Stack**: Elasticsearch, Prometheus, Grafana

## Metrics

Two Prometheus metrics are exposed:

1. `k8s_namespace_sensitive_access_users_count{namespace, verb, resource}` - Users with sensitive namespace access
2. `k8s_cluster_wide_sensitive_access_users_count{resource, verb}` - Users with cluster-wide sensitive access

## Security

All secrets are managed via Kubernetes Secrets:
- Application secrets: `k8s-access-monitor-app`
- Grafana admin: `grafana-admin`
- Elasticsearch credentials: `elasticsearch-creds`

**⚠️ Production**: Replace dummy secrets with real values from Vault/AWS Secrets Manager.

## Troubleshooting

```bash
# Check logs
kubectl logs -n k8s-access-monitor deployment/k8s-access-monitor -c sidecar
kubectl logs -n k8s-access-monitor deployment/k8s-access-monitor -c metrics-exporter

# Check RBAC
kubectl auth can-i list clusterroles \
  --as=system:serviceaccount:k8s-access-monitor:k8s-access-monitor-sa

# Test Elasticsearch connection
kubectl run test-es --image=curlimages/curl --rm -it --restart=Never \
  -- curl elasticsearch.monitoring.svc.cluster.local:9200
```

## Project Structure

```
├── src/
│   ├── main.py              # RBAC collection app
│   ├── sidecar.py          # Log processor
│   └── metrics_exporter.py # Prometheus metrics
├── helm/k8s-access-monitor/ # Helm chart
├── dashboards/             # Grafana dashboards
├── input.json              # User configuration
└── README.md
```

## License

MIT
