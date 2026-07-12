"""
初筛脚本 - 楚云风"简简单单做股票"选股系统

筛选流水线:
  全市场 → 流动性过滤 → 强势过滤 → 回调形态 → 企稳信号 → 基本面排雷 → 候选股

筛选规则来源: 《交易系统的构建心得和运用技巧》楚云风

用法:
  python3 -m stock_cli screener
  python3 -m stock_cli screener --min-amount 2 --pullback 0.382
  python3 -m stock_cli screener --no-fundamental-filter
"""

import sys
from datetime import datetime, timedelta

from stock_cli.config import get_connection, STOCK_INFO_TABLE, FUNDAMENTAL_TABLE
from stock_cli.risk import is_red_alert


def run_screener(
    min_amount=2.0,
    max_pullback=0.382,
    min_uptrend_gain=0.15,
    min_history_days=60,
    fundamental_filter=True,
    top_n=50,
    quiet=False,
):
    """运行初筛，返回候选股列表。
    
    quiet=True时不在stdout输出进度信息，只返回结果。
    """
    conn = get_connection()
    cursor = conn.cursor()

    def log(msg):
        if not quiet:
            print(msg)

    log("=== 楚云风选股初筛 ===")
    log(f"参数: 最低日均成交额={min_amount}亿 | 最大回调比例={max_pullback*100:.1f}% | "
        f"最低涨幅={min_uptrend_gain*100:.0f}% | 最低历史={min_history_days}天")
    log("")

    # Step 0: Get latest trade date
    cursor.execute(f"SELECT MAX(trade_date) FROM {STOCK_INFO_TABLE}")
    latest_date = cursor.fetchone()[0]
    log(f"最新交易日: {latest_date}")

    # Step 1: Liquidity filter - 5-day avg amount >= min_amount 亿
    log("\n[1/5] 流动性过滤...")
    cursor.execute(f"""
        SELECT ts_code, AVG(amount) as avg_amount, COUNT(*) as days
        FROM {STOCK_INFO_TABLE}
        WHERE trade_date >= DATE_SUB(%s, INTERVAL 10 DAY)
          AND trade_date <= %s
        GROUP BY ts_code
        HAVING avg_amount >= %s AND days >= 3
    """, (latest_date, latest_date, min_amount * 1e5))
    liquid_stocks = {r[0]: r[1] for r in cursor.fetchall()}
    log(f"  通过: {len(liquid_stocks)} 只 (日均成交额 >= {min_amount}亿)")

    if not liquid_stocks:
        log("  无股票通过流动性过滤")
        conn.close()
        return []

    # Step 2: Get market average 20-day return (compute from all stocks)
    log("\n[2/5] 计算市场基准...")
    cursor.execute(f"""
        SELECT AVG(pct_chg) as avg_daily
        FROM {STOCK_INFO_TABLE}
        WHERE trade_date >= DATE_SUB(%s, INTERVAL 30 DAY)
          AND trade_date <= %s
    """, (latest_date, latest_date))
    market_avg_daily = float(cursor.fetchone()[0] or 0)

    # Approximate 20-day market return (compound)
    cursor.execute(f"""
        SELECT AVG(ret_20d) as avg_20d_ret FROM (
            SELECT ts_code,
                   (POWER(MAX(CASE WHEN rn = 1 THEN close END) /
                          NULLIF(MAX(CASE WHEN rn = 21 THEN close END), 0), 1) - 1) as ret_20d
            FROM (
                SELECT ts_code, close,
                       ROW_NUMBER() OVER (PARTITION BY ts_code ORDER BY trade_date DESC) as rn
                FROM {STOCK_INFO_TABLE}
                WHERE trade_date >= DATE_SUB(%s, INTERVAL 40 DAY)
                  AND trade_date <= %s
            ) t
            WHERE rn <= 21
            GROUP BY ts_code
        ) x
    """, (latest_date, latest_date))
    market_20d_ret = float(cursor.fetchone()[0] or 0)
    log(f"  市场日均涨幅: {market_avg_daily:.3f}%")
    log(f"  市场20日涨幅: {market_20d_ret*100:.2f}%")

    # Step 3: For liquid stocks, fetch last 60 days data and compute indicators
    log("\n[3/5] 强势+回调形态筛选...")
    candidates = []

    stock_codes = list(liquid_stocks.keys())
    batch_size = 500
    for i in range(0, len(stock_codes), batch_size):
        batch = stock_codes[i:i + batch_size]
        placeholders = ",".join(["%s"] * len(batch))

        cursor.execute(f"""
            SELECT ts_code, trade_date, open, high, low, close,
                   pct_chg, vol, amount
            FROM {STOCK_INFO_TABLE}
            WHERE ts_code IN ({placeholders})
              AND trade_date >= DATE_SUB(%s, INTERVAL 90 DAY)
              AND trade_date <= %s
            ORDER BY ts_code, trade_date
        """, batch + [latest_date, latest_date])

        # Group by stock
        stock_data = {}
        for row in cursor.fetchall():
            code = row[0]
            if code not in stock_data:
                stock_data[code] = []
            stock_data[code].append({
                "date": row[1],
                "open": float(row[2]) if row[2] else 0,
                "high": float(row[3]) if row[3] else 0,
                "low": float(row[4]) if row[4] else 0,
                "close": float(row[5]) if row[5] else 0,
                "pct_chg": float(row[6]) if row[6] else 0,
                "vol": float(row[7]) if row[7] else 0,
                "amount": float(row[8]) if row[8] else 0,
            })

        for code, data in stock_data.items():
            if len(data) < min_history_days:
                continue

            result = _evaluate_stock(code, data, market_20d_ret, max_pullback, min_uptrend_gain)
            if result:
                candidates.append(result)

    log(f"  通过: {len(candidates)} 只 (强势+回调形态)")

    # Step 4: Stabilization signals
    log("\n[4/5] 企稳信号检测...")
    stabilized = []
    for c in candidates:
        sig = _check_stabilization(c["_recent_data"])
        if sig:
            c["stabilization"] = sig
            stabilized.append(c)

    log(f"  通过: {len(stabilized)} 只 (检测到企稳信号)")
    for s in stabilized[:5]:
        log(f"    {s['ts_code']}: {s['stabilization']}")

    # Step 5: Fundamental risk filter
    if fundamental_filter and stabilized:
        log("\n[5/5] 基本面排雷...")
        filtered = []
        for c in stabilized:
            cursor.execute(f"""
                SELECT pledge_status, earnings_management_level, big4_audit
                FROM {FUNDAMENTAL_TABLE}
                WHERE ts_code = %s
                ORDER BY trade_date DESC
                LIMIT 1
            """, (c["ts_code"],))
            row = cursor.fetchone()
            if row:
                pledge, em, big4 = row
                if is_red_alert(pledge, em, big4):
                    continue
                c["pledge_status"] = pledge or "未知"
                c["em_level"] = em or "未知"
                c["big4"] = big4 or "未知"
            filtered.append(c)
        log(f"  通过: {len(filtered)} 只 (排除红色警报)")
        result = filtered[:top_n]
    else:
        result = stabilized[:top_n]

    conn.close()

    # Clean internal field
    for c in result:
        c.pop("_recent_data", None)

    # Output
    log(f"\n=== 初筛结果: {len(result)} 只候选股 ===\n")
    if result and not quiet:
        log(f"{'股票代码':12s} {'20日涨幅':>8s} {'回调深度':>8s} {'量缩':>5s} {'企稳信号':20s} "
            f"{'质押':8s} {'盈余':6s} {'四大':4s}")
        log("-" * 90)
        for c in result:
            log(f"{c['ts_code']:12s} "
                f"{c['ret_20d']*100:>7.1f}% "
                f"{c['pullback_depth']*100:>7.1f}% "
                f"{'是' if c['vol_shrink'] else '否':>5s} "
                f"{c.get('stabilization',''):20s} "
                f"{c.get('pledge_status',''):8s} "
                f"{c.get('em_level',''):6s} "
                f"{c.get('big4',''):4s}")

    return result


