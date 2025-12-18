# Kubernetes Access Monitoring and Analysis System

سیستم پایش و تحلیل دسترسی‌های RBAC در Kubernetes برای ارزیابی امنیت و کنترل دسترسی کاربران.

## نمای کلی

این سیستم یک راهکار کامل برای مانیتورینگ دسترسی‌های کاربران در Kubernetes ارائه می‌دهد که شامل جمع‌آوری، پردازش، ذخیره‌سازی و نمایش بصری داده‌های امنیتی است.

### کامپوننت‌ها

- **اپلیکیشن اصلی**: جمع‌آوری دسترسی‌های RBAC از Kubernetes API هر 5 دقیقه
- **Sidecar Container**: پردازش لاگ‌ها و ارسال به Elasticsearch
- **Metrics Exporter**: ارائه متریک‌های Prometheus برای منابع حساس
- **Grafana Dashboards**: داشبوردهای بصری برای تحلیل دسترسی‌ها

## نیازمندی‌ها

- Kubernetes cluster (1.19+)
- Docker
- kubectl
- Helm 3.0+ (اختیاری)

## راهنمای نصب کامل (از صفر تا صد)

### مرحله ۱: آماده‌سازی Repository

```bash
# Clone repository
git clone https://github.com/BardiaYaghmaie/k8s-access-monitor.git
cd k8s-access-monitor

# اگر از kind استفاده می‌کنید، cluster را ایجاد کنید
kind create cluster --name k8s-access-monitor
kubectl config use-context kind-k8s-access-monitor
```

### مرحله ۲: ساخت Docker Images

```bash
# Build main application
docker build -f Dockerfile -t k8s-access-monitor:latest .

# Build sidecar
docker build -f Dockerfile.sidecar -t k8s-access-monitor-sidecar:latest .

# Build metrics exporter
docker build -f Dockerfile.metrics -t k8s-access-monitor-metrics:latest .

# اگر از kind استفاده می‌کنید، ایمیج‌ها را load کنید
kind load docker-image k8s-access-monitor:latest --name k8s-access-monitor
kind load docker-image k8s-access-monitor-sidecar:latest --name k8s-access-monitor
kind load docker-image k8s-access-monitor-metrics:latest --name k8s-access-monitor
```

### مرحله ۳: ایجاد Namespace و تنظیمات پایه

```bash
# ایجاد namespaces
kubectl create namespace monitoring
kubectl create namespace k8s-access-monitor
```

### مرحله ۴: نصب Elasticsearch

```bash
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
          requests:
            memory: 512Mi
            cpu: 250m
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
```

### مرحله ۵: نصب Prometheus

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
        resources:
          limits:
            memory: 1Gi
            cpu: 500m
          requests:
            memory: 512Mi
            cpu: 250m
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
    rule_files:
    scrape_configs:
    - job_name: 'prometheus'
      static_configs:
      - targets: ['localhost:9090']
    - job_name: 'k8s-access-monitor'
      static_configs:
      - targets: ['k8s-access-monitor-metrics.k8s-access-monitor.svc.cluster.local:8000']
EOF
```

### مرحله ۶: نصب Grafana

```bash
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
          value: admin
        - name: GF_USERS_ALLOW_SIGN_UP
          value: "false"
        resources:
          limits:
            memory: 512Mi
            cpu: 250m
          requests:
            memory: 256Mi
            cpu: 100m
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
```

### مرحله ۷: انتظار برای آماده شدن کامپوننت‌ها

```bash
# بررسی وضعیت pods
kubectl get pods -n monitoring

# انتظار تا همه pods ready شوند
kubectl wait --for=condition=ready pod --all -n monitoring --timeout=300s
```

### مرحله ۸: نصب سیستم مانیتورینگ دسترسی‌ها

```bash
# استفاده از Helm (روش پیشنهادی)
cd helm/k8s-access-monitor
helm install k8s-access-monitor . \
  --namespace k8s-access-monitor \
  --create-namespace \
  --set mainApp.inputConfig="$(cat ../../input.json | jq -c .)"

