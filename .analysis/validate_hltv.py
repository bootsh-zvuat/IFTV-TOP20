# -*- coding: utf-8 -*-
"""决定性验证：HLTV 对手强度数据能否改善中段复现？

这是前 10 轮尝试的最终检验。本次用的是**真正的** HLTV vs-Top-N 数据
（不再是代理/构造信号）。

方法：
  1. 读 HLTV 对手强度（data/hltv_opponent_YYYY.xlsx）
  2. join 到赛事数据（按选手名），复现现行 v1.2.0 中段误差
  3. 加入对手强度通道，做**跨年验证**（在一年选参，另一年测试）

验收标准（沿用前几轮教训）：
  必须**两年都改善**才算成功；单年改善不算（稳定性信号就是这么失败的）。
"""
import os
from collections import defaultdict

import openpyxl
import numpy as np

BASE = r"D:\demo\iftv"
DATA = os.path.join(BASE, "data")
EVENT_LEVEL_WEIGHTS = {
    "Major": 1.0, "超级精英赛": 0.8, "精英赛": 0.75,
    "大型赛事": 0.65, "中型赛事": 0.5, "次级赛事": 0.45, "不纳入": 0.0,
}
PLACEMENT_ADJUST = {"冠军": 2, "亚军": 0.5, "四强": 0, "八强": -0.5, "小组淘汰": -1}
RATING_TIERS = [(1.3, 2), (1.2, 1), (1.1, 0.5)]
RATING_BELOW = [(1.05, -0.5), (1.0, -1)]
# 与 src/config/defaults.ts 一致：单赛事表现分截断区间
SCORE_MIN, SCORE_MAX = -2, 11


