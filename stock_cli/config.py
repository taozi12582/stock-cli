"""
Database configuration and connection management.
Credentials loaded from .env file or environment variables.
"""

import os
from dataclasses import dataclass

import pymysql


def _load_dotenv():
    """Simple .env loader (no python-dotenv dependency)."""
    env_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), ".env")
    if not os.path.exists(env_path):
        return
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if line and not line.startswith("#") and "=" in line:
                key, _, val = line.partition("=")
                os.environ.setdefault(key.strip(), val.strip())


_load_dotenv()


@dataclass
class MySQLConfig:
    host: str = ""
    port: int = 3306
    user: str = ""
    password: str = ""
    database: str = ""
    charset: str = "utf8mb4"

    @classmethod
    def from_env(cls):
        return cls(
            host=os.getenv("MYSQL_HOST", ""),
            port=int(os.getenv("MYSQL_PORT", "3306")),
            user=os.getenv("MYSQL_USER", ""),
            password=os.getenv("MYSQL_PASSWORD", ""),
            database=os.getenv("MYSQL_DATABASE", ""),
            charset=os.getenv("MYSQL_CHARSET", "utf8mb4"),
        )

    def to_dict(self):
        return {
            "host": self.host,
            "port": self.port,
            "user": self.user,
            "password": self.password,
            "database": self.database,
            "charset": self.charset,
        }


STOCK_INFO_TABLE = "stock_info"
FUNDAMENTAL_TABLE = "fundamental_info"


def get_connection():
    cfg = MySQLConfig.from_env()
    return pymysql.connect(**cfg.to_dict())


def execute_query(sql, params=None, fetch="all"):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(sql, params)
        columns = [desc[0] for desc in cursor.description]
        if fetch == "all":
            rows = cursor.fetchall()
        elif fetch == "one":
            rows = cursor.fetchone()
        else:
            rows = cursor.fetchmany(fetch)
        conn.close()
        return columns, rows
    except Exception:
        conn.close()
        raise
