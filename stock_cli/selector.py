"""
选股编排器 - 初筛 → 分批 → 子agent prompt生成

流程:
  1. 运行screener初筛，获取候选股
  2. 将候选股分成N批
  3. 为每批生成一个子agent的完整prompt
  4. 主agent读取输出后，启动N个子agent并行分析
  5. 每个子agent对分到的股票执行 context + SKILL.md分析
  6. 主agent汇总结果

用法:
  python3 -m stock_cli select --top-n 50 --agents 10
  python3 -m stock_cli select --top-n 30 --agents 5 --format json
"""

import json
import sys

from stock_cli.screener import run_screener


SUB_AGENT_PROMPT_TEMPLATE = """你是A股分析子agent（批次 {batch_id}/{total_batches}）。

请对以下 {stock_count} 只股票逐一分析：

{stock_list}

对每只股票执行以下操作：

1. 获取上下文数据（对每只股票都执行）：
   python3 -m stock_cli context <股票代码> --days 120

2. 按stock-analysis Skill的5步框架分析（见 ~/.agents/skills/stock-analysis/SKILL.md）：
   - 第1步：趋势判断（MA10/MA30、相对强弱、当前位置）
   - 第2步：形态识别（强势股回调形态、企稳信号检测）
   - 第3步：买点判断（两步验证法、支撑位、止损位）
   - 第4步：基本面排雷（质押+盈余管理+四大审计风险矩阵）
   - 第5步：综合操作建议（买入/观望/不买、仓位、卖点预设）

   注意：行情优先，先做技术分析（楚云风策略），再做基本面排雷。

3. 对每只股票返回以下结构化结果：
   股票代码: XXXXXX.XX
   趋势: 上升/下降/震荡
   形态: 强势股回调/非目标形态
   企稳信号: XXX / 无
   买点: 成立/不成立
   基本面风险: ★~★★★★★
   操作建议: 买入/观望/不买
   买入价: XX元
   止损位: XX元
   目标价: XX元
   关键说明: 一句话总结

请务必对批次中的每一只股票都给出分析结果。"""


def run_select(
    top_n=50,
    agents=10,
    min_amount=2.0,
    max_pullback=0.382,
    min_uptrend_gain=0.15,
    min_history_days=60,
    fundamental_filter=True,
    format="text",
):
    """运行选股编排：初筛 → 分批 → 输出子agent prompt"""

    # Step 1: Run screener (quiet mode)
    candidates = run_screener(
        min_amount=min_amount,
        max_pullback=max_pullback,
        min_uptrend_gain=min_uptrend_gain,
        min_history_days=min_history_days,
        fundamental_filter=fundamental_filter,
        top_n=top_n,
        quiet=(format == "json"),
    )

    if not candidates:
        if format == "json":
            print(json.dumps({"error": "no candidates"}, ensure_ascii=False))
        else:
            print("初筛无候选股")
        return

    stock_codes = [c["ts_code"] for c in candidates]

    # Step 2: Split into batches
    n_batches = min(agents, len(stock_codes))
    batch_size = (len(stock_codes) + n_batches - 1) // n_batches

    batches = []
    for i in range(n_batches):
        start = i * batch_size
        end = start + batch_size
        batch_stocks = stock_codes[start:end]
        if not batch_stocks:
            break

        prompt = SUB_AGENT_PROMPT_TEMPLATE.format(
            batch_id=i + 1,
            total_batches=n_batches,
            stock_count=len(batch_stocks),
            stock_list="\n".join(f"  - {code}" for code in batch_stocks),
        )

        batches.append({
            "batch_id": i + 1,
            "stock_count": len(batch_stocks),
            "stocks": batch_stocks,
            "prompt": prompt,
        })

    # Step 3: Output
    if format == "json":
        output = {
            "total_candidates": len(candidates),
            "total_batches": len(batches),
            "screener_summary": {
                "latest_date": candidates[0].get("latest_date") if candidates else None,
            },
            "candidates": [
                {
                    "ts_code": c["ts_code"],
                    "close": c.get("close"),
                    "ret_20d": c.get("ret_20d"),
                    "pullback_depth": c.get("pullback_depth"),
                    "pullback_ratio": c.get("pullback_ratio"),
                    "uptrend_gain": c.get("uptrend_gain"),
                    "vol_shrink": c.get("vol_shrink"),
                    "stabilization": c.get("stabilization"),
                    "pledge_status": c.get("pledge_status"),
                    "em_level": c.get("em_level"),
                    "big4": c.get("big4"),
                }
                for c in candidates
            ],
            "batches": batches,
        }
        print(json.dumps(output, ensure_ascii=False, indent=2))
    else:
        print(f"\n{'='*60}")
        print(f"编排方案: {len(candidates)} 只候选股 → {len(batches)} 个子agent并行")
        print(f"{'='*60}\n")

        print("候选股列表:")
        for i, c in enumerate(candidates, 1):
            print(f"  {i:3d}. {c['ts_code']:12s} "
                  f"20日涨幅={c['ret_20d']*100:>+6.1f}% "
                  f"回调={c['pullback_depth']*100:>5.1f}% "
                  f"企稳={c.get('stabilization','无'):20s}")

        print(f"\n{'='*60}")
        print("子agent批次分配:")
        print(f"{'='*60}\n")

        for b in batches:
            print(f"--- 批次 {b['batch_id']}/{len(batches)} ({b['stock_count']}只) ---")
            print(f"股票: {', '.join(b['stocks'])}")
            print()
            print("子agent prompt:")
            print(b["prompt"])
            print(f"\n{'─'*60}\n")
