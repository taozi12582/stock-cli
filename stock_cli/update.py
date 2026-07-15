"""
每日数据更新模块 - 更新stock_info和fundamental_info

流程:
  1. 检查stock_info最新日期
  2. 从Tushare获取缺失交易日的行情数据(pro.daily) + 筹码分布(pro.cyq_perf)
  3. 合并写入stock_info
  4. 更新fundamental_info（质押+四大+盈余管理carry-forward）

用法:
  python3 -m stock_cli update              # 更新到今天
  python3 -m stock_cli update --check      # 只检查不更新
  python3 -m stock_cli update --date 2026-07-01
"""

import os
import sys
import time
from datetime import datetime, date

import tushare as ts
import pymysql

from stock_cli.config import get_connection, STOCK_INFO_TABLE, FUNDAMENTAL_TABLE

TUSHARE_TOKEN = os.environ.get("TUSHARE_TOKEN", "")
TUSHARE_URL = os.environ.get("TUSHARE_URL", "")

BATCH_SIZE = 500
API_SLEEP = 0.3

BIG4_KEYWORDS = ["普华永道", "德勤", "安永", "毕马威"]
PLEDGE_THRESHOLDS = {"low": 20, "mid": 50}


def _get_tushare_api():
    pro = ts.pro_api(TUSHARE_TOKEN)
    pro._DataApi__token = TUSHARE_TOKEN
    pro._DataApi__http_url = TUSHARE_URL
    return pro


def _classify_pledge(ratio, prev_ratio=None):
    if ratio is None or ratio == 0:
        if prev_ratio is not None and prev_ratio > 0:
            return "刚解押"
        return "未质押"
    elif ratio < PLEDGE_THRESHOLDS["low"]:
        return "低比例质押"
    elif ratio < PLEDGE_THRESHOLDS["mid"]:
        return "中比例质押"
    else:
        return "高比例质押"


def _is_big4(agency_name):
    if not agency_name:
        return False
    for kw in BIG4_KEYWORDS:
        if kw in agency_name:
            return True
    return False


def check_data():
    """检查数据最新状态，返回 (latest_stock_date, latest_fund_date, gap_days)。"""
    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(f"SELECT MAX(trade_date) FROM {STOCK_INFO_TABLE}")
    latest_stock = cursor.fetchone()[0]

    cursor.execute(f"SELECT MAX(trade_date) FROM {FUNDAMENTAL_TABLE}")
    latest_fund = cursor.fetchone()[0]

    conn.close()

    today = date.today()
    gap = (today - latest_stock).days if latest_stock else -1

    return latest_stock, latest_fund, gap


def _get_trading_days(pro, start_date, end_date):
    start_str = start_date.strftime("%Y%m%d")
    end_str = end_date.strftime("%Y%m%d")
    df = pro.trade_cal(exchange="SSE", start_date=start_str, end_date=end_str, is_open="1")
    if df is None or len(df) == 0:
        return []
    days = sorted(df["cal_date"].tolist())
    return [datetime.strptime(d, "%Y%m%d").date() for d in days]