# یا نصب دستی با kubectl
kubectl apply -f helm/k8s-access-monitor/templates/ -n k8s-access-monitor
```

### مرحله ۹: تنظیمات Grafana

#### اضافه کردن Data Sources

1. **Port forward به Grafana:**
```bash
kubectl port-forward svc/grafana -n monitoring 3000:3000
```

2. **ورود به Grafana:**
   - آدرس: http://localhost:3000
   - Username: admin
   - Password: admin

3. **اضافه کردن Elasticsearch Data Source:**
   - Name: Elasticsearch
   - URL: http://elasticsearch.monitoring.svc.cluster.local:9200
   - Index name: k8s-access-logs*

4. **اضافه کردن Prometheus Data Source:**
   - Name: Prometheus
   - URL: http://prometheus.monitoring.svc.cluster.local:9090

#### ایمپورت داشبوردهای Grafana

```bash
# ایمپورت داشبورد Elasticsearch
curl -X POST -H "Content-Type: application/json" \
  -d @dashboards/elasticsearch-access-dashboard.json \
  http://admin:admin@localhost:3000/api/dashboards/db

# ایمپورت داشبورد Prometheus
curl -X POST -H "Content-Type: application/json" \
  -d @dashboards/prometheus-security-dashboard.json \
  http://admin:admin@localhost:3000/api/dashboards/db
```

## تنظیمات پیشرفته

### شخصی‌سازی کاربران مانیتور

فایل `input.json` را ویرایش کنید تا کاربران مورد نظر خود را اضافه کنید:

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
          "data": "eyJzb3VyY2UiOiAiTERBUCIsICJsYXN0X3VwZGF0ZWQiOiAiMjAyNS0xMi0xOFQxNDoxNToyNFoiLCAicm93c19hZmZlY3RlZCI6ICIxMCIsICJyZXBsYWNlIjogZmFsc2V9Cg=="
        }
      ],
      "internals": {
        "user-uuid-1": {
          "username": "your.username",
          "groups": ["developers", "admin"],
          "first_name": "Your",
          "last_name": "Name"
        }
      }
    }
  ]
}
```

### تنظیمات حساسیت منابع

در `src/metrics_exporter.py` می‌توانید منابع حساس را تنظیم کنید:

```python
# Line 29-31 in metrics_exporter.py
self.sensitive_namespaces = {'kube-system', 'default', 'your-sensitive-namespace'}
self.sensitive_resources = {'secrets', 'pods', 'nodes', 'your-sensitive-resource'}
```

## مانیتورینگ و عیب‌یابی

### بررسی وضعیت سیستم

```bash
# بررسی pods
kubectl get pods -n k8s-access-monitor

# بررسی cronjob
kubectl get cronjobs -n k8s-access-monitor

# مشاهده لاگ‌ها
kubectl logs -l app.kubernetes.io/name=k8s-access-monitor -n k8s-access-monitor

# مشاهده لاگ‌های sidecar
kubectl logs -l app.kubernetes.io/name=k8s-access-monitor -c sidecar -n k8s-access-monitor
```

### بررسی متریک‌ها

```bash
# Port forward به metrics
kubectl port-forward svc/k8s-access-monitor-metrics -n k8s-access-monitor 8000:8000

# مشاهده متریک‌ها
curl http://localhost:8000/metrics
```

### بررسی Elasticsearch

```bash
# Port forward به Elasticsearch
kubectl port-forward svc/elasticsearch -n monitoring 9200:9200

# بررسی ایندکس‌ها
curl http://localhost:9200/_cat/indices

# جستجو در داده‌ها
curl -X GET "localhost:9200/k8s-access-logs/_search?pretty"
```

### بررسی Prometheus

```bash
# Port forward به Prometheus
kubectl port-forward svc/prometheus -n monitoring 9090:9090

# دسترسی به UI در http://localhost:9090
```

## ساختار پروژه

