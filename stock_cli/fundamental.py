"""
Fundamental context formatter - 3-layer compressed context.
Dimensions: pledge_status, earnings_management_level, big4_audit.
"""

from stock_cli.risk import assess_risk, risk_label


def _fmt(val):
    if val is None or val == "" or (isinstance(val, float) and val != val):
        return "未知"
    return str(val)


def _fmt_date(d):
    if hasattr(d, "strftime"):
        return d.strftime("%Y-%m-%d")
    return str(d)[:10]


def _fmt_short_date(d):
    if hasattr(d, "strftime"):
        return d.strftime("%m-%d")
    return str(d)[5:10]


def _safe_float(val, default=0.0):
    if val is None or val == "" or (isinstance(val, float) and val != val):
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


def format_fundamental(columns, rows, stock_code, days=120):
    if not rows:
        return _empty_context(stock_code)

    # Build row dicts
    data = [dict(zip(columns, r)) for r in rows]
    # Sort by trade_date ascending, take last N days
    data.sort(key=lambda x: str(x.get("trade_date", "")))
    data = data[-(days * 2):]  # fundamental has fewer rows, take extra then trim
    data = data[-days:] if len(data) > days else data

    first = data[0]
    last = data[-1]
    total = len(data)

    start_date = _fmt_date(first.get("trade_date"))
    end_date = _fmt_date(last.get("trade_date"))

    lines = []
    lines.append("=" * 60)
    lines.append("基本面上下文")
    lines.append("=" * 60)
    lines.append(f"股票: {stock_code}")
    lines.append(f"周期: {start_date} ~ {end_date} ({total}个交易日)")

    # --- Layer 1: Static Background ---
    lines.append("")
    lines.append("--- 第1层: 静态背景 ---")

    big4 = _fmt(last.get("big4_audit"))
    agency = _fmt(last.get("audit_agency"))
    if big4 != "未知" and agency != "未知":
        lines.append(f"四大审计: {big4} ({agency})")
    else:
        lines.append(f"四大审计: {big4}")

    em_level = _fmt(last.get("earnings_management_level"))
    da_val = _safe_float(last.get("discretionary_accruals"))
    if em_level != "未知" and da_val != 0:
        lines.append(f"盈余管理: {em_level} (不透明度={da_val:.4f})")
    else:
        lines.append(f"盈余管理: {em_level}")

    pledge = _fmt(last.get("pledge_status"))
    pledge_ratio = _safe_float(last.get("pledge_ratio"))
    if pledge != "未知" and pledge_ratio > 0:
        lines.append(f"质押状态: {pledge} ({pledge_ratio:.1f}%)")
    else:
        lines.append(f"质押状态: {pledge}")

    # --- Layer 2: Dynamic Changes ---
    lines.append("")
    lines.append(f"--- 第2层: 变化记录 ({total}天内) ---")

    change_count = 0
    for i in range(1, len(data)):
        prev = data[i - 1]
        curr = data[i]
        changes = []

        # Pledge changes
        prev_p = _fmt(prev.get("pledge_status"))
        curr_p = _fmt(curr.get("pledge_status"))
        if prev_p != "未知" and curr_p != "未知" and prev_p != curr_p:
            prev_r = _safe_float(prev.get("pledge_ratio"))
            curr_r = _safe_float(curr.get("pledge_ratio"))
            if prev_p != "未质押" and curr_p == "未质押":
                changes.append(f"质押 {prev_p}({prev_r:.1f}%) -> 刚解押")
            elif prev_p == "未质押" and curr_p != "未质押":
                changes.append(f"质押 未质押 -> {curr_p}({curr_r:.1f}%)")
            else:
                changes.append(f"质押 {prev_p}({prev_r:.1f}%) -> {curr_p}({curr_r:.1f}%)")

        # Earnings management changes
        prev_em = _fmt(prev.get("earnings_management_level"))
        curr_em = _fmt(curr.get("earnings_management_level"))
        if prev_em != "未知" and curr_em != "未知" and prev_em != curr_em:
            changes.append(f"盈余管理 {prev_em} -> {curr_em}")

        # Big4 changes
        prev_b = _fmt(prev.get("big4_audit"))
        curr_b = _fmt(curr.get("big4_audit"))
        if prev_b != "未知" and curr_b != "未知" and prev_b != curr_b:
            changes.append(f"审计 {prev_b} -> {curr_b}")

        if changes:
            day_num = i + 1
            d_str = _fmt_short_date(curr.get("trade_date"))
            lines.append(f"  [第{day_num}天 {d_str}] {' | '.join(changes)}")
            change_count += 1

    # Current status line
    d_str = _fmt_short_date(last.get("trade_date"))
    lines.append(
        f"  [第{total}天 {d_str}(当前)] "
        f"质押:{pledge} | 盈余管理:{em_level} | 四大:{big4}"
    )
    lines.append(f"  ({total}天内共{change_count}条变化)")

    # --- Layer 3: Summary + Risk Assessment ---
    lines.append("")
    lines.append("--- 第3层: 关键事件 + 风险评估 ---")

    events = []

    # Detect pledge release events
    for i in range(1, len(data)):
        prev_p = _fmt(data[i - 1].get("pledge_status"))
        curr_p = _fmt(data[i].get("pledge_status"))
        if prev_p != "未质押" and curr_p == "未质押":
            day_num = i + 1
            d_str = _fmt_short_date(data[i].get("trade_date"))
            events.append(
                f"  第{day_num}天({d_str}): 质押解押 -> 崩盘风险预警"
                f"(谢德仁论文:解押后风险显著上升)"
            )

    # Detect EM deterioration
    em_order = ["低", "中", "高"]
    for i in range(1, len(data)):
        prev_em = _fmt(data[i - 1].get("earnings_management_level"))
        curr_em = _fmt(data[i].get("earnings_management_level"))
        if prev_em in em_order and curr_em in em_order:
            if em_order.index(curr_em) > em_order.index(prev_em):
                day_num = i + 1
                d_str = _fmt_short_date(data[i].get("trade_date"))
                events.append(
                    f"  第{day_num}天({d_str}): 盈余管理{prev_em}->{curr_em}"
                    f"(潘越论文:不透明度上升->暴跌风险增大)"
                )

    if not events:
        lines.append("  120天内无重大基本面变化")
    else:
        for e in events:
            lines.append(e)

    # Risk assessment
    level, level_name, reason = assess_risk(pledge, em_level, big4)
    lines.append(f"  当前风险等级: {risk_label(level)}")
    lines.append(f"  评估依据: {reason}")

    return "\n".join(lines)


def _empty_context(stock_code):
    lines = []
    lines.append("=" * 60)
    lines.append("基本面上下文")
    lines.append("=" * 60)
    lines.append(f"股票: {stock_code}")
    lines.append("数据: 暂不可用 (可能尚未回填)")
    return "\n".join(lines)
