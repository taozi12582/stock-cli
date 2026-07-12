"""
stock-cli: A股股票数据CLI工具
从MySQL获取stock_info(行情)和fundamental_info(基本面)数据，
生成可供LLM/子代理分析的压缩上下文。

用法:
  python3 -m stock_cli context 000001.SZ --days 120
  python3 -m stock_cli price 000001.SZ 600519.SH --mode full
  python3 -m stock_cli fundamental 000001.SZ
  python3 -m stock_cli risk 000001.SZ 600519.SH 000858.SZ
  python3 -m stock_cli screen --exclude-red --limit 50
  python3 -m stock_cli screener
"""

import argparse
import json
import sys

from stock_cli.context import generate_context, quick_risk_check
from stock_cli.db import (
    fetch_price_data,
    fetch_fundamental_data,
    fetch_stock_list_by_risk,
)
from stock_cli.fundamental import format_fundamental
from stock_cli.price import format_price
from stock_cli.risk import risk_label


def cmd_context(args):
    results = []
    for code in args.stocks:
        result = generate_context(
            code,
            days=args.days,
            price_mode=args.mode,
            include_prompt=not args.no_prompt,
        )
        results.append((code, result))
        print(result)
        if len(args.stocks) > 1:
            print("\n" + "=" * 80 + "\n")

    if args.output:
        with open(args.output, "w") as f:
            for code, result in results:
                f.write(f"# Stock: {code}\n")
                f.write(result)
                f.write("\n\n" + "=" * 80 + "\n\n")
        print(f"输出已写入 {args.output}", file=sys.stderr)


def cmd_fundamental(args):
    for code in args.stocks:
        cols, rows = fetch_fundamental_data(code, args.days)
        result = format_fundamental(cols, rows, code, args.days)
        print(result)
        if len(args.stocks) > 1:
            print()


def cmd_price(args):
    for code in args.stocks:
        cols, rows = fetch_price_data(code, args.days)
        result = format_price(cols, rows, code, args.days, args.mode)
        print(result)
        if len(args.stocks) > 1:
            print()


def cmd_risk(args):
    if args.format == "json":
        results = []
        for code in args.stocks:
            r = quick_risk_check(code)
            if r:
                results.append(r)
            else:
                results.append({"stock": code, "error": "no data"})
        print(json.dumps(results, ensure_ascii=False, indent=2))
        return

    for code in args.stocks:
        r = quick_risk_check(code)
        if not r:
            print(f"{code}: 无数据")
            continue

        flag = ""
        if r["is_red_alert"]:
            flag = " [红色警报]"
        elif r["is_green"]:
            flag = " [绿色安全]"

        print(f"{code}: {risk_label(r['risk_level'])}{flag}")
        print(f"  质押: {r['pledge_status']}" + (f" ({r['pledge_ratio']:.1f}%)" if r['pledge_ratio'] > 0 else ""))
        print(f"  盈余管理: {r['earnings_management']}" + (f" (DA={r['discretionary_accruals']:.4f})" if r['discretionary_accruals'] != 0 else ""))
        print(f"  四大: {r['big4_audit']}" + (f" ({r['audit_agency']})" if r['audit_agency'] != "未知" else ""))
        print(f"  依据: {r['risk_reason']}")
        if len(args.stocks) > 1:
            print()


