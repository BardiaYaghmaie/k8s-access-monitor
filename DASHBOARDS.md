# Dashboard Files Guide

## Which Dashboard Files to Use

You have 2 dashboard files in the `dashboards/` directory:

### ✅ **CORRECT - Use These for Grafana:**
1. **`elasticsearch-access-dashboard-unwrapped.json`** - Elasticsearch dashboard (unwrapped format)
2. **`prometheus-security-dashboard-unwrapped.json`** - Prometheus dashboard (unwrapped format)

These are the correct files for:
- Grafana file-based provisioning (auto-import)
- Manual import into Grafana

## Why Unwrapped?

Grafana's file-based provisioning expects the dashboard object directly, not wrapped in `{"dashboard": {...}}`. The unwrapped versions have:
- ✅ Correct JSON structure
- ✅ UID fields for proper identification
- ✅ All panels and configurations intact

## Verification

Both dashboards are valid JSON and contain:
- **Elasticsearch Dashboard**: 4 panels, UID: `k8s-access-elasticsearch`
- **Prometheus Dashboard**: 7 panels, UID: `k8s-security-prometheus`

## Usage

The README.md automatically uses these dashboard files when creating the ConfigMap. If you need to manually import:
1. Use the `*-unwrapped.json` files
2. Go to Grafana → Dashboards → Import
3. Upload the JSON file
