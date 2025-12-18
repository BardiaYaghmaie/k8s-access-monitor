#!/usr/bin/env python3
"""
Test script for Kubernetes Access Monitor
"""

import json
import sys
import os
from pathlib import Path

def test_input_parsing():
    """Test parsing of input.json"""
    print("Testing input.json parsing...")

    if not Path('input.json').exists():
        print("❌ input.json not found")
        return False

    try:
        with open('input.json', 'r') as f:
            data = json.load(f)

        # Validate structure
        if 'metadata' not in data:
            print("❌ metadata not found in input.json")
            return False

        if 'data' not in data or not isinstance(data['data'], list):
            print("❌ data array not found in input.json")
            return False

        if not data['data'][0].get('internals'):
            print("❌ internals not found in input.json")
            return False

        users = list(data['data'][0]['internals'].keys())
        print(f"✅ Found {len(users)} users: {', '.join(users[:3])}{'...' if len(users) > 3 else ''}")

        return True

    except Exception as e:
        print(f"❌ Error parsing input.json: {e}")
        return False

def test_output_format():
    """Test output.json format"""
    print("\nTesting output.json format...")

    if not Path('output.json').exists():
        print("❌ output.json not found")
        return False

    try:
        with open('output.json', 'r') as f:
            data = json.load(f)

        required_fields = ['username', 'groups', 'accesses', 'timestamp']

        for field in required_fields:
            if field not in data:
                print(f"❌ Required field '{field}' not found in output.json")
                return False

        if not isinstance(data['accesses'], list):
            print("❌ accesses should be a list")
            return False

        print("✅ output.json format is valid")
        print(f"   Username: {data['username']}")
        print(f"   Groups: {data['groups']}")
        print(f"   Access count: {len(data['accesses'])}")

        return True

    except Exception as e:
        print(f"❌ Error parsing output.json: {e}")
        return False

def test_dockerfiles():
    """Test Dockerfile existence"""
    print("\nTesting Dockerfiles...")

    dockerfiles = ['Dockerfile', 'Dockerfile.sidecar', 'Dockerfile.metrics']
    missing = []

    for df in dockerfiles:
        if not Path(df).exists():
            missing.append(df)

    if missing:
        print(f"❌ Missing Dockerfiles: {', '.join(missing)}")
        return False

    print("✅ All Dockerfiles present")
    return True

def test_helm_chart():
    """Test Helm chart structure"""
    print("\nTesting Helm chart...")

    helm_path = Path('helm/k8s-access-monitor')

    required_files = [
        'Chart.yaml',
        'values.yaml',
        'templates/_helpers.tpl',
        'templates/deployment.yaml',
        'templates/cronjob.yaml',
        'templates/service.yaml',
        'templates/configmap.yaml',
        'templates/rbac.yaml',
        'templates/serviceaccount.yaml'
    ]

    missing = []
    for rf in required_files:
        if not (helm_path / rf).exists():
            missing.append(rf)

    if missing:
        print(f"❌ Missing Helm files: {', '.join(missing)}")
        return False

    print("✅ Helm chart structure is complete")
    return True

def test_dashboards():
    """Test Grafana dashboards"""
    print("\nTesting Grafana dashboards...")

    dashboards_path = Path('dashboards')

    required_dashboards = [
        'elasticsearch-access-dashboard.json',
        'prometheus-security-dashboard.json'
    ]

    missing = []
    for db in required_dashboards:
        if not (dashboards_path / db).exists():
            missing.append(db)

    if missing:
        print(f"❌ Missing dashboards: {', '.join(missing)}")
        return False

    # Validate JSON
    for db in required_dashboards:
        try:
            with open(dashboards_path / db, 'r') as f:
                json.load(f)
        except Exception as e:
            print(f"❌ Invalid JSON in {db}: {e}")
            return False

    print("✅ All dashboards are valid JSON")
    return True

def test_source_code():
    """Test source code structure"""
    print("\nTesting source code...")

    src_path = Path('src')

    required_files = [
        'main.py',
        'sidecar.py',
        'metrics_exporter.py'
    ]

    missing = []
    for rf in required_files:
        if not (src_path / rf).exists():
            missing.append(rf)

    if missing:
        print(f"❌ Missing source files: {', '.join(missing)}")
        return False

    # Check if files are executable
    for rf in required_files:
        if not os.access(src_path / rf, os.X_OK):
            print(f"⚠️  {rf} is not executable")

    print("✅ Source code structure is complete")
    return True

def main():
    """Run all tests"""
    print("🚀 Kubernetes Access Monitor - Test Suite")
    print("=" * 50)

    tests = [
        test_input_parsing,
        test_output_format,
        test_dockerfiles,
        test_helm_chart,
        test_dashboards,
        test_source_code
    ]

    passed = 0
    total = len(tests)

    for test in tests:
        try:
            if test():
                passed += 1
        except Exception as e:
            print(f"❌ Test failed with exception: {e}")

    print("\n" + "=" * 50)
    print(f"📊 Test Results: {passed}/{total} passed")

    if passed == total:
        print("🎉 All tests passed! Ready for deployment.")
        return 0
    else:
        print("❌ Some tests failed. Please fix the issues before deployment.")
        return 1

if __name__ == "__main__":
    sys.exit(main())
