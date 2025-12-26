# Kubernetes Access Monitoring System

Complete RBAC monitoring system for Kubernetes with Prometheus metrics and Elasticsearch logging.

## Overview

Monitors Kubernetes RBAC permissions for specified users every 5 minutes:
- **Collector** (CronJob): Queries K8s API for user access permissions
- **Metrics Exporter**: Exposes Prometheus metrics for sensitive access
- **Sidecar**: Forwards logs to Elasticsearch
- **Dashboards**: Grafana dashboards for visualization

## Prerequisites

- Kubernetes cluster (tested with kind)
- kubectl configured to access the cluster
- Docker installed
- Helm 3.x installed
- kind (if using local testing)

## Complete Setup Guide

### Step 1: Build Docker Images

```bash
# Build all required images
docker build -f Dockerfile -t k8s-access-monitor:latest .
docker build -f Dockerfile.sidecar -t k8s-access-monitor-sidecar:latest .
docker build -f Dockerfile.metrics -t k8s-access-monitor-metrics:latest .

# Load images into kind cluster (if using kind)
kind load docker-image k8s-access-monitor:latest k8s-access-monitor-metrics:latest k8s-access-monitor-sidecar:latest --name <your-cluster-name>
```

### Step 2: Create Monitoring Namespace

```bash
kubectl create namespace monitoring
```

### Step 3: Deploy Elasticsearch

**If using kind, load Elasticsearch image first:**

```bash
# Load Elasticsearch image into kind cluster (if using kind)
kind load docker-image elasticsearch:9.2.3 --name <your-cluster-name>
```

**Deploy Elasticsearch:**

```bash
kubectl apply -f - <<'EOF'
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
        image: elasticsearch:9.2.3
        imagePullPolicy: IfNotPresent
        ports:
        - containerPort: 9200
        env:
        - name: discovery.type
          value: single-node
        - name: xpack.security.enabled
          value: "false"
        - name: ES_JAVA_OPTS
          value: "-Xms512m -Xmx512m"
        resources:
          requests:
            memory: 1Gi
            cpu: 250m
          limits:
            memory: 2Gi
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

kubectl wait --for=condition=ready pod -l app=elasticsearch -n monitoring --timeout=180s
```

### Step 4: Deploy Prometheus

**If using kind, load Prometheus image first:**

```bash
# Load Prometheus image into kind cluster (if using kind)
docker pull prom/prometheus:latest
kind load docker-image prom/prometheus:latest --name <your-cluster-name>
```

**Deploy Prometheus:**

```bash
kubectl apply -f - <<'EOF'
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
      - job_name: 'k8s-access-monitor-metrics'
        static_configs:
          - targets:
            - 'k8s-access-monitor-metrics.default.svc.cluster.local:8000'
        metrics_path: /metrics
        scheme: http
---
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
        image: prom/prometheus:latest
        ports:
        - containerPort: 9090
          name: http
        volumeMounts:
        - name: config
          mountPath: /etc/prometheus
        args:
          - '--config.file=/etc/prometheus/prometheus.yml'
          - '--storage.tsdb.path=/prometheus'
          - '--storage.tsdb.retention.time=200h'
        resources:
          requests:
            memory: 512Mi
            cpu: 250m
          limits:
            memory: 1Gi
            cpu: 500m
      volumes:
      - name: config
        configMap:
          name: prometheus-config
---
apiVersion: v1
kind: Service
metadata:
  name: prometheus
  namespace: monitoring
spec:
  type: ClusterIP
  ports:
  - port: 9090
    targetPort: 9090
    protocol: TCP
    name: http
  selector:
    app: prometheus
EOF

kubectl wait --for=condition=ready pod -l app=prometheus -n monitoring --timeout=120s
```

### Step 5: Deploy Grafana with Dashboards

