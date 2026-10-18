# -*- coding: utf-8 -*-
"""稳健性检验：vsTop5 通道的改善是否真实可靠？

初步结果很积极（10 个配置两年都改善），但必须排除以下可能：
  A. 改善来自"把中段的人挤出去"（Top20 变成 20/20 是因为恰好对齐）
  B. k 的选择过拟合 —— 需要一个"两年都不看"的安全区间
  C. 改善只发生在 MAE，Spearman 没改善（说明只是压平了，不是排对了）
  D. 数据泄漏 —— HLTV 页面本身就是官方评选依据，用它预测官方名次有循环论证风险

重点检验 D（这是最关键的学术性问题）与 B。
"""
import os
from collections import defaultdict

import openpyxl
import numpy as np

BASE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # 项目根 = .analysis/ 的上一级
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
    ev_rows = load_rows(os.path.join(DATA, f"if_sim_{year}_events.xlsx"))
    official = {str(r.get("选手名")).strip(): int(num(r.get("名次")))
                for r in load_rows(os.path.join(DATA, f"if_sim_{year}_baseline.xlsx"))}
    opp = {}
    p = os.path.join(DATA, f"hltv_opponent_{year}.xlsx")
    for r in load_rows(p):
        nm = str(r.get("选手") or "").strip()
        if nm:
            opp[nm] = dict(rating=num(r.get("Rating")), vs5=num(r.get("vsTop5")),
                           vs20=num(r.get("vsTop20")), maps=num(r.get("地图数")))
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
        honor = str(r.get("荣誉类型") or "无").strip()
        rk = int(num(r.get("荣誉顺位")))
        hb = 10 if honor == "MVP" else ({1: 8, 2: 6, 3: 4}.get(rk, 0) if honor == "EVP" else 0)
        a["honor"] += hb * w
        a["rating"] += rating_bonus(num(r.get("Rating"))) * w
        a["place"] += PLACEMENT_ADJUST.get(str(r.get("队伍名次") or "").strip(), 0) * w
    players = [nm for nm in acc if acc[nm]["mp"] >= 20]
    feats = {nm: dict(cur=acc[nm]["honor"] + acc[nm]["rating"] + acc[nm]["place"],
                      vs5=opp.get(nm, {}).get("vs5", 0.0),
                      vs20=opp.get(nm, {}).get("vs20", 0.0),
                      hltv_rating=opp.get(nm, {}).get("rating", 0.0))
             for nm in players}
    return official, feats


def rank_of(s):
    return {nm: i + 1 for i, (nm, _) in enumerate(sorted(s.items(), key=lambda kv: -kv[1]))}


def seg(pred, official, lo, hi):
    s = [nm for nm in official if lo <= official[nm] <= hi and nm in pred]
    if not s:
        return None
    return (float(np.mean([abs(pred[nm] - official[nm]) for nm in s])),
            spearman([official[nm] for nm in s], [pred[nm] for nm in s]), len(s))


def main():
    D = {y: build(y) for y in (2025, 2024)}

    def zf(feats, key, players):
        v = np.array([feats[nm][key] for nm in players], float)
        mu, sd = v.mean(), v.std()
        return {nm: (feats[nm][key] - mu) / sd if sd > 1e-9 else 0.0 for nm in players}

    print("=" * 100)
    print("检验 B：k 的安全区间（两个年份的响应曲线）")
    print("=" * 100)
    print(f"  {'k':>6} | {'2025 MAE':>9} {'2025 sp':>8} {'2025 Top20':>10} | "
          f"{'2024 MAE':>9} {'2024 sp':>8} {'2024 Top20':>10}")
    rows = []
    for k in (0, 0.25, 0.5, 1, 1.5, 2, 3, 4, 5, 7, 10):
        out = []
        for y in (2025, 2024):
            official, feats = D[y]
            players = list(feats)
            zv5 = zf(feats, "vs5", players)
            pred = rank_of({nm: feats[nm]["cur"] + k * zv5[nm] for nm in players})
            m, mh = seg(pred, official, 7, 20), seg(pred, official, 1, 6)
            t20 = len({nm for nm in official if nm in list(pred)[:20]})
            out.append((m[0], m[1], t20, mh[0]))
        rows.append((k, out))
        print(f"  {k:>6} | {out[0][0]:>9.2f} {out[0][1]:>+8.3f} {out[0][2]:>10} | "
              f"{out[1][0]:>9.2f} {out[1][1]:>+8.3f} {out[1][2]:>10}")

    print("\n" + "=" * 100)
    print("检验 C：改善是「排对了」还是「压平了」？")
    print("=" * 100)
    for k in (1, 2, 3, 5):
        for y in (2025, 2024):
            official, feats = D[y]
            players = list(feats)
            zv5 = zf(feats, "vs5", players)
            pred = rank_of({nm: feats[nm]["cur"] + k * zv5[nm] for nm in players})
            m = seg(pred, official, 7, 20)
            print(f"  k={k} {y}: 中段 MAE={m[0]:.2f}  Spearman={m[1]:+.3f}")

    print("\n" + "=" * 100)
    print("检验 D：数据泄漏风险（HLTV vsTop5 是否只是官方评分的代理）")
    print("=" * 100)
    for y in (2025, 2024):
        official, feats = D[y]
        mid = [nm for nm in official if 7 <= official[nm] <= 20 and nm in feats]
        if len(mid) < 3:
            continue
        # HLTV 整体 rating 与 vsTop5 的相关性
        a = [feats[nm]["hltv_rating"] for nm in mid]
        b = [feats[nm]["vs5"] for nm in mid]
        r = float(np.corrcoef(a, b)[0, 1]) if len(a) > 2 else float("nan")
        print(f"  {y}: 中段内 HLTV整体Rating 与 vsTop5 的 Pearson r = {r:+.3f}")
        print(f"        （高相关 → vsTop5 可能只是整体 rating 的翻版，信息增量有限）")

    print("\n" + "=" * 100)
    print("检验 A：改善是否伴随人员替换（Top20 成员变化）")
    print("=" * 100)
    for y in (2025, 2024):
        official, feats = D[y]
        players = list(feats)
        zv5 = zf(feats, "vs5", players)
        p0 = rank_of({nm: feats[nm]["cur"] for nm in players})
        p2 = rank_of({nm: feats[nm]["cur"] + 2 * zv5[nm] for nm in players})
        t0 = {nm for nm in official if nm in list(p0)[:20]}
        t2 = {nm for nm in official if nm in list(p2)[:20]}
        print(f"  {y}: 基线命中 {len(t0)}/20 → 加通道后 {len(t2)}/20")
        gained = t2 - t0
        lost = t0 - t2
        if gained:
            print(f"       新进榜: {sorted(gained)}")
        if lost:
            print(f"       掉出榜: {sorted(lost)}")


if __name__ == "__main__":
    main()
