"""
Price data formatter - 120 days of stock_info with all 21 columns.
Supports two modes: 'summary' (compact) and 'full' (complete table).
"""

from datetime import datetime, timedelta


def _safe_float(val, default=0.0):
    if val is None or val == "" or (isinstance(val, float) and val != val):
        return default
    try:
        return float(val)
    except (ValueError, TypeError):
        return default


def _fmt_date(d):
    if hasattr(d, "strftime"):
        return d.strftime("%Y-%m-%d")
    return str(d)[:10]


def _fmt_short_date(d):
    if hasattr(d, "strftime"):
        return d.strftime("%m-%d")
    return str(d)[5:10]


def _fmt_vol(v):
    v = _safe_float(v)
    if v >= 1e8:
        return f"{v/1e8:.2f}亿"
    if v >= 1e4:
        return f"{v/1e4:.2f}万"
    return f"{v:.0f}"


def _fmt_price(p):
    p = _safe_float(p)
    return f"{p:.2f}"


def _fmt_pct(p):
    p = _safe_float(p)
    if p >= 0:
        return f"+{p:.2f}%"
    return f"{p:.2f}%"


def _is_new_week(curr_date, prev_date):
    if prev_date is None:
        return True
    try:
        if hasattr(curr_date, "isocalendar"):
            return curr_date.isocalendar()[1] != prev_date.isocalendar()[1]
        d1 = datetime.strptime(str(curr_date)[:10], "%Y-%m-%d")
        d2 = datetime.strptime(str(prev_date)[:10], "%Y-%m-%d")
        return d1.isocalendar()[1] != d2.isocalendar()[1]
    except Exception:
        return False


def format_price(columns, rows, stock_code, days=120, mode="summary"):
    if not rows:
        return _empty_price(stock_code)

    data = [dict(zip(columns, r)) for r in rows]
    data.sort(key=lambda x: str(x.get("trade_date", "")))
    data = data[-days:] if len(data) > days else data

    total = len(data)
    first = data[0]
    last = data[-1]

    lines = []
    lines.append("=" * 60)
    lines.append("行情数据")
    lines.append("=" * 60)
    lines.append(f"股票: {stock_code}")
    lines.append(f"周期: {_fmt_date(first['trade_date'])} ~ {_fmt_date(last['trade_date'])} ({total}天)")

    if mode == "full":
        lines.extend(_format_full_table(data))
    else:
        lines.extend(_format_summary(data))

    return "\n".join(lines)


