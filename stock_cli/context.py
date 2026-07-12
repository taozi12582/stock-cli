"""
Combined context generator - merges fundamental + price data.
Produces a single text block ready for LLM/subagent consumption.
"""

from stock_cli.db import (
    fetch_price_data,
    fetch_fundamental_data,
    fetch_latest_fundamental,
)
from stock_cli.fundamental import format_fundamental
from stock_cli.price import format_price
from stock_cli.risk import assess_risk, risk_label, is_red_alert, is_green


ANALYSIS_PROMPT = """=== 分析指引 ===

按 stock-analysis Skill 的5步框架分析（见 ~/.agents/skills/stock-analysis/SKILL.md）：

1. 趋势判断（MA10/MA30、相对强弱、当前位置）
2. 形态识别（强势股回调形态、企稳信号检测）
3. 买点判断（两步验证法、支撑位、止损位）
4. 基本面排雷（质押+盈余管理+四大审计风险矩阵）
5. 综合操作建议（买入/观望/不买、仓位、卖点预设）

注意：行情优先，先做技术分析（楚云风策略），再做基本面排雷。排雷是最后一道关。
"""


def generate_context(stock_code, days=120, price_mode="summary", include_prompt=True):
    # Fetch fundamental data
    fund_cols, fund_rows = fetch_fundamental_data(stock_code, days)
    # Fetch price data
    price_cols, price_rows = fetch_price_data(stock_code, days)

    # Format
    fund_text = format_fundamental(fund_cols, fund_rows, stock_code, days)
    price_text = format_price(price_cols, price_rows, stock_code, days, price_mode)

    # Combine — 行情优先，基本面排雷在后
    parts = [price_text, "", fund_text]

    if include_prompt:
        parts.append("")
        parts.append(ANALYSIS_PROMPT)

    return "\n".join(parts)


def generate_context_batch(stock_codes, days=120, price_mode="summary", include_prompt=True):
    results = {}
    for code in stock_codes:
        results[code] = generate_context(code, days, price_mode, include_prompt)
    return results


def quick_risk_check(stock_code):
    cols, rows = fetch_latest_fundamental(stock_code)
    if not rows:
        return None

    row = dict(zip(cols, rows[0]))
    pledge = _fmt_val(row.get("pledge_status"))
    em = _fmt_val(row.get("earnings_management_level"))
    big4 = _fmt_val(row.get("big4_audit"))
    pledge_ratio = _safe_float(row.get("pledge_ratio"))
    da = _safe_float(row.get("discretionary_accruals"))
    agency = _fmt_val(row.get("audit_agency"))

    level, level_name, reason = assess_risk(pledge, em, big4)
    red = is_red_alert(pledge, em, big4)
    green = is_green(pledge, em, big4)

    return {
        "stock": stock_code,
        "pledge_status": pledge,
        "pledge_ratio": pledge_ratio,
        "earnings_management": em,
        "discretionary_accruals": da,
        "big4_audit": big4,
        "audit_agency": agency,
        "risk_level": level,
        "risk_name": level_name,
        "risk_reason": reason,
        "is_red_alert": red,
        "is_green": green,
    }


def _fmt_val(val):
    if val is None or val == "" or (isinstance(val, float) and val != val):
        return "未知"
    return str(val)


def _safe_float(val, default=0.0):
    if val is None or val == "" or (isinstance(val, float) and val != val):
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default