```bash
# Create dashboard ConfigMaps (using unwrapped versions)
kubectl create configmap grafana-dashboards-prometheus \
  --from-file=prometheus-security-dashboard.json=dashboards/prometheus-security-dashboard-unwrapped.json \
  -n monitoring

kubectl create configmap grafana-dashboards-elasticsearch \
  --from-file=elasticsearch-access-dashboard.json=dashboards/elasticsearch-access-dashboard-unwrapped.json \
  -n monitoring

# Deploy Grafana
kubectl apply -f - <<'EOF'
apiVersion: v1
kind: ConfigMap
metadata:
  name: grafana-provisioning-datasources
  namespace: monitoring
data:
  datasources.yaml: |
    apiVersion: 1
    datasources:
    - name: Prometheus
      type: prometheus
      access: proxy
      url: http://prometheus.monitoring.svc.cluster.local:9090
      uid: prometheus-uid
      isDefault: true
      jsonData:
        httpMethod: GET
        timeInterval: 15s
    - name: Elasticsearch
      type: elasticsearch
      access: proxy
      url: http://elasticsearch.monitoring.svc.cluster.local:9200
      uid: P31C819B24CF3C3C7
      database: "k8s-access-logs"
      jsonData:
        timeField: "@timestamp"
        esVersion: "9.0.0"
        index: "k8s-access-logs"
        logMessageField: "username"
        logLevelField: "access_count"
---
apiVersion: v1
kind: ConfigMap
metadata:
  name: grafana-provisioning-dashboards
  namespace: monitoring
data:
  dashboards.yaml: |
    apiVersion: 1
    providers:
    - name: 'prometheus'
      orgId: 1
      folder: 'Kubernetes Security'
      type: file
      disableDeletion: false
      updateIntervalSeconds: 10
      allowUiUpdates: true
      options:
        path: /var/lib/grafana/dashboards/prometheus
    - name: 'elasticsearch'
      orgId: 1
      folder: 'Kubernetes Security'
      type: file
      disableDeletion: false
      updateIntervalSeconds: 10
      allowUiUpdates: true
      options:
        path: /var/lib/grafana/dashboards/elasticsearch
---
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
        image: grafana/grafana:10.0.0
        ports:
        - containerPort: 3000
          name: http
        env:
        - name: GF_SECURITY_ADMIN_USER
          value: "admin"
        - name: GF_SECURITY_ADMIN_PASSWORD
          value: "admin"
        - name: GF_SERVER_ROOT_URL
          value: "/"
        volumeMounts:
        - name: datasources
          mountPath: /etc/grafana/provisioning/datasources
        - name: dashboard-providers
          mountPath: /etc/grafana/provisioning/dashboards
        - name: dashboards-prometheus
          mountPath: /var/lib/grafana/dashboards/prometheus
        - name: dashboards-elasticsearch
          mountPath: /var/lib/grafana/dashboards/elasticsearch
        resources:
          requests:
            memory: 256Mi
            cpu: 100m
          limits:
            memory: 512Mi
            cpu: 500m
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
  namespace: monitoring
spec:
  type: ClusterIP
  ports:
  - port: 3000
    targetPort: 3000
    protocol: TCP
    name: http
  selector:
    app: grafana
EOF

kubectl wait --for=condition=ready pod -l app=grafana -n monitoring --timeout=120s
```

### Step 6: Deploy k8s-access-monitor Application

```bash
# Deploy using Helm
helm upgrade --install k8s-access-monitor ./helm/k8s-access-monitor \
  --namespace default \
  --create-namespace \
  --set-file mainApp.inputConfig=input.json \
  --set metricsExporter.serviceMonitor.enabled=false \
  --set sidecar.enabled=true \
  --set sidecar.elasticsearch.url=http://elasticsearch.monitoring.svc.cluster.local:9200

# Wait for deployment to be ready
kubectl wait --for=condition=ready pod -l app.kubernetes.io/name=k8s-access-monitor -n default --timeout=120s
```

### Step 7: Verify Deployment

```bash
# Check all pods are running
kubectl get pods -n monitoring
kubectl get pods -n default -l app.kubernetes.io/name=k8s-access-monitor

# Check services
kubectl get svc -n monitoring
kubectl get svc -n default | grep k8s-access-monitor

# Check CronJob
kubectl get cronjob -n default
```

## Accessing Dashboards

### Port Forward to Grafana

```bash
kubectl port-forward -n monitoring svc/grafana 3000:3000
```

### Login to Grafana

Open http://localhost:3000 in your browser:
- **Username**: `admin`
- **Password**: `admin`

### Available Dashboards

Dashboards are auto-imported in the **"Kubernetes Security"** folder:

1. **Kubernetes Security Monitoring - Prometheus**
   - Security metrics and alerts
   - Sensitive namespace access tracking
   - Cluster-wide access monitoring

2. **Kubernetes Access Monitoring - Elasticsearch**
   - User access logs and history
   - Filterable by username, resource, and verb
   - Access timeline visualization

## Managing User List

The system monitors users defined in `input.json`. You can add, modify, or remove users at any time.

### Method 1: Update via ConfigMap (Recommended for Quick Changes)

1. **Edit `input.json`** - Add/remove users in the `internals` section:

```json
{
  "metadata": {
    "timestamp": "2025-12-10T15:00:00Z",
    "version": "v1"
  },
  "data": [
    {
      "configs": [
        {
          "id": "your-config-id",
          "data": "base64-encoded-config-data"
        }
      ],
      "internals": {
        "user-uuid-here": {
          "source": "config-id",
          "username": "user.name",
          "groups": ["group1", "group2"],
          "first_name": "First",
          "last_name": "Last"
        }
      }
    }
  ]
}
```

2. **Update the ConfigMap** with new user data:

```bash
kubectl create configmap k8s-access-monitor-config \
  --from-file=input.json=input.json \
  --dry-run=client -o yaml | kubectl apply -f - -n default
```

3. **Restart the deployment** to pick up changes:

```bash
kubectl rollout restart deployment/k8s-access-monitor -n default
```

4. **Wait for pods to be ready** and verify:

```bash
kubectl wait --for=condition=ready pod -l app.kubernetes.io/name=k8s-access-monitor -n default --timeout=120s

# Check logs to verify users are loaded
kubectl logs -n default deployment/k8s-access-monitor -c metrics-exporter --tail=20 | grep "Loaded"
```