def _format_summary(data):
    lines = []
    total = len(data)

    # --- Period Statistics ---
    lines.append("")
    lines.append("--- 区间统计 ---")

    closes = [_safe_float(d.get("close")) for d in data]
    highs = [_safe_float(d.get("high")) for d in data]
    lows = [_safe_float(d.get("low")) for d in data]
    vols = [_safe_float(d.get("vol")) for d in data]
    amounts = [_safe_float(d.get("amount")) for d in data]

    max_high = max(highs)
    min_low = min(lows)
    max_high_idx = highs.index(max_high)
    min_low_idx = lows.index(min_low)

    curr_close = _safe_float(data[-1].get("close"))
    first_close = _safe_float(data[0].get("close"))
    period_ret = ((curr_close - first_close) / first_close * 100) if first_close else 0

    avg_vol = sum(vols) / len(vols) if vols else 0
    avg_amt = sum(amounts) / len(amounts) if amounts else 0

    lines.append(f"  区间最高: {_fmt_price(max_high)} ({_fmt_short_date(data[max_high_idx]['trade_date'])})")
    lines.append(f"  区间最低: {_fmt_price(min_low)} ({_fmt_short_date(data[min_low_idx]['trade_date'])})")
    lines.append(f"  当前收盘: {_fmt_price(curr_close)}")
    lines.append(f"  区间涨跌: {_fmt_pct(period_ret)} (从{_fmt_price(first_close)})")
    lines.append(f"  日均成交量: {_fmt_vol(avg_vol)}")
    lines.append(f"  日均成交额: {_fmt_vol(avg_amt)}")

    # --- Chip Distribution ---
    lines.append("")
    lines.append("--- 筹码分布 ---")

    # Find latest row with actual chip data (cost_50pct may be NULL for recent dates)
    last = data[-1]
    chip_row = last
    if _safe_float(last.get("cost_50pct")) == 0 and _safe_float(last.get("winner_rate")) == 0:
        for d in reversed(data):
            if _safe_float(d.get("cost_50pct")) > 0 or _safe_float(d.get("winner_rate")) > 0:
                chip_row = d
                break
        if chip_row is not last:
            chip_date = _fmt_date(chip_row.get("trade_date"))
            lines.append(f"  (注: 筹码数据最新日期为 {chip_date})")

    c5 = _safe_float(chip_row.get("cost_5pct"))
    c15 = _safe_float(chip_row.get("cost_15pct"))
    c50 = _safe_float(chip_row.get("cost_50pct"))
    c85 = _safe_float(chip_row.get("cost_85pct"))
    c95 = _safe_float(chip_row.get("cost_95pct"))
    wavg = _safe_float(chip_row.get("weight_avg"))
    win_rate = _safe_float(chip_row.get("winner_rate"))
    cc90 = _safe_float(chip_row.get("cost_concentration_90pct"))
    his_lo = _safe_float(chip_row.get("his_low"))
    his_hi = _safe_float(chip_row.get("his_high"))

    lines.append(f"  成本分布: 5%={_fmt_price(c5)} | 15%={_fmt_price(c15)} | 50%={_fmt_price(c50)} | 85%={_fmt_price(c85)} | 95%={_fmt_price(c95)}")
    lines.append(f"  加权均价: {_fmt_price(wavg)}")
    lines.append(f"  获利比例: {win_rate:.1f}%")
    lines.append(f"  90%集中度: {cc90:.4f}")
    lines.append(f"  历史最高: {_fmt_price(his_hi)} | 历史最低: {_fmt_price(his_lo)}")

    # Chip trend (compare first available vs latest)
    first_chip = None
    for d in data:
        if _safe_float(d.get("cost_50pct")) > 0 or _safe_float(d.get("winner_rate")) > 0:
            first_chip = d
            break
    if first_chip is None:
        first_chip = data[0]
    first_cc90 = _safe_float(first_chip.get("cost_concentration_90pct"))
    first_win = _safe_float(first_chip.get("winner_rate"))
    first_date = _fmt_short_date(first_chip.get("trade_date"))
    cc90_trend = cc90 - first_cc90
    win_trend = win_rate - first_win

    lines.append(f"  筹码集中度变化: {first_cc90:.4f}({first_date}) -> {cc90:.4f} ({'上升' if cc90_trend > 0 else '下降'}{abs(cc90_trend):.4f})")
    lines.append(f"  获利比例变化: {first_win:.1f}%({first_date}) -> {win_rate:.1f}% ({'上升' if win_trend > 0 else '下降'}{abs(win_trend):.1f}%)")

    # --- Weekly Aggregates ---
    lines.append("")
    lines.append("--- 周线摘要 ---")

    weeks = []
    curr_week = []
    prev_date = None

    for d in data:
        dt = d.get("trade_date")
        if _is_new_week(dt, prev_date) and curr_week:
            weeks.append(curr_week)
            curr_week = []
        curr_week.append(d)
        prev_date = dt
    if curr_week:
        weeks.append(curr_week)

    week_num = 0
    for w in weeks:
        week_num += 1
        w_open = _safe_float(w[0].get("open"))
        w_high = max(_safe_float(d.get("high")) for d in w)
        w_low = min(_safe_float(d.get("low")) for d in w)
        w_close = _safe_float(w[-1].get("close"))
        w_vol = sum(_safe_float(d.get("vol")) for d in w)
        w_amt = sum(_safe_float(d.get("amount")) for d in w)
        w_pct = _safe_float(w[-1].get("pct_chg"))

        w_start = _fmt_short_date(w[0]["trade_date"])
        w_end = _fmt_short_date(w[-1]["trade_date"])

        lines.append(
            f"  W{week_num:02d} {w_start}~{w_end}  "
            f"O:{_fmt_price(w_open)} H:{_fmt_price(w_high)} "
            f"L:{_fmt_price(w_low)} C:{_fmt_price(w_close)}  "
            f"{_fmt_pct(w_pct)}  Vol:{_fmt_vol(w_vol)} Amt:{_fmt_vol(w_amt)}"
        )

    # --- Recent 10 Days Detailed ---
    lines.append("")
    lines.append(f"--- 最近{min(10, total)}天明细 ---")
    lines.append("  日期     开盘   最高   最低   收盘   涨跌%   成交量    成交额    C5%   C50%  C95%  均价  获利%  集中度")

    recent = data[-10:]
    day_idx = total - len(recent)
    for d in recent:
        day_idx += 1
        lines.append(_format_detail_row(d, day_idx))

    return lines