def _update_stock_info_for_date(pro, conn, trade_date):
    """获取并插入某交易日的stock_info数据。"""
    date_str = trade_date.strftime("%Y%m%d")
    cursor = conn.cursor()

    df_daily = pro.daily(trade_date=date_str)
    if df_daily is None or len(df_daily) == 0:
        return 0

    df_chip = pro.cyq_perf(trade_date=date_str)
    if df_chip is not None and len(df_chip) > 0:
        chip_dict = df_chip.set_index("ts_code").to_dict(orient="index")
    else:
        chip_dict = None

    values = []
    for _, row in df_daily.iterrows():
        ts_code = row["ts_code"]

        cost_5 = cost_15 = cost_50 = cost_85 = cost_95 = None
        weight_avg = winner_rate = his_low = his_high = None
        cc90 = None

        if chip_dict is not None and ts_code in chip_dict:
            chip = chip_dict[ts_code]
            his_low = float(chip.get("his_low") or 0) or None
            his_high = float(chip.get("his_high") or 0) or None
            cost_5 = float(chip.get("cost_5pct") or 0) or None
            cost_15 = float(chip.get("cost_15pct") or 0) or None
            cost_50 = float(chip.get("cost_50pct") or 0) or None
            cost_85 = float(chip.get("cost_85pct") or 0) or None
            cost_95 = float(chip.get("cost_95pct") or 0) or None
            weight_avg = float(chip.get("weight_avg") or 0) or None
            winner_rate = float(chip.get("winner_rate") or 0) or None

            if cost_5 and cost_95 and (cost_95 + cost_5) > 0:
                cc90 = (cost_95 - cost_5) / (cost_95 + cost_5)

        values.append((
            ts_code, trade_date,
            float(row.get("open") or 0), float(row.get("high") or 0),
            float(row.get("low") or 0), float(row.get("close") or 0),
            float(row.get("pre_close") or 0), float(row.get("change") or 0),
            float(row.get("pct_chg") or 0),
            float(row.get("vol") or 0), float(row.get("amount") or 0),
            cost_5, cost_15, cost_50, cost_85, cost_95,
            weight_avg, winner_rate, his_low, his_high, cc90,
        ))

    sql = f"""
        INSERT INTO {STOCK_INFO_TABLE} (
            ts_code, trade_date,
            open, high, low, close, pre_close, `change`, pct_chg,
            vol, amount,
            cost_5pct, cost_15pct, cost_50pct, cost_85pct, cost_95pct,
            weight_avg, winner_rate, his_low, his_high, cost_concentration_90pct
        ) VALUES (
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
        )
        ON DUPLICATE KEY UPDATE
            open=VALUES(open), high=VALUES(high), low=VALUES(low),
            close=VALUES(close), pre_close=VALUES(pre_close),
            `change`=VALUES(`change`), pct_chg=VALUES(pct_chg),
            vol=VALUES(vol), amount=VALUES(amount),
            cost_5pct=VALUES(cost_5pct), cost_15pct=VALUES(cost_15pct),
            cost_50pct=VALUES(cost_50pct), cost_85pct=VALUES(cost_85pct),
            cost_95pct=VALUES(cost_95pct), weight_avg=VALUES(weight_avg),
            winner_rate=VALUES(winner_rate), his_low=VALUES(his_low),
            his_high=VALUES(his_high),
            cost_concentration_90pct=VALUES(cost_concentration_90pct)
    """

    for i in range(0, len(values), BATCH_SIZE):
        cursor.executemany(sql, values[i:i + BATCH_SIZE])
        conn.commit()

    return len(values)