def cmd_screen(args):
    cols, rows = fetch_stock_list_by_risk(
        exclude_red=args.exclude_red,
        green_only=args.green_only,
        limit=args.limit,
    )

    if not rows:
        print("没有找到符合条件的股票")
        return

    if args.format == "json":
        data = [dict(zip(cols, r)) for r in rows]
        print(json.dumps(data, ensure_ascii=False, indent=2, default=str))
        return

    print(f"共找到 {len(rows)} 只股票")
    print(f"{'股票代码':12s} {'质押状态':10s} {'质押%':>6s} {'盈余管理':8s} {'四大':4s} {'审计机构':20s}")
    print("-" * 70)

    for r in rows:
        row = dict(zip(cols, r))
        code = row.get("ts_code", "")
        pledge = _fmt(row.get("pledge_status"))
        ratio = _safe_float(row.get("pledge_ratio"))
        em = _fmt(row.get("earnings_management_level"))
        big4 = _fmt(row.get("big4_audit"))
        agency = _fmt(row.get("audit_agency"))

        ratio_str = f"{ratio:.1f}%" if ratio > 0 else "-"
        print(f"{code:12s} {pledge:10s} {ratio_str:>6s} {em:8s} {big4:4s} {agency:20s}")


def _fmt(val):
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


def cmd_screener(args):
    from stock_cli.screener import run_screener
    if args.format == "json":
        result = run_screener(
            min_amount=args.min_amount,
            max_pullback=args.max_pullback,
            min_uptrend_gain=args.min_uptrend_gain,
            min_history_days=args.min_history_days,
            fundamental_filter=not args.no_fundamental_filter,
            top_n=args.top_n,
            quiet=True,
        )
        import json as _json
        for c in result:
            c.pop("_recent_data", None)
        print(_json.dumps(result, ensure_ascii=False, indent=2, default=str))
    else:
        run_screener(
            min_amount=args.min_amount,
            max_pullback=args.max_pullback,
            min_uptrend_gain=args.min_uptrend_gain,
            min_history_days=args.min_history_days,
            fundamental_filter=not args.no_fundamental_filter,
            top_n=args.top_n,
        )


def cmd_select(args):
    from stock_cli.selector import run_select
    run_select(
        top_n=args.top_n,
        agents=args.agents,
        min_amount=args.min_amount,
        max_pullback=args.max_pullback,
        min_uptrend_gain=args.min_uptrend_gain,
        min_history_days=args.min_history_days,
        fundamental_filter=not args.no_fundamental_filter,
        format=args.format,
    )