```
k8s-access-monitor/
├── src/
│   ├── main.py                 # اپلیکیشن اصلی جمع‌آوری RBAC
│   ├── sidecar.py             # پردازشگر لاگ‌ها برای ES
│   └── metrics_exporter.py    # صادرکننده متریک‌های Prometheus
├── helm/
│   └── k8s-access-monitor/
│       ├── Chart.yaml
│       ├── values.yaml        # تنظیمات Helm
│       └── templates/         # Templateهای Kubernetes
├── dashboards/
│   ├── elasticsearch-access-dashboard.json    # داشبورد دسترسی‌ها
│   └── prometheus-security-dashboard.json     # داشبورد امنیتی
├── Dockerfile                 # ایمیج اپلیکیشن اصلی
├── Dockerfile.sidecar         # ایمیج sidecar
├── Dockerfile.metrics         # ایمیج metrics exporter
├── requirements.txt           # وابستگی‌های Python
├── input.json                 # تنظیمات کاربران
├── output.json                # نمونه خروجی
├── test.py                    # اسکریپت تست
└── README.md                  # این فایل
```

## متریک‌های Prometheus

### k8s_namespace_sensitive_access_users_count

شمارش کاربران با دسترسی به namespaceهای حساس:

```
k8s_namespace_sensitive_access_users_count{namespace="kube-system", verb="create", resource="pods"} 4
k8s_namespace_sensitive_access_users_count{namespace="default", verb="delete", resource="secrets"} 2
```

### k8s_cluster_wide_sensitive_access_users_count

شمارش کاربران با دسترسی cluster-wide به منابع حساس:

```
k8s_cluster_wide_sensitive_access_users_count{resource="secrets", verb="create"} 3
k8s_cluster_wide_sensitive_access_users_count{resource="pods", verb="exec"} 1
```

## توسعه و تست محلی

### اجرای تست‌ها

```bash
# اجرای validation کامل
python test.py

# نصب وابستگی‌ها
pip install -r requirements.txt

# اجرای اپلیکیشن اصلی (نیاز به دسترسی k8s)
python src/main.py

# اجرای sidecar (نیاز به Elasticsearch)
python src/sidecar.py

# اجرای metrics exporter
python src/metrics_exporter.py
```

### ساخت ایمیج‌ها برای توسعه

```bash
# Build with no cache for development
docker build --no-cache -f Dockerfile -t k8s-access-monitor:dev .

# Load into kind cluster
kind load docker-image k8s-access-monitor:dev --name k8s-access-monitor
```

## Troubleshooting

### مشکلات رایج

1. **CronJob اجرا نمی‌شود**
```bash
kubectl describe cronjob k8s-access-monitor-collector -n k8s-access-monitor
kubectl get jobs -n k8s-access-monitor
```

2. **دسترسی RBAC**
```bash
kubectl auth can-i list clusterroles --as=system:serviceaccount:k8s-access-monitor:k8s-access-monitor-sa
```

3. **اتصال به Elasticsearch**
```bash
kubectl run test-es --image=curlimages/curl --rm -it --restart=Never \
  -- curl elasticsearch.monitoring.svc.cluster.local:9200
```

4. **Metrics دریافت نمی‌شود**
```bash
kubectl port-forward svc/prometheus -n monitoring 9090:9090
# سپس در مرورگر: http://localhost:9090/targets
```

### Debug Mode

```bash
# فعال‌سازی debug logging
kubectl set env cronjob/k8s-access-monitor-collector LOG_LEVEL=DEBUG -n k8s-access-monitor
```

## امنیت

### RBAC Configuration

سیستم با حداقل دسترسی‌های مورد نیاز کار می‌کند:

- خواندن ClusterRole و ClusterRoleBinding
- خواندن Role و RoleBinding در تمام namespaceها
- دسترسی به API server

### Best Practices

- استفاده از Service Account اختصاصی
- محدود کردن namespaceهای حساس
- مانیتورینگ مداوم دسترسی‌ها
- تنظیم alerting برای دسترسی‌های مشکوک

## Contributing

1. Fork repository
2. Create feature branch (`git checkout -b feature/amazing-feature`)
3. Commit changes (`git commit -m 'Add amazing feature'`)
4. Push to branch (`git push origin feature/amazing-feature`)
5. Open Pull Request

## License

This project is licensed under the MIT License.

## Support

برای پشتیبانی:
- ایجاد Issue در GitHub repository
- بررسی documentation کامل
- اجرای test suite برای validation
