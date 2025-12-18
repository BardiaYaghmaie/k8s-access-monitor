#!/usr/bin/env python3
"""
Sidecar container for processing access logs and sending to Elasticsearch
"""

import json
import os
import time
import logging
from datetime import datetime
from typing import Dict, Any, List
from pathlib import Path

try:
    from elasticsearch import Elasticsearch
except ImportError:
    Elasticsearch = None

# Configure logging
logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

class LogProcessor:
    def __init__(self, log_file: str = "/app/logs/access_logs.jsonl"):
        self.log_file = Path(log_file)
        self.processed_file = self.log_file.with_suffix('.processed')
        self.elasticsearch_url = os.getenv('ELASTICSEARCH_URL', 'http://elasticsearch:9200')
        self.index_name = os.getenv('ELASTICSEARCH_INDEX', 'k8s-access-logs')

        # Initialize Elasticsearch client
        self.es_client = None
        if Elasticsearch:
            try:
                self.es_client = Elasticsearch([self.elasticsearch_url])
                logger.info(f"Connected to Elasticsearch at {self.elasticsearch_url}")
            except Exception as e:
                logger.error(f"Failed to connect to Elasticsearch: {e}")
        else:
            logger.warning("Elasticsearch client not available")

    def process_logs(self):
        """Main method to process log files and send to Elasticsearch"""
        logger.info("Starting log processing...")

        if not self.log_file.exists():
            logger.warning(f"Log file {self.log_file} does not exist yet")
            return

        processed_lines = set()
        if self.processed_file.exists():
            try:
                with open(self.processed_file, 'r') as f:
                    processed_lines = set(line.strip() for line in f)
            except Exception as e:
                logger.error(f"Failed to read processed file: {e}")

        new_entries = []

        try:
            with open(self.log_file, 'r') as f:
                for line_num, line in enumerate(f, 1):
                    line = line.strip()
                    if not line or line in processed_lines:
                        continue

                    try:
                        log_entry = json.loads(line)
                        new_entries.append((line_num, log_entry))
                    except json.JSONDecodeError as e:
                        logger.error(f"Failed to parse line {line_num}: {e}")
                        continue

        except Exception as e:
            logger.error(f"Failed to read log file: {e}")
            return

        if not new_entries:
            logger.info("No new log entries to process")
            return

        # Process new entries
        for line_num, log_entry in new_entries:
            self._process_log_entry(log_entry)

            # Mark as processed
            try:
                with open(self.processed_file, 'a') as f:
                    f.write(f"{line_num}\n")
            except Exception as e:
                logger.error(f"Failed to mark line {line_num} as processed: {e}")

        logger.info(f"Processed {len(new_entries)} new log entries")

    def _process_log_entry(self, log_entry: Dict[str, Any]):
        """Process a single log entry"""
        try:
            # Transform the log entry for Elasticsearch
            es_document = self._transform_for_elasticsearch(log_entry)

            # Send to Elasticsearch
            if self.es_client:
                self._send_to_elasticsearch(es_document)
            else:
                logger.info(f"Would send to Elasticsearch: {json.dumps(es_document, ensure_ascii=False)}")

        except Exception as e:
            logger.error(f"Failed to process log entry: {e}")

    def _transform_for_elasticsearch(self, log_entry: Dict[str, Any]) -> Dict[str, Any]:
        """Transform log entry for Elasticsearch indexing"""
        # Flatten accesses for better querying
        flattened_accesses = []

        for access in log_entry.get('accesses', []):
            namespace = access.get('namespace', '')
            is_cluster = access.get('is_cluster', False)
            resources = access.get('resources', {})

            for resource, verbs in resources.items():
                for verb in verbs:
                    flattened_accesses.append({
                        'namespace': namespace,
                        'resource': resource,
                        'verb': verb,
                        'is_cluster': is_cluster
                    })

        return {
            'username': log_entry.get('username'),
            'groups': log_entry.get('groups', []),
            'timestamp': log_entry.get('timestamp'),
            'access_count': len(log_entry.get('accesses', [])),
            'flattened_accesses': flattened_accesses,
            '@timestamp': datetime.fromisoformat(log_entry.get('timestamp').replace('Z', '+00:00'))
        }

    def _send_to_elasticsearch(self, document: Dict[str, Any]):
        """Send document to Elasticsearch"""
        try:
            response = self.es_client.index(
                index=self.index_name,
                document=document
            )
            logger.debug(f"Indexed document with ID: {response['_id']}")
        except Exception as e:
            logger.error(f"Failed to send document to Elasticsearch: {e}")

    def run_continuously(self, interval: int = 30):
        """Run log processing continuously"""
        logger.info(f"Starting continuous log processing every {interval} seconds")

        while True:
            try:
                self.process_logs()
            except Exception as e:
                logger.error(f"Error in log processing cycle: {e}")

            time.sleep(interval)

def main():
    processor = LogProcessor()

    # Check if we should run continuously or just once
    if os.getenv('CONTINUOUS_MODE', 'true').lower() == 'true':
        processor.run_continuously()
    else:
        processor.process_logs()

if __name__ == "__main__":
    main()