def _evaluate_stock(code, data, market_20d_ret, max_pullback, min_uptrend_gain):
    if len(data) < 30:
        return None

    closes = [d["close"] for d in data]
    vols = [d["vol"] for d in data]
    highs = [d["high"] for d in data]
    lows = [d["low"] for d in data]
    opens = [d["open"] for d in data]
    n = len(data)

    # Moving averages
    ma10 = sum(closes[-10:]) / 10 if n >= 10 else 0
    ma30 = sum(closes[-30:]) / 30 if n >= 30 else 0

    # Trend check: uptrend (MA10 > MA30, or close > MA30)
    if ma30 == 0 or closes[-1] <= ma30:
        return None

    # 20-day return
    if n >= 21 and closes[-21] > 0:
        ret_20d = (closes[-1] / closes[-21]) - 1
    else:
        return None

    # Relative strength: stock 20d return > market 20d return
    if ret_20d <= market_20d_ret:
        return None

    # Find recent high (look back up to 30 days)
    lookback = min(30, n)
    recent_data = data[-lookback:]
    recent_highs = [d["high"] for d in recent_data]
    high_idx = recent_highs.index(max(recent_highs))

    # High should not be the last day (must be in pullback)
    if high_idx >= lookback - 2:
        return None

    recent_high = recent_highs[high_idx]
    current_close = closes[-1]

    # Pullback depth
    pullback = (recent_high - current_close) / recent_high if recent_high > 0 else 0
    if pullback <= 0 or pullback > 0.30:
        return None

    # Find the low before the high (start of uptrend)
    pre_high_data = recent_data[:high_idx + 1]
    if len(pre_high_data) < 5:
        return None
    pre_high_lows = [d["low"] for d in pre_high_data]
    uptrend_start = min(pre_high_lows)
    uptrend_gain = (recent_high / uptrend_start - 1) if uptrend_start > 0 else 0

    # Must have had a significant uptrend
    if uptrend_gain < min_uptrend_gain:
        return None

    # Pullback ratio relative to uptrend
    pullback_ratio = (recent_high - current_close) / (recent_high - uptrend_start) if (recent_high - uptrend_start) > 0 else 1
    if pullback_ratio > max_pullback:
        return None

    # Index of the high in full data (for volume comparison)
    pullback_start = len(data) - (lookback - high_idx)

    # Volume shrinkage: pullback period volume vs uptrend period volume
    pullback_days = len(data) - pullback_start - 1
    if pullback_days > 0:
        pullback_vol = sum(vols[pullback_start + 1:]) / pullback_days
    else:
        pullback_vol = vols[-1]

    prior_vol_start = max(0, pullback_start - 10)
    prior_vol_end = pullback_start
    if prior_vol_end > prior_vol_start:
        uptrend_vol = sum(vols[prior_vol_start:prior_vol_end]) / (prior_vol_end - prior_vol_start)
    else:
        uptrend_vol = pullback_vol
    vol_shrink = pullback_vol < uptrend_vol if uptrend_vol > 0 else False

    return {
        "ts_code": code,
        "close": current_close,
        "ma10": ma10,
        "ma30": ma30,
        "ret_20d": ret_20d,
        "recent_high": recent_high,
        "pullback_depth": pullback,
        "pullback_ratio": pullback_ratio,
        "uptrend_gain": uptrend_gain,
        "vol_shrink": vol_shrink,
        "_recent_data": data[-10:],
    }