def _fmt_or_dash(val):
    if val is None or (isinstance(val, float) and val != val):
        return "-"
    try:
        return f"{float(val):.2f}"
    except (ValueError, TypeError):
        return "-"


def _fmt_pct_or_dash(val):
    if val is None or (isinstance(val, float) and val != val):
        return "  -   "
    v = float(val)
    return f"+{v:.2f}%" if v >= 0 else f"{v:.2f}%"


def _format_detail_row(d, day_idx):
    dt = _fmt_short_date(d.get("trade_date"))
    o = _fmt_price(d.get("open"))
    h = _fmt_price(d.get("high"))
    lo = _fmt_price(d.get("low"))
    c = _fmt_price(d.get("close"))
    pct = _fmt_pct(d.get("pct_chg"))
    vol = _fmt_vol(d.get("vol"))
    amt = _fmt_vol(d.get("amount"))
    c5 = _fmt_or_dash(d.get("cost_5pct"))
    c50 = _fmt_or_dash(d.get("cost_50pct"))
    c95 = _fmt_or_dash(d.get("cost_95pct"))
    wavg = _fmt_or_dash(d.get("weight_avg"))
    win = _fmt_or_dash(d.get("winner_rate"))
    cc = d.get("cost_concentration_90pct")
    cc_str = f"{float(cc):.3f}" if cc is not None else "  -  "

    return (
        f"  {dt} {o:>6} {h:>6} {lo:>6} {c:>6} {pct:>7}  "
        f"{vol:>8} {amt:>8}  {c5:>5} {c50:>5} {c95:>5} {wavg:>5} {win:>5}% {cc_str}"
    )


def _format_full_table(data):
    lines = []
    total = len(data)

    lines.append("")
    lines.append(f"--- 完整{total}天数据 ---")
    header = (
        f"  {'日期':10s} {'开':>6s} {'高':>6s} {'低':>6s} {'收':>6s} "
        f"{'前收':>6s} {'涨跌':>6s} {'涨跌%':>7s} "
        f"{'成交量':>8s} {'成交额':>8s} "
        f"{'C5%':>6s} {'C15%':>6s} {'C50%':>6s} {'C85%':>6s} {'C95%':>6s} "
        f"{'均价':>6s} {'获利%':>6s} {'历史低':>6s} {'历史高':>6s} {'集中度':>6s}"
    )
    lines.append(header)
    lines.append("  " + "-" * (len(header) - 2))

    for i, d in enumerate(data):
        dt = _fmt_short_date(d.get("trade_date"))
        row = (
            f"  {dt:10s} "
            f"{_fmt_price(d.get('open')):>6s} {_fmt_price(d.get('high')):>6s} "
            f"{_fmt_price(d.get('low')):>6s} {_fmt_price(d.get('close')):>6s} "
            f"{_fmt_price(d.get('pre_close')):>6s} {_fmt_price(d.get('change')):>6s} "
            f"{_fmt_pct(d.get('pct_chg')):>7s} "
            f"{_fmt_vol(d.get('vol')):>8s} {_fmt_vol(d.get('amount')):>8s} "
            f"{_fmt_or_dash(d.get('cost_5pct')):>6s} {_fmt_or_dash(d.get('cost_15pct')):>6s} "
            f"{_fmt_or_dash(d.get('cost_50pct')):>6s} {_fmt_or_dash(d.get('cost_85pct')):>6s} "
            f"{_fmt_or_dash(d.get('cost_95pct')):>6s} "
            f"{_fmt_or_dash(d.get('weight_avg')):>6s} "
            f"{_fmt_or_dash(d.get('winner_rate')):>5s}% "
            f"{_fmt_or_dash(d.get('his_low')):>6s} {_fmt_or_dash(d.get('his_high')):>6s} "
            f"{_fmt_or_dash(d.get('cost_concentration_90pct')):>6s}"
        )
        lines.append(row)

    return lines


def _empty_price(stock_code):
    lines = []
    lines.append("=" * 60)
    lines.append("行情数据")
    lines.append("=" * 60)
    lines.append(f"股票: {stock_code}")
    lines.append("数据: 暂不可用")
    return "\n".join(lines)
