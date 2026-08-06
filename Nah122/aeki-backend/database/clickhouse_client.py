"""
ClickHouse client for dashboard analytics
"""

import os
import logging
import clickhouse_connect
from typing import List, Dict, Any

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ClickHouseClient")


class ClickHouseClient:
    def __init__(self):
        self.provider = os.getenv("CLICKHOUSE_PROVIDER", "clickhouse").lower()
        if os.getenv("TINYBIRD_TOKEN"):
            self.provider = "tinybird"
        
        if self.provider == "tinybird":
            self.host = os.getenv("TINYBIRD_CH_HOST", "clickhouse.europe-west2.gcp.tinybird.co")
            self.port = int(os.getenv("TINYBIRD_CH_PORT", "443"))
            self.username = os.getenv("TINYBIRD_CH_USER", "petros_workspace")
            self.password = os.getenv("TINYBIRD_TOKEN", "")
            self.secure = True
        else:
            self.host = os.getenv("CLICKHOUSE_HOST", "localhost")
            self.port = int(os.getenv("CLICKHOUSE_PORT", "8123"))
            self.username = os.getenv("CLICKHOUSE_USER", "default")
            self.password = os.getenv("CLICKHOUSE_PASSWORD", "")
            self.secure = os.getenv("CLICKHOUSE_SECURE", "false").lower() == "true"
        
        self.client = None
        self._connect()
    
    def _connect(self):
        """Establish connection to ClickHouse"""
        try:
            self.client = clickhouse_connect.get_client(
                host=self.host,
                port=self.port,
                username=self.username,
                password=self.password,
                secure=self.secure,
            )
            name = "Tinybird ClickHouse Interface" if self.provider == "tinybird" else "ClickHouse"
            logger.info(f"✅ Connected to {name} at {self.host}:{self.port}")
        except Exception as e:
            logger.error(f"❌ Failed to connect to ClickHouse: {e}")
            raise
    
    def query(self, sql: str) -> List[Dict[str, Any]]:
        """Execute a query and return results as list of dicts"""
        try:
            result = self.client.query(sql)
            columns = result.column_names
            rows = result.result_rows
            
            return [dict(zip(columns, row)) for row in rows]
        except Exception as e:
            logger.error(f"❌ Query failed: {e}")
            logger.error(f"SQL: {sql}")
            raise
    
    def query_df(self, sql: str):
        """Execute a query and return results as pandas DataFrame"""
        try:
            return self.client.query_df(sql)
        except Exception as e:
            logger.error(f"❌ Query failed: {e}")
            raise
    
    def close(self):
        """Close the connection"""
        if self.client:
            self.client.close()


import threading

_local = threading.local()

def get_clickhouse_client() -> ClickHouseClient:
    """Get or create a thread-local ClickHouse client instance"""
    if not hasattr(_local, "client"):
        _local.client = ClickHouseClient()
    return _local.client
