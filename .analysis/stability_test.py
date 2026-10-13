# -*- coding: utf-8 -*-
"""关键验证：稳定性信号能否改善中段？

前提问题：现有 if_sim_2025_events.xlsx **没有**稳定性列（采集管线刚改，尚未重跑）。
所以本脚本用两种方式验证：

  方式 A（代理验证）：用"每赛事 rating 的离散度"近似稳定性。
     即：某选手在多个赛事之间的 rating 波动。
     这不需要逐图数据，用现有列即可算 —— 若连它都没用，逐图 std 也难有用。

  方式 B（逐图验证）：实拉少量赛事，得到真实逐图 std，
     检验逐图 std 与"赛事间波动"是否一致（决定能否用 A 替代 B 做快速评估）。

重要：必须同时看中段 MAE 和 Top20 重叠，并两年交叉验证。
"""
import os
import sys
import importlib.util
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
    header = [str(h).strip() if h is not None else "" for h in rows[0]]
    return [dict(zip(header, r)) for r in rows[1:] if r and any(v is not None for v in r)]


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


def build(year, evf, blf):
    rows = load_rows(os.path.join(DATA, evf))
    official = {str(r.get("选手名")).strip(): int(num(r.get("名次")))
                for r in load_rows(os.path.join(DATA, blf))}
    acc = defaultdict(lambda: defaultdict(float))
    per_event_ratings = defaultdict(list)   # 选手在各赛事的 rating（用于赛事间波动）
    ratings = defaultdict(list)

    for r in rows:
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
        ratings[nm].append(rt)
        if rt > 0:
            per_event_ratings[nm].append((rt, w))
        honor = str(r.get("荣誉类型") or "无").strip()
        rk = int(num(r.get("荣誉顺位")))
        hb = 10 if honor == "MVP" else ({1: 8, 2: 6, 3: 4}.get(rk, 0) if honor == "EVP" else 0)
        a["honor"] += hb * w
        a["rating"] += rating_bonus(rt) * w
        a["place"] += PLACEMENT_ADJUST.get(str(r.get("队伍名次") or "").strip(), 0) * w

    players = [nm for nm in acc if acc[nm]["mp"] >= 20]
    out = {}
    for nm in players:
        vals = [x for x, _ in per_event_ratings[nm]]
        if len(vals) >= 2:
            # 赛事间 rating 标准差（加权近似）
            ws_ = [w for _, w in per_event_ratings[nm]]
            mu = sum(v * w for v, w in per_event_ratings[nm]) / sum(ws_)
            var = sum(w * (v - mu) ** 2 for v, w in per_event_ratings[nm]) / sum(ws_)
            std_between = var ** 0.5
            cv_between = std_between / mu if mu else 0.0
        else:
            std_between, cv_between = 0.0, 0.0
        out[nm] = dict(
            total=acc[nm]["honor"] + acc[nm]["rating"] + acc[nm]["place"],
            mp=acc[nm]["mp"],
            avg=float(np.mean(ratings[nm])) if ratings[nm] else 0.0,
            std_between=std_between, cv_between=cv_between,
            n_events=len([1 for _ in per_event_ratings[nm]]),
        )
    return official, out


def metrics(pred, official, lo, hi):
    seg = [nm for nm in official if lo <= official[nm] <= hi and nm in pred]
    if not seg:
        return None
    mae = float(np.mean([abs(pred[nm] - official[nm]) for nm in seg]))
    sp = spearman([official[nm] for nm in seg], [pred[nm] for nm in seg])
    return mae, sp, len(seg)


def main():
    for year, evf, blf in [
        (2025, "if_sim_2025_events.xlsx", "if_sim_2025_baseline.xlsx"),
        (2024, "if_sim_2024_events.xlsx", "if_sim_2024_baseline.xlsx"),
    ]:
        official, f = build(year, evf, blf)
        players = list(f.keys())

        def z(key):
            v = np.array([f[nm][key] for nm in players], float)
            mu, sd = v.mean(), v.std()
            return {nm: (f[nm][key] - mu) / sd if sd > 1e-9 else 0.0 for nm in players}

        z_avg, z_cv, z_std = z("avg"), z("cv_between"), z("std_between")
        z_mp = z("mp")
        cur = {nm: f[nm]["total"] for nm in players}

        def rank_of(s):
            return {nm: i + 1 for i, (nm, _) in enumerate(sorted(s.items(), key=lambda kv: -kv[1]))}

        p0 = rank_of(cur)
        m_all = metrics(p0, official, 1, 20)
        m_h = metrics(p0, official, 1, 6)
        m_m = metrics(p0, official, 7, 20)
        top20_0 = len({nm for nm in official if nm in list(p0)[:20]})

        print("=" * 104)
        print(f"{year} 年：稳定性信号（赛事间波动代理）")
        print("=" * 104)
        print(f"  现行 v1.2.0        Top20重叠={top20_0}/20 中段MAE={m_m[0]:5.2f} "
              f"中段sp={m_m[1]:+.3f} 头部MAE={m_h[0]:4.2f}")
        print()
        print(f"  {'配置':<40} {'Top20':>6} {'头部MAE':>8} {'中段MAE':>8} {'中段sp':>9}")

        best = None
        for label, k_avg, k_cv, k_mp in [
            ("(k_avg,k_cv,k_mp) = (1,0,0)", 1, 0, 0),
            ("(0,1,0)  纯稳定性", 0, 1, 0),
            ("(0,-1,0) 稳定性反向", 0, -1, 0),
            ("(1,1,0)", 1, 1, 0),
            ("(1,-1,0)", 1, -1, 0),
            ("(1,0,1)", 1, 0, 1),
            ("(0,1,1)", 0, 1, 1),
            ("(0,-1,1)", 0, -1, 1),
            ("(2,-1,1)", 2, -1, 1),
            ("(1,0.5,0)", 1, 0.5, 0),
            ("(0,2,0)", 0, 2, 0),
            ("(0,-2,0)", 0, -2, 0),
        ]:
            blend = {nm: cur[nm] + k_avg * z_avg[nm] + k_cv * z_cv[nm] + k_mp * z_mp[nm]
                     for nm in players}
            p = rank_of(blend)
            mm = metrics(p, official, 7, 20)
            mh = metrics(p, official, 1, 6)
            t20 = len({nm for nm in official if nm in list(p)[:20]})
            print(f"  {label:<40} {t20:>4}/20 {mh[0]:>8.2f} {mm[0]:>8.2f} {mm[1]:>+9.3f}")
            if best is None or mm[0] < best[1]:
                best = (label, mm[0], mm[1], t20, mh[0])

        print(f"\n  该年中段 MAE 最小: {best[0]}  MAE={best[1]:.2f} sp={best[2]:+.3f} "
              f"Top20={best[3]}/20 头部MAE={best[4]:.2f}")
        print(f"  基准对比:         现行            MAE={m_m[0]:.2f} sp={m_m[1]:+.3f} "
              f"Top20={top20_0}/20 头部MAE={m_h[0]:.2f}")

        # cv 与官方名次的相关性（中段内）
        mid = [nm for nm in official if 7 <= official[nm] <= 20 and nm in f]
        if len(mid) >= 3:
            cvc = spearman([official[nm] for nm in mid], [f[nm]["cv_between"] for nm in mid])
            avgc = spearman([official[nm] for nm in mid], [f[nm]["avg"] for nm in mid])
            print(f"\n  中段内相关性（负=方向正确）: cv={cvc:+.3f}  平均Rating={avgc:+.3f}")
        print()


if __name__ == "__main__":
    main()