def build_parser():
    parser = argparse.ArgumentParser(
        prog="stock-cli",
        description="A股股票数据CLI - 行情+基本面上下文生成器",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # 生成完整分析上下文（基本面+行情+分析prompt）
  python3 -m stock_cli context 000001.SZ --days 120

  # 多只股票批量生成
  python3 -m stock_cli context 000001.SZ 600519.SH 000858.SZ --output analysis.txt

  # 完整120天行情数据（所有21列）
  python3 -m stock_cli price 000001.SZ --mode full

  # 只看基本面风险
  python3 -m stock_cli fundamental 000001.SZ

  # 快速风险检查
  python3 -m stock_cli risk 000001.SZ 600519.SH 000858.SZ

  # 筛选绿色安全股
  python3 -m stock_cli screen --green-only --limit 50

  # 排除红色警报股
  python3 -m stock_cli screen --exclude-red --limit 100
""",
    )

    subparsers = parser.add_subparsers(dest="command", help="子命令")

    # context
    p_ctx = subparsers.add_parser("context", help="生成完整分析上下文（行情+基本面+prompt）")
    p_ctx.add_argument("stocks", nargs="+", help="股票代码（空格分隔）")
    p_ctx.add_argument("--days", type=int, default=120, help="天数（默认120）")
    p_ctx.add_argument("--mode", choices=["summary", "full"], default="summary",
                         help="行情模式: summary=摘要(默认), full=完整120天表格")
    p_ctx.add_argument("--no-prompt", action="store_true", help="不附加分析prompt")
    p_ctx.add_argument("--output", type=str, help="写入文件而非输出到终端")
    p_ctx.add_argument("--format", choices=["text", "json"], default="text")
    p_ctx.set_defaults(func=cmd_context)

    # fundamental
    p_fund = subparsers.add_parser("fundamental", help="只输出基本面数据")
    p_fund.add_argument("stocks", nargs="+", help="股票代码")
    p_fund.add_argument("--days", type=int, default=120, help="天数")
    p_fund.set_defaults(func=cmd_fundamental)

    # price
    p_price = subparsers.add_parser("price", help="只输出行情数据")
    p_price.add_argument("stocks", nargs="+", help="股票代码")
    p_price.add_argument("--days", type=int, default=120, help="天数")
    p_price.add_argument("--mode", choices=["summary", "full"], default="summary",
                          help="summary=摘要, full=完整表格")
    p_price.set_defaults(func=cmd_price)

    # risk
    p_risk = subparsers.add_parser("risk", help="快速基本面风险检查")
    p_risk.add_argument("stocks", nargs="+", help="股票代码")
    p_risk.add_argument("--format", choices=["text", "json"], default="text")
    p_risk.set_defaults(func=cmd_risk)

    # screen
    p_screen = subparsers.add_parser("screen", help="按基本面风险筛选股票")
    p_screen.add_argument("--exclude-red", dest="exclude_red", action="store_true",
                           default=True, help="排除红色警报股（默认开启）")
    p_screen.add_argument("--no-exclude-red", dest="exclude_red", action="store_false",
                           help="不排除红色警报股")
    p_screen.add_argument("--green-only", action="store_true",
                           help="只显示绿色安全股（未质押+低盈余管理+四大）")
    p_screen.add_argument("--limit", type=int, default=100, help="最大数量")
    p_screen.add_argument("--format", choices=["text", "json"], default="text")
    p_screen.set_defaults(func=cmd_screen)

    # screener
    p_scr = subparsers.add_parser("screener", help="楚云风选股初筛（强势股回调形态）")
    p_scr.add_argument("--min-amount", type=float, default=2.0,
                        help="最低日均成交额(亿)，默认2亿")
    p_scr.add_argument("--max-pullback", type=float, default=0.382,
                        help="最大回调比例(0-1)，默认0.382")
    p_scr.add_argument("--min-uptrend-gain", type=float, default=0.15,
                        help="前波上涨最低涨幅(0-1)，默认0.15")
    p_scr.add_argument("--min-history-days", type=int, default=60,
                        help="最低历史交易日数，默认60")
    p_scr.add_argument("--no-fundamental-filter", action="store_true",
                        help="跳过基本面排雷")
    p_scr.add_argument("--top-n", type=int, default=50, help="最多输出数量")
    p_scr.add_argument("--format", choices=["text", "json"], default="text",
                        help="输出格式")
    p_scr.set_defaults(func=cmd_screener)

    # select
    p_sel = subparsers.add_parser("select", help="选股编排（初筛→分批→子agent prompt）")
    p_sel.add_argument("--top-n", type=int, default=50, help="初筛最多输出数量")
    p_sel.add_argument("--agents", type=int, default=10, help="子agent数量，默认10")
    p_sel.add_argument("--min-amount", type=float, default=2.0,
                        help="最低日均成交额(亿)，默认2亿")
    p_sel.add_argument("--max-pullback", type=float, default=0.382,
                        help="最大回调比例(0-1)，默认0.382")
    p_sel.add_argument("--min-uptrend-gain", type=float, default=0.15,
                        help="前波上涨最低涨幅(0-1)，默认0.15")
    p_sel.add_argument("--min-history-days", type=int, default=60,
                        help="最低历史交易日数，默认60")
    p_sel.add_argument("--no-fundamental-filter", action="store_true",
                        help="跳过基本面排雷")
    p_sel.add_argument("--format", choices=["text", "json"], default="text",
                        help="输出格式: text=人类可读, json=机器可读")
    p_sel.set_defaults(func=cmd_select)

    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()

    if not hasattr(args, "func"):
        parser.print_help()
        sys.exit(1)

    try:
        args.func(args)
    except KeyboardInterrupt:
        print("\n中断", file=sys.stderr)
        sys.exit(130)
    except Exception as e:
        print(f"错误: {e}", file=sys.stderr)
        sys.exit(1)
