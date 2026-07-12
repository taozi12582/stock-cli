"""
Database queries for stock_info and fundamental_info tables.
All queries return (columns, rows) tuples.
"""

from stock_cli.config import (
    STOCK_INFO_TABLE,
    FUNDAMENTAL_TABLE,
    execute_query,
)


PRICE_COLUMNS = [
    "ts_code", "trade_date",
    "open", "high", "low", "close", "pre_close", "`change`", "pct_chg",
    "vol", "amount",
    "cost_5pct", "cost_15pct", "cost_50pct", "cost_85pct", "cost_95pct",
    "weight_avg", "winner_rate",
    "his_low", "his_high", "cost_concentration_90pct",
]

FUNDAMENTAL_COLUMNS = [
    "ts_code", "trade_date",
    "pledge_status", "pledge_ratio",
    "earnings_management_level", "discretionary_accruals",
    "big4_audit", "audit_agency",
]


def fetch_price_data(stock_code, days=120):
    sql = f"""
        SELECT {", ".join(PRICE_COLUMNS)}
        FROM {STOCK_INFO_TABLE}
        WHERE ts_code = %s
        ORDER BY trade_date DESC
        LIMIT %s
    """
    return execute_query(sql, (stock_code, days))


def fetch_fundamental_data(stock_code, days=120):
    sql = f"""
        SELECT {", ".join(FUNDAMENTAL_COLUMNS)}
        FROM {FUNDAMENTAL_TABLE}
        WHERE ts_code = %s
        ORDER BY trade_date DESC
        LIMIT %s
    """
    return execute_query(sql, (stock_code, days * 2))


def fetch_latest_fundamental(stock_code):
    sql = f"""
        SELECT {", ".join(FUNDAMENTAL_COLUMNS)}
        FROM {FUNDAMENTAL_TABLE}
        WHERE ts_code = %s
        ORDER BY trade_date DESC
        LIMIT 1
    """
    return execute_query(sql, (stock_code,))


def fetch_stock_list_by_risk(exclude_red=True, green_only=False, limit=100):
    if green_only:
        sql = f"""
            SELECT f.ts_code, f.trade_date, f.pledge_status, f.pledge_ratio,
                   f.earnings_management_level, f.discretionary_accruals,
                   f.big4_audit, f.audit_agency
            FROM {FUNDAMENTAL_TABLE} f
            INNER JOIN (
                SELECT ts_code, MAX(trade_date) as max_date
                FROM {FUNDAMENTAL_TABLE}
                GROUP BY ts_code
            ) latest ON f.ts_code = latest.ts_code AND f.trade_date = latest.max_date
            WHERE f.pledge_status IN ('未质押', '低比例')
              AND f.earnings_management_level = '低'
              AND f.big4_audit = '是'
            ORDER BY f.ts_code
            LIMIT %s
        """
        return execute_query(sql, (limit,))
    elif exclude_red:
        sql = f"""
            SELECT f.ts_code, f.trade_date, f.pledge_status, f.pledge_ratio,
                   f.earnings_management_level, f.discretionary_accruals,
                   f.big4_audit, f.audit_agency
            FROM {FUNDAMENTAL_TABLE} f
            INNER JOIN (
                SELECT ts_code, MAX(trade_date) as max_date
                FROM {FUNDAMENTAL_TABLE}
                GROUP BY ts_code
            ) latest ON f.ts_code = latest.ts_code AND f.trade_date = latest.max_date
            WHERE f.pledge_status NOT IN ('高比例', '刚解押')
              AND NOT (f.earnings_management_level = '高' AND f.big4_audit = '否')
            ORDER BY f.ts_code
            LIMIT %s
        """
        return execute_query(sql, (limit,))
    else:
        sql = f"""
            SELECT f.ts_code, f.trade_date, f.pledge_status, f.pledge_ratio,
                   f.earnings_management_level, f.discretionary_accruals,
                   f.big4_audit, f.audit_agency
            FROM {FUNDAMENTAL_TABLE} f
            INNER JOIN (
                SELECT ts_code, MAX(trade_date) as max_date
                FROM {FUNDAMENTAL_TABLE}
                GROUP BY ts_code
            ) latest ON f.ts_code = latest.ts_code AND f.trade_date = latest.max_date
            ORDER BY f.ts_code
            LIMIT %s
        """
        return execute_query(sql, (limit,))


def fetch_all_stock_codes(limit=10000):
    sql = f"""
        SELECT DISTINCT ts_code FROM {STOCK_INFO_TABLE}
        ORDER BY ts_code LIMIT %s
    """
    return execute_query(sql, (limit,))


def fetch_price_latest(stock_code):
    sql = f"""
        SELECT {", ".join(PRICE_COLUMNS)}
        FROM {STOCK_INFO_TABLE}
        WHERE ts_code = %s
        ORDER BY trade_date DESC
        LIMIT 1
    """
    return execute_query(sql, (stock_code,))
