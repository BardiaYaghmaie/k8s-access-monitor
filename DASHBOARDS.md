# Dashboard Files Guide

## Which Dashboard Files to Use

You have 4 dashboard files in the `dashboards/` directory:

### ✅ **CORRECT - Use These for Grafana:**
1. **`elasticsearch-access-dashboard-unwrapped.json`** - Elasticsearch dashboard (unwrapped format)
2. **`prometheus-security-dashboard-unwrapped.json`** - Prometheus dashboard (unwrapped format)

These are the correct files for:
- Grafana file-based provisioning (auto-import)
- Manual import into Grafana

### 📦 **Backup - Reference Only:**
3. **`elasticsearch-access-dashboard.json`** - Wrapped version (backup)
4. **`prometheus-security-dashboard.json`** - Wrapped version (backup)

These wrapped versions are kept for reference but should NOT be used for Grafana import.

## Why Unwrapped?

Grafana's file-based provisioning expects the dashboard object directly, not wrapped in `{"dashboard": {...}}`. The unwrapped versions have:
- ✅ Correct JSON structure
- ✅ UID fields for proper identification
- ✅ All panels and configurations intact

## Verification

Both unwrapped dashboards are valid JSON and contain:
- **Elasticsearch Dashboard**: 4 panels, UID: `k8s-access-elasticsearch`
- **Prometheus Dashboard**: 7 panels, UID: `k8s-security-prometheus`

## Usage

The README.md automatically uses the unwrapped versions when creating the ConfigMap. If you need to manually import:
1. Use the `*-unwrapped.json` files
2. Go to Grafana → Dashboards → Import
3. Upload the JSON file
