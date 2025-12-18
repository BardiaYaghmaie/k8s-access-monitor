#!/usr/bin/env python3
"""
Prometheus metrics exporter for Kubernetes access monitoring
"""

import json
import os
import time
import logging
from datetime import datetime
from typing import Dict, List, Any, Set
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

from kubernetes import client, config
from kubernetes.client.rest import ApiException

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class MetricsExporter:
    def __init__(self, input_file: str = "/app/input.json"):
        self.input_file = input_file
        self.users_data = self._load_users_data()
        self.k8s_client = self._init_kubernetes_client()

        # Define sensitive namespaces and resources
        self.sensitive_namespaces = {'kube-system', 'default'}
        self.sensitive_resources = {'secrets', 'pods', 'nodes', 'namespaces'}

    def _load_users_data(self) -> Dict[str, Any]:
        """Load users data from input file"""
        try:
            with open(self.input_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            users = {}
            for user_id, user_info in data['data'][0]['internals'].items():
                username = user_info['username']
                users[username] = {
                    'username': username,
                    'groups': user_info.get('groups', []),
                }

            logger.info(f"Loaded {len(users)} users for metrics")
            return users

        except Exception as e:
            logger.error(f"Failed to load users data: {e}")
            return {}

    def _init_kubernetes_client(self):
        """Initialize Kubernetes API client"""
        try:
            try:
                config.load_incluster_config()
            except:
                config.load_kube_config()
            return client.CoreV1Api()
        except Exception as e:
            logger.error(f"Failed to initialize Kubernetes client: {e}")
            return None

    def _get_all_bindings(self) -> tuple:
        """Get all role bindings and cluster role bindings"""
        cluster_bindings = []
        role_bindings = []

        try:
            rbac_api = client.RbacAuthorizationV1Api()

            # Get cluster role bindings
            cluster_bindings = rbac_api.list_cluster_role_binding().items

            # Get role bindings
            role_bindings = rbac_api.list_role_binding_for_all_namespaces().items

        except ApiException as e:
            logger.error(f"Failed to get bindings: {e}")

        return cluster_bindings, role_bindings

    def _get_roles(self) -> tuple:
        """Get all roles and cluster roles"""
        cluster_roles = {}
        roles = {}

        try:
            rbac_api = client.RbacAuthorizationV1Api()

            # Get cluster roles
            for role in rbac_api.list_cluster_role().items:
                cluster_roles[role.metadata.name] = role

            # Get roles
            for role in rbac_api.list_role_for_all_namespaces().items:
                key = f"{role.metadata.namespace}/{role.metadata.name}"
                roles[key] = role

        except ApiException as e:
            logger.error(f"Failed to get roles: {e}")

        return cluster_roles, roles

    def _extract_permissions(self, role) -> Dict[str, List[str]]:
        """Extract permissions from a role"""
        permissions = {}

        if hasattr(role, 'rules') and role.rules:
            for rule in role.rules:
                verbs = rule.verbs or []
                resources = rule.resources or []
                api_groups = rule.api_groups or ['']

                for resource in resources:
                    if resource not in permissions:
                        permissions[resource] = []
                    for verb in verbs:
                        if verb not in permissions[resource]:
                            permissions[resource].append(verb)

        return permissions

    def _user_matches_subjects(self, username: str, subjects) -> bool:
        """Check if user matches subjects"""
        if not subjects:
            return False

        for subject in subjects:
            if subject.kind == 'User' and subject.name == username:
                return True
            elif subject.kind == 'Group':
                user_groups = self.users_data.get(username, {}).get('groups', [])
                if subject.name in user_groups:
                    return True

        return False

    def calculate_namespace_sensitive_metrics(self) -> Dict[str, Dict[str, int]]:
        """Calculate metrics for sensitive namespace access"""
        metrics = {}

        cluster_bindings, role_bindings = self._get_all_bindings()
        cluster_roles, roles = self._get_roles()

        # Process cluster role bindings (cluster-wide access)
        for binding in cluster_bindings:
            if not binding.subjects:
                continue

            role_ref = binding.role_ref
            if role_ref.kind != 'ClusterRole':
                continue

            role_name = role_ref.name
            if role_name not in cluster_roles:
                continue

            role = cluster_roles[role_name]
            permissions = self._extract_permissions(role)

            # Check each user
            for username in self.users_data.keys():
                if not self._user_matches_subjects(username, binding.subjects):
                    continue

                # This user has cluster-wide access
                for namespace in self.sensitive_namespaces:
                    for resource, verbs in permissions.items():
                        if resource in self.sensitive_resources:
                            for verb in verbs:
                                key = f"{namespace}_{verb}_{resource}"
                                if key not in metrics:
                                    metrics[key] = {}
                                metrics[key][username] = metrics[key].get(username, 0) + 1

        # Process role bindings (namespace-specific access)
        for binding in role_bindings:
            if not binding.subjects:
                continue

            namespace = binding.metadata.namespace
            if namespace not in self.sensitive_namespaces:
                continue

            role_ref = binding.role_ref
            role_name = role_ref.name

            role_key = f"{namespace}/{role_name}"
            if role_key not in roles:
                continue

            role = roles[role_key]
            permissions = self._extract_permissions(role)

            # Check each user
            for username in self.users_data.keys():
                if not self._user_matches_subjects(username, binding.subjects):
                    continue

                for resource, verbs in permissions.items():
                    if resource in self.sensitive_resources:
                        for verb in verbs:
                            key = f"{namespace}_{verb}_{resource}"
                            if key not in metrics:
                                metrics[key] = {}
                            metrics[key][username] = metrics[key].get(username, 0) + 1

        return metrics

    def calculate_cluster_wide_sensitive_metrics(self) -> Dict[str, Dict[str, int]]:
        """Calculate metrics for cluster-wide sensitive access"""
        metrics = {}

        cluster_bindings, _ = self._get_all_bindings()
        cluster_roles, _ = self._get_roles()

        # Process cluster role bindings
        for binding in cluster_bindings:
            if not binding.subjects:
                continue

            role_ref = binding.role_ref
            if role_ref.kind != 'ClusterRole':
                continue

            role_name = role_ref.name
            if role_name not in cluster_roles:
                continue

            role = cluster_roles[role_name]
            permissions = self._extract_permissions(role)

            # Check each user
            for username in self.users_data.keys():
                if not self._user_matches_subjects(username, binding.subjects):
                    continue

                for resource, verbs in permissions.items():
                    if resource in self.sensitive_resources:
                        for verb in verbs:
                            key = f"{verb}_{resource}"
                            if key not in metrics:
                                metrics[key] = {}
                            metrics[key][username] = metrics[key].get(username, 0) + 1

        return metrics

    def generate_prometheus_metrics(self) -> str:
        """Generate Prometheus metrics output"""
        lines = []

        # Namespace sensitive access metrics
        namespace_metrics = self.calculate_namespace_sensitive_metrics()
        for key, users in namespace_metrics.items():
            namespace, verb, resource = key.split('_', 2)
            user_count = len(users)
            lines.append(f'k8s_namespace_sensitive_access_users_count{{namespace="{namespace}",verb="{verb}",resource="{resource}"}} {user_count}')

        # Cluster-wide sensitive access metrics
        cluster_metrics = self.calculate_cluster_wide_sensitive_metrics()
        for key, users in cluster_metrics.items():
            verb, resource = key.split('_', 1)
            user_count = len(users)
            lines.append(f'k8s_cluster_wide_sensitive_access_users_count{{resource="{resource}",verb="{verb}"}} {user_count}')

        return '\n'.join(lines)

class MetricsHandler(BaseHTTPRequestHandler):
    def __init__(self, *args, exporter=None, **kwargs):
        self.exporter = exporter
        super().__init__(*args, **kwargs)

    def do_GET(self):
        if self.path == '/metrics':
            self.send_response(200)
            self.send_header('Content-type', 'text/plain; charset=utf-8')
            self.end_headers()

            try:
                metrics = self.exporter.generate_prometheus_metrics()
                self.wfile.write(metrics.encode('utf-8'))
            except Exception as e:
                logger.error(f"Failed to generate metrics: {e}")
                self.wfile.write(b'# Error generating metrics\n')
        else:
            self.send_response(404)
            self.end_headers()
            self.wfile.write(b'Not found\n')

    def log_message(self, format, *args):
        # Suppress default HTTP server logs
        pass

def main():
    port = int(os.getenv('METRICS_PORT', '8000'))
    input_file = os.getenv('INPUT_FILE', '/app/input.json')

    exporter = MetricsExporter(input_file)

    def handler_class(*args, **kwargs):
        return MetricsHandler(*args, exporter=exporter, **kwargs)

    server = HTTPServer(('0.0.0.0', port), handler_class)
    logger.info(f"Starting metrics server on port {port}")

    try:
        server.serve_forever()
    except KeyboardInterrupt:
        logger.info("Shutting down metrics server")
        server.shutdown()

if __name__ == "__main__":
    main()
