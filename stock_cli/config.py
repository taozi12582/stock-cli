"""
Database configuration and connection management.
Supports environment variables with fallback defaults.
"""

import os
from dataclasses import dataclass

import pymysql


@dataclass
class MySQLConfig:
    host: str = "rm-bp1zrq0lt0hzy2v7tfo.mysql.rds.aliyuncs.com"
    port: int = 3306
    user: str = "taozi"
    password: str = "Orangejuice123!"
    database: str = "tzx-ow"
    charset: str = "utf8mb4"

    @classmethod
    def from_env(cls):
        return cls(
            host=os.getenv("MYSQL_HOST", cls.host),
            port=int(os.getenv("MYSQL_PORT", cls.port)),
            user=os.getenv("MYSQL_USER", cls.user),
            password=os.getenv("MYSQL_PASSWORD", cls.password),
            database=os.getenv("MYSQL_DATABASE", cls.database),
            charset=os.getenv("MYSQL_CHARSET", cls.charset),
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
