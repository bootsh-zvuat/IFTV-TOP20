# -*- coding: utf-8 -*-
"""最终方案验证：中段专用二次排序（分段模型）。

已有证据汇总（两年一致）：
  1. 现行 v1.2.0 在头部完美（MAE 0.33/1.00），中段是问题所在。
  2. 所有"全局调参"都让中段更差 → 不能动全局公式。
  3. 中段内与官方名次相关性方向正确的信号：
       平均 Rating（-0.270/-0.077）
       参赛场次（-0.090/-0.253）
       赛事内相对 rating（-0.244/-0.055）
     荣誉事件数方向相反（+0.270/+0.235）
  4. 单独的 z(rating)+z(maps) 在中段优于现行（6.50/6.57 vs 4.93/9.57 的 MAE 对比不成立，
     需固定口径重测）。

思路：不动全局公式（保住头部），只用"按名次分段"的方式，
在 Top-N 之后用中段信号重排。检验它是否真的比全局公式更接近官方。

关键：必须用同一年内、同一选手池、同一评估口径对比，避免口径漂移。
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
    ratings = defaultdict(list)
    by_event = defaultdict(list)

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
        ratings[nm].append(num(r.get("Rating")))
        by_event[str(r.get("赛事名称") or "")].append((nm, num(r.get("Rating"))))
        honor = str(r.get("荣誉类型") or "无").strip()
        rk = int(num(r.get("荣誉顺位")))
        hb = 10 if honor == "MVP" else ({1: 8, 2: 6, 3: 4}.get(rk, 0) if honor == "EVP" else 0)
        a["honor"] += hb * w
        a["rating"] += rating_bonus(num(r.get("Rating"))) * w
        a["place"] += PLACEMENT_ADJUST.get(str(r.get("队伍名次") or "").strip(), 0) * w

    # 赛事内相对 rating（加权）
    ev_mu = {}
    for ev, recs in by_event.items():
        rs = [x[1] for x in recs if x[1] > 0]
        if len(rs) >= 5:
            mu, sd = float(np.mean(rs)), float(np.std(rs))
            ev_mu[ev] = (mu, sd if sd > 1e-9 else 1e-9)
    relz = defaultdict(float)
    relw = defaultdict(float)
    for r in rows:
        nm = str(r.get("选手名") or "").strip()
        if not nm:
            continue
        ev = str(r.get("赛事名称") or "")
        if ev not in ev_mu:
            continue
        mu, sd = ev_mu[ev]
        rt = num(r.get("Rating"))
        if rt <= 0:
            continue
        lvl = str(r.get("赛事级别") or "").strip()
        w = num(r.get("赛事权重")) or EVENT_LEVEL_WEIGHTS.get(lvl, 0)
        relz[nm] += ((rt - mu) / sd) * w
        relw[nm] += w

    players = [nm for nm in acc if acc[nm]["mp"] >= 20]
    out = {}
    for nm in players:
        out[nm] = dict(
            total=acc[nm]["honor"] + acc[nm]["rating"] + acc[nm]["place"],
            honor=acc[nm]["honor"], rating=acc[nm]["rating"], place=acc[nm]["place"],
            mp=acc[nm]["mp"],
            avg=float(np.mean(ratings[nm])) if ratings[nm] else 0.0,
            relz=(relz[nm] / relw[nm]) if relw[nm] else 0.0,
            n_ev=acc[nm]["honor"] > 0,
        )
    return official, out


def rank_of(scores):
    rk = sorted(scores.items(), key=lambda kv: -kv[1])
    return {nm: i + 1 for i, (nm, _) in enumerate(rk)}


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

        z_avg, z_mp, z_rel = z("avg"), z("mp"), z("relz")
        cur = {nm: f[nm]["total"] for nm in players}
        pred_cur = rank_of(cur)

        print("=" * 104)
        print(f"{year} 年：分段重排方案")
        print("=" * 104)
        m = metrics(pred_cur, official, 1, 20)
        mh = metrics(pred_cur, official, 1, 6)
        mm = metrics(pred_cur, official, 7, 20)
        print(f"  现行 v1.2.0         Top20: MAE={m[0]:5.2f} sp={m[1]:+.3f} | "
              f"头部: MAE={mh[0]:4.2f} sp={mh[1]:+.3f} | 中段: MAE={mm[0]:5.2f} sp={mm[1]:+.3f}")

        # 分段方案：头部用现行分数，中段(mid)用混合分
        for ko, km, kr in [(1, 1, 0), (0.5, 1, 0), (1, 0.5, 0), (0.8, 0.8, 0.5),
                           (1, 1, 0.5), (0.5, 1, 0.5), (0.3, 1, 0.3)]:
            blend = {nm: cur[nm] + ko * z_avg[nm] + km * z_mp[nm] + kr * z_rel[nm]
                     for nm in players}
            p = rank_of(blend)
            # 只在中段生效：头部锁定现行顺序
            head_order = [nm for nm, _ in sorted(cur.items(), key=lambda kv: -kv[1])][:6]
            locked = {nm: (1e6 - i) for i, nm in enumerate(head_order)}
            rest = [nm for nm in players if nm not in locked]
            rest_sorted = sorted(rest, key=lambda nm: -blend[nm])
            final = dict(locked)
            for i, nm in enumerate(rest_sorted, start=len(head_order) + 1):
                final[nm] = -i
            pf = {nm: i + 1 for i, (nm, _) in enumerate(
                sorted(final.items(), key=lambda kv: -kv[1]))}
            m20 = metrics(pf, official, 1, 20)
            mh2 = metrics(pf, official, 1, 6)
            mm2 = metrics(pf, official, 7, 20)
            over = len({nm for nm in official if nm in list(pf)[:20]})
            print(f"  锁定头部 + 中段混合 (o={ko}, m={km}, r={kr})  "
                  f"Top20重叠={len({nm for nm in official if nm in [n for n,_ in sorted(pf.items(), key=lambda kv: kv[1])][:20]})}/20 "
                  f"中段: MAE={mm2[0]:5.2f} sp={mm2[1]:+.3f}")
        print()


if __name__ == "__main__":
    main()
