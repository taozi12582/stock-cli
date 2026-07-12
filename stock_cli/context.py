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


ANALYSIS_PROMPT = """=== 分析任务 ===

你是A股趋势分析agent，擅长结合基本面维度与行情时序数据预测股票趋势。

### 第1步：基本面信号识别
从基本面上下文中提取关键信号：
1. 质押状态：当前是质押中/刚解押/未质押？120天内是否发生过解押事件？
   - 刚解押 = 暴跌风险预警信号（谢德仁论文：质押期靠盈余操纵维稳股价，解押后维稳动力消失，风险释放）
2. 盈余管理程度：当前处于高/中/低？120天内是否恶化（从低->中->高）？
   - 高盈余管理 = 信息不透明 = 暴跌前兆（潘越论文：不透明度系数1.13，1%显著）
3. 四大审计：是否由四大审计？
   - 非四大 = 信息质量保障弱（辛清泉论文：四大审计->股价波动性更低）

### 第2步：暴跌风险矩阵评估
根据3维度组合评估当前暴跌风险：

| 组合 | 风险等级 | 说明 |
|---|---|---|
| 刚解押 + 高盈余管理 + 非四大 | ★★★★★ 极高 | 三重风险叠加 |
| 刚解押 + (高盈余管理 或 非四大) | ★★★★ 高 | 解押风险叠加信息质量差 |
| 质押中 + 高盈余管理 | ★★★ 高 | 维稳不可持续，盈余操纵积累风险 |
| 质押中 + 非四大 | ★★★ 高 | 信息质量无保障 |
| 刚解押 | ★★★ 中高 | 解押后崩盘风险显著上升 |
| 高盈余管理 + 非四大 | ★★★ 中高 | 信息不透明+无审计保障 |
| 未质押 + 低盈余管理 + 四大 | ★☆ 极低 | 信息环境良好 |

### 第3步：行情趋势分析
结合120天行情数据（OHLCV、筹码集中度等）：
1. 当前处于什么技术形态？（上升/下降/震荡/底部/顶部）
2. 量价关系是否健康？
3. 筹码集中度变化趋势如何？（集中度上升=筹码集中，下降=筹码分散）
4. 获利比例变化趋势如何？（高位获利盘多=抛压大）
5. 成交量是否有异常（突然放大或萎缩）？

### 第4步：综合趋势判断
- 基本面风险高 + 技术面走弱 -> 看跌或暴跌风险
- 基本面风险高 + 技术面尚可 -> 警惕滞涨后补跌
- 基本面良好 + 技术面走强 -> 看涨
- 基本面良好 + 技术面走弱 -> 可能是买入机会
- 刚解押 + 技术面横盘 -> 警惕"暴风雨前的平静"

### 第5步：输出结论

【趋势判断】
- 未来5-10天趋势：看涨/看跌/震荡/暴跌风险
- 置信度：高/中/低
- 核心依据：（1-2句话说明最关键的判断依据）

【基本面风险】
- 当前风险等级：★★★（1-5星）
- 主要风险点：
- 需要持续监控的信号：

【操作建议】
- 建议操作：买入/持有/减仓/清仓/观望
- 建议止损位：（具体价格）
- 关键观察点：（未来几天需要关注的指标或事件）

【时序数据观察要点】
- 120天行情中最值得注意的3个异常点：
- 这些异常与基本面变化的关联：
"""


def generate_context(stock_code, days=120, price_mode="summary", include_prompt=True):
    # Fetch fundamental data
    fund_cols, fund_rows = fetch_fundamental_data(stock_code, days)
    # Fetch price data
    price_cols, price_rows = fetch_price_data(stock_code, days)

    # Format
    fund_text = format_fundamental(fund_cols, fund_rows, stock_code, days)
    price_text = format_price(price_cols, price_rows, stock_code, days, price_mode)

    # Combine
    parts = [fund_text, "", price_text]

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