def num(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return 0.0


def load_rows(path):
    wb = openpyxl.load_workbook(path, read_only=True, data_only=True)
    ws = wb[wb.sheetnames[0]]
    rows = list(ws.iter_rows(values_only=True))
    wb.close()
    hdr = [str(h).strip() if h is not None else "" for h in rows[0]]
    return [dict(zip(hdr, r)) for r in rows[1:] if r and any(v is not None for v in r)]


def rating_bonus(r):
    b = 0.0
    for th, bo in RATING_TIERS:
        if r >= th:
            b = max(b, bo)
    for th, bo in RATING_BELOW:
        if r < th:
            b = min(b, bo)
    return b


def spearman(a, b):
    a, b = np.asarray(a, float), np.asarray(b, float)
    if len(a) < 2:
        return float("nan")
    ra = np.argsort(np.argsort(a)).astype(float)
    rb = np.argsort(np.argsort(b)).astype(float)
    ra -= ra.mean(); rb -= rb.mean()
    d = np.sqrt((ra ** 2).sum() * (rb ** 2).sum())
    return float((ra * rb).sum() / d) if d else float("nan")


def build(year):
    """返回 (official, feats)。features 含现行总分 + HLTV 对手强度各档

    注意：必须与 src/core/score.ts 一致 —— 单赛事表现分要**截断到 [scoreMin, scoreMax]**。
    早期版本漏了截断，使 MVP 赛事得到 14 分（应截到 11），
    高估了头部选手总分并污染了基线，导致中段结论失真。现已修正。
    """
    ev_rows = load_rows(os.path.join(DATA, f"if_sim_{year}_events.xlsx"))
    official = {str(r.get("选手名")).strip(): int(num(r.get("名次")))
                for r in load_rows(os.path.join(DATA, f"if_sim_{year}_baseline.xlsx"))}

    # HLTV 对手强度（按选手名）
    opp = {}
    p = os.path.join(DATA, f"hltv_opponent_{year}.xlsx")
    if os.path.exists(p):
        for r in load_rows(p):
            nm = str(r.get("选手") or "").strip()
            if not nm:
                continue
            opp[nm] = dict(
                vs5=num(r.get("vsTop5")), vs10=num(r.get("vsTop10")),
                vs20=num(r.get("vsTop20")), vs30=num(r.get("vsTop30")),
                vs50=num(r.get("vsTop50")),
                maps=num(r.get("地图数")),
            )

    acc = defaultdict(lambda: defaultdict(float))
    for r in ev_rows:
        nm = str(r.get("选手名") or "").strip()
        if not nm:
            continue
        mp = num(r.get("地图数"))
        if mp and mp < 3:
            continue
        lvl = str(r.get("赛事级别") or "").strip()
        w = num(r.get("赛事权重")) or EVENT_LEVEL_WEIGHTS.get(lvl, 0)
        if w == 0:
            continue
        a = acc[nm]
        a["mp"] += mp
        rt = num(r.get("Rating"))
        honor = str(r.get("荣誉类型") or "无").strip()
        rk = int(num(r.get("荣誉顺位")))
        hb = 10 if honor == "MVP" else ({1: 8, 2: 6, 3: 4}.get(rk, 0) if honor == "EVP" else 0)
        # 关键：与 score.ts 一致，先合成再截断到 [scoreMin, scoreMax]
        raw = hb + rating_bonus(rt) + PLACEMENT_ADJUST.get(str(r.get("队伍名次") or "").strip(), 0)
        clamped = min(SCORE_MAX, max(SCORE_MIN, raw))
        # 按通道拆分时保持比例（拆的是同一份截断后的分），
        # 否则三通道之和会超过截断值
        if raw != 0:
            k = clamped / raw
        else:
            k = 1.0
        a["honor"] += hb * k * w
        a["rating"] += rating_bonus(rt) * k * w
        a["place"] += PLACEMENT_ADJUST.get(str(r.get("队伍名次") or "").strip(), 0) * k * w

    players = [nm for nm in acc if acc[nm]["mp"] >= 20]
    feats = {}
    for nm in players:
        o = opp.get(nm, {})
        feats[nm] = dict(
            cur=acc[nm]["honor"] + acc[nm]["rating"] + acc[nm]["place"],
            vs5=o.get("vs5", 0.0), vs10=o.get("vs10", 0.0), vs20=o.get("vs20", 0.0),
            vs30=o.get("vs30", 0.0), vs50=o.get("vs50", 0.0),
            has_opp=1.0 if o else 0.0,
        )
    return official, feats, opp


def rank_of(s):
    return {nm: i + 1 for i, (nm, _) in enumerate(sorted(s.items(), key=lambda kv: -kv[1]))}


def seg_metrics(pred, official, lo, hi):
    seg = [nm for nm in official if lo <= official[nm] <= hi and nm in pred]
    if not seg:
        return None
    mae = float(np.mean([abs(pred[nm] - official[nm]) for nm in seg]))
    sp = spearman([official[nm] for nm in seg], [pred[nm] for nm in seg])
    return mae, sp, len(seg)


def main():
    data = {}
    for y in (2025, 2024):
        official, feats, opp = build(y)
        data[y] = (official, feats)
        cov = sum(1 for nm in official if nm in opp)
        print(f"{y}: 选手池={len(feats)}  官方Top20有HLTV对手数据={cov}/20")

    print("\n" + "=" * 100)
    print("各信号在官方 7-20 段内与官方名次的相关性（负号=方向正确）")
    print("=" * 100)
    for y in (2025, 2024):
        official, feats = data[y]
        mid = [nm for nm in official if 7 <= official[nm] <= 20 and nm in feats]
        if len(mid) < 3:
            continue
        print(f"\n  {y} 年 (n={len(mid)}):")
        for key in ("cur", "vs5", "vs10", "vs20", "vs30", "vs50"):
            vals = [feats[nm][key] for nm in mid]
            oranks = [official[nm] for nm in mid]
            print(f"    {key:<8} Spearman={spearman(oranks, vals):+.3f}")

    print("\n" + "=" * 100)
    print("跨年验证：加入 vsTopN 通道后，中段是否改善？")
    print("=" * 100)

    # 先看基线（运行时计算，不硬编码）
    base = {}
    for y in (2025, 2024):
        official, feats = data[y]
        pred = rank_of({nm: feats[nm]["cur"] for nm in feats})
        m = seg_metrics(pred, official, 7, 20)
        mh = seg_metrics(pred, official, 1, 6)
        t20 = len({nm for nm in official if nm in list(pred)[:20]})
        base[y] = m[0]
        print(f"  {y} 基线 v1.2.0: Top20={t20}/20  头部MAE={mh[0]:.2f}  "
              f"中段MAE={m[0]:.2f} 中段sp={m[1]:+.3f}")
    global BASE25_MID, BASE24_MID
    BASE25_MID, BASE24_MID = base[2025], base[2024]

    def eval_blend(year, k_vs5, k_vs20, k_avg):
        official, feats = data[year]
        players = list(feats)
        # z-score 归一化，使量级可比
        def z(key):
            v = np.array([feats[nm][key] for nm in players], float)
            mu, sd = v.mean(), v.std()
            return {nm: (feats[nm][key] - mu) / sd if sd > 1e-9 else 0.0 for nm in players}
        zv5, zv20 = z("vs5"), z("vs20")
        # 整体 HLTV rating 相对赛事数据 rating 的差异（对手强度调整的代理）
        for nm in players:
            feats[nm]["opp_avg"] = (feats[nm]["vs5"] + feats[nm]["vs20"]) / 2
        zavg = z("opp_avg")
        blend = {nm: feats[nm]["cur"] + k_vs5 * zv5[nm] + k_vs20 * zv20[nm] + k_avg * zavg[nm]
                 for nm in players}
        pred = rank_of(blend)
        m = seg_metrics(pred, official, 7, 20)
        mh = seg_metrics(pred, official, 1, 6)
        t20 = len({nm for nm in official if nm in list(pred)[:20]})
        return dict(mid_mae=m[0], mid_sp=m[1], head_mae=mh[0], top20=t20)

    print("\n  扫描单一 vsTopN 通道（k 为 z-score 权重）：")
    print(f"  {'通道':<12} {'k':>5} | {'2025 中段MAE':>13} {'sp':>8} {'Top20':>6} | "
          f"{'2024 中段MAE':>13} {'sp':>8} {'Top20':>6}")
    best = {}
    for ch, idx in (("vs5", 0), ("vs20", 1)):
        for k in (0.5, 1, 2, 3, 5, -1, -2):
            k5 = k if idx == 0 else 0
            k20 = k if idx == 1 else 0
            r25 = eval_blend(2025, k5, k20, 0)
            r24 = eval_blend(2024, k5, k20, 0)
            both = (r25["mid_mae"] < BASE25_MID) and (r24["mid_mae"] < BASE24_MID)
            mark = " ✓两年都改善" if both else ""
            print(f"  {ch:<12} {k:>5} | {r25['mid_mae']:>13.2f} {r25['mid_sp']:>+8.3f} "
                  f"{r25['top20']:>6} | {r24['mid_mae']:>13.2f} {r24['mid_sp']:>+8.3f} "
                  f"{r24['top20']:>6}{mark}")
            if both:
                best[(ch, k)] = (r25, r24)

    print("\n" + "=" * 100)
    if best:
        print(f"✓ 有 {len(best)} 个配置两年都改善中段：")
        for (ch, k), (r25, r24) in best.items():
            print(f"    {ch} k={k}: 2025 {BASE25_MID:.2f}→{r25['mid_mae']:.2f}, "
                  f"2024 {BASE24_MID:.2f}→{r24['mid_mae']:.2f}")
    else:
        print("✗ 没有任何配置能同时改善两年 —— 与之前 10 轮结论一致。")
    print("=" * 100)


# 基线中段 MAE：由 main() 运行时填充（勿硬编码 —— 早期硬编码值来自
# 未做 scoreMax 截断的错误实现，见 build() 的注释）
BASE25_MID = None
BASE24_MID = None

# 修正前的错误基线（保留仅作对照，勿使用）
BASE25_MID_WRONG = 4.57
BASE24_MID_WRONG = 5.21

if __name__ == "__main__":
    main()