def _check_stabilization(data):
    """
    Check for stabilization signals (企稳信号).
    Returns signal description if found, None otherwise.
    """
    if len(data) < 3:
        return None

    signals = []

    last = data[-1]
    prev = data[-2]
    prev2 = data[-3]

    last_body = last["close"] - last["open"]
    prev_body = prev["close"] - prev["open"]

    # Signal 1: Bullish candle eating previous bearish candle's body
    if prev_body < 0 and last_body > 0:
        if last["close"] >= prev["open"] and last["open"] <= prev["close"]:
            signals.append("吞噬前阴线")

    # Signal 2: Last bearish candle body eaten > 50%
    if prev_body < 0:
        eat_ratio = (last["close"] - prev["close"]) / abs(prev_body) if prev_body != 0 else 0
        if eat_ratio > 0.5 and last_body > 0:
            signals.append(f"吃掉前阴线{eat_ratio*100:.0f}%")

    # Signal 3: Intraday recovery (close - low) / close > 4% and close > open
    if last["close"] > 0:
        intraday_recovery = (last["close"] - last["low"]) / last["close"]
        if intraday_recovery > 0.04 and last_body > 0:
            signals.append("盘中回升>4%")

    # Signal 4: One down day, next day recovers > 50%
    if prev_body < 0 and last_body > 0:
        recovery = (last["close"] - prev["close"]) / abs(prev["close"] - prev["open"]) if (prev["close"] - prev["open"]) != 0 else 0
        if recovery > 0.5:
            signals.append("次日收回过半")

    # Signal 5: Small body consolidation after decline, then breakout
    if len(data) >= 5:
        recent_5 = data[-5:]
        small_bodies = all(abs(d["close"] - d["open"]) / d["close"] < 0.02 if d["close"] > 0 else True for d in recent_5[:-1])
        last_big_up = last_body > 0 and (last_body / last["close"]) > 0.03
        if small_bodies and last_big_up:
            signals.append("横盘后突破")

    # Volume minimum
    recent_vols = [d["vol"] for d in data[-5:]] if len(data) >= 5 else [d["vol"] for d in data]
    if min(recent_vols) == recent_vols[-1] and last_body > 0:
        signals.append("缩量至极+阳线")

    return " + ".join(signals) if signals else None
