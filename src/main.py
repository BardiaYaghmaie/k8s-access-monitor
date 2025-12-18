#!/usr/bin/env python3
"""
Kubernetes Access Monitoring and Analysis System
Main application for collecting user access data from Kubernetes RBAC
"""

import json
import os
import sys
import time
from datetime import datetime
from typing import Dict, List, Any, Optional
import base64
import logging

from kubernetes import client, config
from kubernetes.client.rest import ApiException

try:
    from elasticsearch import Elasticsearch
except ImportError:
    Elasticsearch = None

# Security: Load secrets from environment variables (set by Kubernetes secrets)
API_KEY = os.getenv('API_KEY', 'dummy-api-key')
JWT_SECRET = os.getenv('JWT_SECRET', 'dummy-jwt-secret')

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class KubernetesAccessMonitor:
    def __init__(self, input_file: str = "input.json", output_file: str = None):
        # Allow overriding output file via environment variable
        if output_file is None:
            output_file = os.getenv('OUTPUT_FILE', '/tmp/access_logs.jsonl')
        self.input_file = input_file
        self.output_file = output_file
        self.users_data = self._load_users_data()
        self.k8s_client = self._init_kubernetes_client()
        
        # Initialize Elasticsearch if available
        self.es_client = None
        es_url = os.getenv('ELASTICSEARCH_URL', 'http://elasticsearch:9200')
        es_index = os.getenv('ELASTICSEARCH_INDEX', 'k8s-access-logs')
        if Elasticsearch:
            try:
                self.es_client = Elasticsearch([es_url])
                logger.info(f"Connected to Elasticsearch at {es_url}")
            except Exception as e:
                logger.warning(f"Failed to connect to Elasticsearch: {e}")
        self.es_index = es_index

    def _load_users_data(self) -> Dict[str, Any]:
        """Load and parse the input JSON file containing user data"""
        try:
            with open(self.input_file, 'r', encoding='utf-8') as f:
                data = json.load(f)

            users = {}
            # Process internals (user information)
            for user_id, user_info in data['data'][0]['internals'].items():
                username = user_info['username']
                users[username] = {
                    'username': username,
                    'groups': user_info.get('groups', []),
                    'first_name': user_info.get('first_name', ''),
                    'last_name': user_info.get('last_name', ''),
                    'source': user_info.get('source', '')
                }

            logger.info(f"Loaded {len(users)} users from input file")
            return users

        except Exception as e:
            logger.error(f"Failed to load users data: {e}")
            sys.exit(1)

    def _init_kubernetes_client(self):
        """Initialize Kubernetes API client"""
        try:
            # Try to load in-cluster config first, then kubeconfig
            try:
                config.load_incluster_config()
                logger.info("Using in-cluster Kubernetes configuration")
            except:
                config.load_kube_config()
                logger.info("Using kubeconfig for Kubernetes connection")

            return client.CoreV1Api()
        except Exception as e:
            logger.error(f"Failed to initialize Kubernetes client: {e}")
            sys.exit(1)

    def _get_cluster_role_bindings(self) -> List[Dict]:
        """Get all ClusterRoleBindings from the cluster"""
        try:
            rbac_api = client.RbacAuthorizationV1Api()
            bindings = rbac_api.list_cluster_role_binding()
            return [binding.to_dict() for binding in bindings.items]
        except ApiException as e:
            logger.error(f"Failed to get cluster role bindings: {e}")
            return []

    def _get_role_bindings(self) -> List[Dict]:
        """Get all RoleBindings from all namespaces"""
        try:
            rbac_api = client.RbacAuthorizationV1Api()
            bindings = rbac_api.list_role_binding_for_all_namespaces()
            return [binding.to_dict() for binding in bindings.items]
        except ApiException as e:
            logger.error(f"Failed to get role bindings: {e}")
            return []

    def _get_cluster_roles(self) -> Dict[str, Dict]:
        """Get all ClusterRoles"""
        try:
            rbac_api = client.RbacAuthorizationV1Api()
            roles = rbac_api.list_cluster_role()
            return {role.metadata.name: role.to_dict() for role in roles.items}
        except ApiException as e:
            logger.error(f"Failed to get cluster roles: {e}")
            return {}

    def _get_roles(self) -> Dict[str, Dict]:
        """Get all Roles from all namespaces"""
        try:
            rbac_api = client.RbacAuthorizationV1Api()
            roles = rbac_api.list_role_for_all_namespaces()
            roles_dict = {}
            for role in roles.items:
                key = f"{role.metadata.namespace}/{role.metadata.name}"
                roles_dict[key] = role.to_dict()
            return roles_dict
        except ApiException as e:
            logger.error(f"Failed to get roles: {e}")
            return {}

    def _extract_permissions_from_role(self, role_data: Dict) -> Dict[str, List[str]]:
        """Extract permissions from a role definition"""
        permissions = {}

        if 'rules' in role_data:
            for rule in role_data['rules']:
                verbs = rule.get('verbs', [])
                resources = rule.get('resources', [])
                api_groups = rule.get('api_groups', [''])

                for resource in resources:
                    if resource not in permissions:
                        permissions[resource] = []
                    for verb in verbs:
                        if verb not in permissions[resource]:
                            permissions[resource].append(verb)

        return permissions

    def _get_user_accesses(self, username: str) -> List[Dict]:
        """Get all accesses for a specific user"""
        accesses = []

        # Get cluster role bindings and role bindings
        cluster_bindings = self._get_cluster_role_bindings()
        role_bindings = self._get_role_bindings()

        # Get roles
        cluster_roles = self._get_cluster_roles()
        roles = self._get_roles()

        # Check cluster role bindings
        for binding in cluster_bindings:
            subjects = binding.get('subjects', [])
            role_ref = binding.get('role_ref', {})

            if self._user_matches_subjects(username, subjects):
                role_name = role_ref.get('name')
                if role_name in cluster_roles:
                    permissions = self._extract_permissions_from_role(cluster_roles[role_name])
                    if permissions:
                        accesses.append({
                            'namespace': '',  # Cluster-wide
                            'resources': permissions,
                            'is_cluster': True
                        })

        # Check role bindings
        for binding in role_bindings:
            subjects = binding.get('subjects', [])
            role_ref = binding.get('role_ref', {})
            namespace = binding.get('metadata', {}).get('namespace', 'default')

            if self._user_matches_subjects(username, subjects):
                role_name = role_ref.get('name')
                role_key = f"{namespace}/{role_name}"

                if role_key in roles:
                    permissions = self._extract_permissions_from_role(roles[role_key])
                    if permissions:
                        accesses.append({
                            'namespace': namespace,
                            'resources': permissions,
                            'is_cluster': False
                        })

        return accesses

    def _user_matches_subjects(self, username: str, subjects) -> bool:
        """Check if username matches any of the subjects in a binding"""
        if not subjects:
            return False

        for subject in subjects:
            subject_kind = subject.get('kind', '')
            subject_name = subject.get('name', '')

            if subject_kind == 'User' and subject_name == username:
                return True
            elif subject_kind == 'Group':
                # Check if user is in the group (from our users data)
                user_groups = self.users_data.get(username, {}).get('groups', [])
                if subject_name in user_groups:
                    return True

        return False

    def _send_to_elasticsearch(self, log_entry: Dict[str, Any]):
        """Send log entry to Elasticsearch"""
        if not self.es_client:
            return
        
        try:
            # Transform for Elasticsearch
            es_doc = {
                'username': log_entry.get('username'),
                'groups': log_entry.get('groups', []),
                'timestamp': log_entry.get('timestamp'),
                'access_count': len(log_entry.get('accesses', [])),
                '@timestamp': datetime.fromisoformat(log_entry.get('timestamp').replace('Z', '+00:00'))
            }
            
            # Flatten accesses
            flattened = []
            for access in log_entry.get('accesses', []):
                namespace = access.get('namespace', '')
                is_cluster = access.get('is_cluster', False)
                resources = access.get('resources', {})
                
                for resource, verbs in resources.items():
                    for verb in verbs:
                        flattened.append({
                            'namespace': namespace,
                            'resource': resource,
                            'verb': verb,
                            'is_cluster': is_cluster
                        })
            
            es_doc['flattened_accesses'] = flattened
            
            # Send to Elasticsearch
            self.es_client.index(index=self.es_index, document=es_doc)
            logger.debug(f"Sent log entry for {log_entry.get('username')} to Elasticsearch")
        except Exception as e:
            logger.error(f"Failed to send to Elasticsearch: {e}")

    def collect_and_log_accesses(self):
        """Main method to collect accesses and generate logs"""
        logger.info("Starting access collection...")

        timestamp = datetime.utcnow().isoformat() + 'Z'

        # Process each user
        for username, user_info in self.users_data.items():
            accesses = self._get_user_accesses(username)

            log_entry = {
                'username': username,
                'groups': user_info['groups'],
                'accesses': accesses,
                'timestamp': timestamp
            }

            # Print to stdout
            print(json.dumps(log_entry, ensure_ascii=False))

            # Save to file - ensure directory exists
            try:
                os.makedirs(os.path.dirname(self.output_file) if os.path.dirname(self.output_file) else '.', exist_ok=True)
                with open(self.output_file, 'a', encoding='utf-8') as f:
                    f.write(json.dumps(log_entry, ensure_ascii=False) + '\n')
            except Exception as e:
                logger.warning(f"Failed to write to file {self.output_file}: {e}")

            # Send to Elasticsearch
            self._send_to_elasticsearch(log_entry)

        logger.info(f"Access collection completed. Logs saved to {self.output_file}")

def main():
    # Always use environment variables for configuration in containers
    input_file = os.getenv('INPUT_FILE', 'input.json')
    # Default to /app/logs for shared volume, fallback to /tmp
    output_file = os.getenv('OUTPUT_FILE', '/app/logs/access_logs.jsonl')
    monitor = KubernetesAccessMonitor(input_file=input_file, output_file=output_file)
    monitor.collect_and_log_accesses()

if __name__ == "__main__":
    main()