### Method 2: Update via Helm (Recommended for Production)

This method automatically updates the ConfigMap and restarts pods:

```bash
helm upgrade k8s-access-monitor ./helm/k8s-access-monitor \
  --namespace default \
  --set-file mainApp.inputConfig=input.json \
  --set metricsExporter.serviceMonitor.enabled=false \
  --set sidecar.enabled=true \
  --set sidecar.elasticsearch.url=http://elasticsearch.monitoring.svc.cluster.local:9200
```

### Verifying User List Changes

After updating, verify the changes:

```bash
# Check metrics exporter loaded users
kubectl logs -n default deployment/k8s-access-monitor -c metrics-exporter --tail=5 | grep "Loaded"

# Trigger a manual collection to test
kubectl create job --from=cronjob/k8s-access-monitor-collector test-$(date +%s) -n default

# Check the job logs to see if new users are processed
kubectl logs -l job-name -n default --tail=50 | grep "username"
```

**Note:** The CronJob will automatically collect access data for all users in the updated list on its next scheduled run (every 5 minutes).

## Testing the System

### Deploy Test RBAC Resources (Optional)

To generate test data for dashboards and verify the system is working, you can deploy test RBAC resources:

```bash
# Deploy test RBAC bindings that match users in input.json
kubectl apply -f test-rbac.yaml
```

This creates:
- ClusterRoles and ClusterRoleBindings for groups (sre-production, cluster-readonly)
- Roles and RoleBindings for namespace-specific access (dev, qa, devops groups)
- Direct user bindings for testing

**Note:** This is optional and only needed for testing. In production, your cluster will have its own RBAC bindings that will be automatically detected.

### Generate Data for Alert Panels (Pod Exec, Node Delete)

To test the alert panels in the Prometheus dashboard (Pod Execution Access Alert, Node Access Alert), you can create additional test bindings:

```bash
kubectl apply -f - <<'EOF'
# Test ClusterRole with pod exec access
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: test-pod-exec-role
rules:
  - apiGroups: [""]
    resources: ["pods", "pods/exec"]
    verbs: ["get", "list", "watch", "exec"]
---
# Test ClusterRoleBinding for pod exec
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: test-pod-exec-binding
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: test-pod-exec-role
subjects:
  - kind: User
    name: mohammad.jafari
    apiGroup: rbac.authorization.k8s.io
---
# Test ClusterRole with node delete access
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRole
metadata:
  name: test-node-delete-role
rules:
  - apiGroups: [""]
    resources: ["nodes"]
    verbs: ["get", "list", "watch", "delete", "patch"]
---
# Test ClusterRoleBinding for node delete
apiVersion: rbac.authorization.k8s.io/v1
kind: ClusterRoleBinding
metadata:
  name: test-node-delete-binding
roleRef:
  apiGroup: rbac.authorization.k8s.io
  kind: ClusterRole
  name: test-node-delete-role
subjects:
  - kind: User
    name: ali.ahmadi
    apiGroup: rbac.authorization.k8s.io
EOF
```

After deploying, wait 15-30 seconds for metrics to be recalculated, then refresh the Grafana dashboard. The alert panels should now show data:
- **Pod Execution Access Alert**: Should show 1
- **Node Access Alert**: Should show 1

### Trigger Manual Collection

To test immediately without waiting for the CronJob schedule:

```bash
# Create a manual job from the CronJob
kubectl create job --from=cronjob/k8s-access-monitor-collector manual-test-$(date +%s) -n default

# Check the job logs
kubectl logs -l job-name --tail=50 -n default
```

### Verify Metrics

```bash
# Port forward to metrics service
kubectl port-forward -n default svc/k8s-access-monitor-metrics 8000:8000

# Check metrics in another terminal
curl http://localhost:8000/metrics | grep k8s_
```

**Expected output:** You should see metrics like:
- `k8s_namespace_sensitive_access_users_count{namespace="default",verb="get",resource="pods"} 8`
- `k8s_cluster_wide_sensitive_access_users_count{resource="pods",verb="exec"} 1`

### Verify Elasticsearch

```bash
# Check documents in Elasticsearch
kubectl exec -n monitoring deployment/elasticsearch -- curl -s "http://localhost:9200/k8s-access-logs/_count"
```

**Expected output:** Should show document count > 0 after RBAC resources are deployed and collection runs.

## Project Structure

```
hamravesh-task/
├── src/
│   ├── main.py              # Main collector (CronJob)
│   ├── metrics_exporter.py  # Prometheus metrics exporter
│   └── sidecar.py           # Elasticsearch log forwarder
├── helm/k8s-access-monitor/ # Helm chart for deployment
├── dashboards/              # Grafana dashboards
│   ├── prometheus-security-dashboard-unwrapped.json
│   └── elasticsearch-access-dashboard-unwrapped.json
├── input.json               # User list to monitor
├── test-rbac.yaml           # Test RBAC resources for demo/testing
├── Dockerfile               # Main collector image
├── Dockerfile.metrics       # Metrics exporter image
├── Dockerfile.sidecar       # Sidecar image
└── README.md                # This file
```