def _update_fundamental_for_date(pro, conn, trade_date):
    """更新某交易日的fundamental_info数据。"""
    cursor = conn.cursor()
    cursor.execute(
        "SELECT ts_code FROM stock_info WHERE trade_date = %s", (trade_date,)
    )
    codes = [row[0] for row in cursor.fetchall()]
    if not codes:
        return

    # 1. Pledge
    pledge_updated = 0
    for ts_code in codes:
        try:
            df = pro.pledge_stat(ts_code=ts_code)
            if df is not None and len(df) > 0:
                latest = df.iloc[0]
                ratio = float(latest.get("pledge_ratio", 0) or 0)
                cursor.execute(f"""
                    SELECT pledge_ratio FROM {FUNDAMENTAL_TABLE}
                    WHERE ts_code = %s AND trade_date < %s
                    ORDER BY trade_date DESC LIMIT 1
                """, (ts_code, trade_date))
                prev = cursor.fetchone()
                prev_ratio = prev[0] if prev and prev[0] else 0
                status = _classify_pledge(ratio, prev_ratio if ratio == 0 else None)
                cursor.execute(f"""
                    INSERT INTO {FUNDAMENTAL_TABLE}
                        (ts_code, trade_date, pledge_status, pledge_ratio)
                    VALUES (%s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                        pledge_status = VALUES(pledge_status),
                        pledge_ratio = VALUES(pledge_ratio)
                """, (ts_code, trade_date, status, ratio))
                pledge_updated += 1
        except Exception:
            pass
        time.sleep(API_SLEEP)
    conn.commit()
    print(f"  质押: {pledge_updated}/{len(codes)}", file=sys.stderr)

    # 2. Big4
    date_str = trade_date.strftime("%Y%m%d")
    try:
        df = pro.fina_audit(ann_date=date_str)
        if df is not None and len(df) > 0:
            for _, row in df.iterrows():
                ts_code = row["ts_code"]
                agency = row.get("audit_agency", "")
                big4 = "是" if _is_big4(agency) else "否"
                cursor.execute(f"""
                    INSERT INTO {FUNDAMENTAL_TABLE}
                        (ts_code, trade_date, big4_audit, audit_agency)
                    VALUES (%s, %s, %s, %s)
                    ON DUPLICATE KEY UPDATE
                        big4_audit = VALUES(big4_audit),
                        audit_agency = VALUES(audit_agency)
                """, (ts_code, trade_date, big4, agency or ""))
            conn.commit()
            print(f"  四大审计: {len(df)} 条", file=sys.stderr)
    except Exception:
        pass

    # 3. EM carry-forward
    em_values = []
    for ts_code in codes:
        cursor.execute(f"""
            SELECT earnings_management_level, discretionary_accruals
            FROM {FUNDAMENTAL_TABLE}
            WHERE ts_code = %s AND trade_date < %s
              AND earnings_management_level IS NOT NULL
            ORDER BY trade_date DESC LIMIT 1
        """, (ts_code, trade_date))
        prev = cursor.fetchone()
        if prev:
            em_values.append((ts_code, trade_date, prev[0], prev[1]))

    sql_em = f"""
        INSERT INTO {FUNDAMENTAL_TABLE}
            (ts_code, trade_date, earnings_management_level, discretionary_accruals)
        VALUES (%s, %s, %s, %s)
        ON DUPLICATE KEY UPDATE
            earnings_management_level = VALUES(earnings_management_level),
            discretionary_accruals = VALUES(discretionary_accruals)
    """
    for i in range(0, len(em_values), BATCH_SIZE):
        cursor.executemany(sql_em, em_values[i:i + BATCH_SIZE])
    conn.commit()
    print(f"  盈余管理carry-forward: {len(em_values)} 条", file=sys.stderr)


def run_update(target_date=None, skip_fundamental=False, quiet=False):
    """运行数据更新。返回更新的交易日数量。"""

    def log(msg):
        if not quiet:
            print(msg, file=sys.stderr)

    conn = get_connection()
    cursor = conn.cursor()

    cursor.execute(f"SELECT MAX(trade_date) FROM {STOCK_INFO_TABLE}")
    latest_stock = cursor.fetchone()[0]

    if target_date is None:
        target_date = date.today()

    log(f"stock_info 最新: {latest_stock}")
    log(f"目标日期: {target_date}")

    if latest_stock and target_date <= latest_stock:
        log("数据已是最新，无需更新")
        conn.close()
        return 0

    pro = _get_tushare_api()

    start = latest_stock if latest_stock else target_date
    trading_days = _get_trading_days(pro, start, target_date)
    if latest_stock:
        trading_days = [d for d in trading_days if d > latest_stock]

    if not trading_days:
        log("无缺失交易日")
        conn.close()
        return 0

    log(f"\n需更新 {len(trading_days)} 个交易日:")

    for td in trading_days:
        log(f"\n--- {td} ---")
        count = _update_stock_info_for_date(pro, conn, td)
        log(f"  行情: {count} 条")
        if count > 0 and not skip_fundamental:
            _update_fundamental_for_date(pro, conn, td)

    cursor.execute(f"SELECT MAX(trade_date) FROM {STOCK_INFO_TABLE}")
    final_stock = cursor.fetchone()[0]
    cursor.execute(f"SELECT MAX(trade_date) FROM {FUNDAMENTAL_TABLE}")
    final_fund = cursor.fetchone()[0]

    log(f"\n更新完成:")
    log(f"  stock_info: {final_stock}")
    log(f"  fundamental_info: {final_fund}")

    conn.close()
    return len(trading_days)
