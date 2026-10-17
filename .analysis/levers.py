# -*- coding: utf-8 -*-
"""
只读诊断 3：真正的中段杠杆在哪？

verify_fix.py 证明：把离散 rating 档换成连续项，几乎无改善（中段MAE 4.71→4.43，
Spearman 反而略降）。所以"分档压平"不是主因。需要找真正的杠杆。

关键线索（fit_ranking.py 的结构 vs 模拟器结构）：
  拟合模型： 每年 z-score 归一化后加权 → 中段靠"相对同侪的位置"
  模拟器  ： Σ(绝对分 × 权重)      → 中段靠"荣誉事件数累加"

本脚本测试几个候选杠杆（逐一叠加，量化每一步的边际收益）：
  L1 荣誉通道：EVP 不再统一 5 分（现行 FITTED）/ 或降低 EVP 权重
  L2 名次通道：冠军队全体共享 +2/赛事，是否该按个人贡献折减
  L3 荣誉饱和：官方中段更看重"入选 Top20 的次数"而非单次高分
  L4 分数归一化：把总分做年度 z-score 后再排（改变的是相对结构）
  L5 排除"图数不足"选手占位（zhokiNg 7 图等）
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
MIN_EVENT_MAPS = 3


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


def parse(rows):
    """原始记录列表，便于多种加权方案复用"""
    recs = []
    for r in rows:
        nm = str(r.get("选手名") or "").strip()
        if not nm:
            continue
        maps = num(r.get("地图数"))
        if maps and maps < MIN_EVENT_MAPS:
            continue
        lvl = str(r.get("赛事级别") or "").strip()
        w = num(r.get("赛事权重")) or EVENT_LEVEL_WEIGHTS.get(lvl, 0)
        if w == 0:
            continue
        honor = str(r.get("荣誉类型") or "无").strip()
        rank = int(num(r.get("荣誉顺位")))
        recs.append(dict(nm=nm, maps=maps, level=lvl, w=w, honor=honor, rank=rank,
                         rating=num(r.get("Rating")),
                         place=str(r.get("队伍名次") or "").strip(),
                         event=str(r.get("赛事名称") or ""), team=str(r.get("队伍") or "")))
    return recs


def score(recs, evp1=8, evp2=6, evp3=4, place_scale=1.0, min_maps=20,
          z_normalize=False, honor_map=None):
    ch = defaultdict(lambda: {"honor": 0.0, "rating": 0.0, "place": 0.0,
                              "maps": 0.0, "ratings": [], "n_ev": 0})
    for r in recs:
        c = ch[r["nm"]]
        c["maps"] += r["maps"]
        c["ratings"].append(r["rating"])
        if r["honor"] == "MVP":
            hb = 10
            c["n_ev"] += 1
        elif r["honor"] == "EVP":
            hb = {1: evp1, 2: evp2, 3: evp3}.get(r["rank"], 0)
            c["n_ev"] += 1
        else:
            hb = 0
        c["honor"] += hb * r["w"]
        c["rating"] += rating_bonus(r["rating"]) * r["w"]
        c["place"] += PLACEMENT_ADJUST.get(r["place"], 0) * place_scale * r["w"]
    out = {}
    for nm, c in ch.items():
        if c["maps"] < min_maps:
            continue
        tot = c["honor"] + c["rating"] + c["place"]
        c["raw"] = tot
        c["avg_rating"] = float(np.mean(c["ratings"])) if c["ratings"] else 0.0
        out[nm] = c
    if z_normalize and out:
        vals = np.array([c["raw"] for c in out.values()], float)
        mu, sd = vals.mean(), vals.std()
        if sd > 1e-9:
            for c in out.values():
                c["total"] = (c["raw"] - mu) / sd
        else:
            for c in out.values():
                c["total"] = 0.0
    else:
        for c in out.values():
            c["total"] = c["raw"]
    return out


def evaluate(ch, official):
    ranked = sorted(ch.items(), key=lambda kv: -kv[1]["total"])
    pred = {nm: i + 1 for i, (nm, _) in enumerate(ranked)}
    common = [nm for nm in official if nm in pred]
    mid = [nm for nm in common if 7 <= official[nm] <= 20]
    head = [nm for nm in common if official[nm] <= 6]
    devs = {nm: pred[nm] - official[nm] for nm in common}
    sp_mid = float("nan")
    if len(mid) >= 2:
        a = np.array([official[nm] for nm in mid], float)
        b = np.array([pred[nm] for nm in mid], float)
        ra = np.argsort(np.argsort(a)).astype(float); rb = np.argsort(np.argsort(b)).astype(float)
        ra -= ra.mean(); rb -= rb.mean()
        d = np.sqrt((ra ** 2).sum() * (rb ** 2).sum())
        sp_mid = float((ra * rb).sum() / d) if d else float("nan")
    sp_all = float("nan")
    if len(common) >= 2:
        a = np.array([official[nm] for nm in common], float)
        b = np.array([pred[nm] for nm in common], float)
        ra = np.argsort(np.argsort(a)).astype(float); rb = np.argsort(np.argsort(b)).astype(float)
        ra -= ra.mean(); rb -= rb.mean()
        d = np.sqrt((ra ** 2).sum() * (rb ** 2).sum())
        sp_all = float((ra * rb).sum() / d) if d else float("nan")
    return dict(
        top5=len({n for n in official if official[n] <= 5} & set(list(pred)[:5])),
        top10=len({n for n in official if official[n] <= 10} & set(list(pred)[:10])),
        top20=len({n for n in official if n in list(pred)[:20]}),
        head_mae=float(np.mean([abs(devs[n]) for n in head])) if head else float("nan"),
        mid_mae=float(np.mean([abs(devs[n]) for n in mid])) if mid else float("nan"),
        mid_sp=sp_mid, all_sp=sp_all,
        mid_max=int(max(abs(devs[n]) for n in mid)) if mid else 0,
    )


def show(label, r, base=None):
    delta = ""
    if base:
        delta = (f"   Δ中段MAE={r['mid_mae']-base['mid_mae']:+.2f}"
                 f" Δ中段sp={r['mid_sp']-base['mid_sp']:+.3f}")
    print(f"{label:<34} Top20={r['top20']:>2}/20 头部MAE={r['head_mae']:4.2f} "
          f"中段MAE={r['mid_mae']:5.2f} 中段sp={r['mid_sp']:+.3f} "
          f"全体sp={r['all_sp']:+.3f} max={r['mid_max']:>3}{delta}")


def main():
    rows = load_rows(os.path.join(DATA, "if_sim_2025_events.xlsx"))
    baseline = load_rows(os.path.join(DATA, "if_sim_2025_baseline.xlsx"))
    official = {str(r.get("选手名")).strip(): int(num(r.get("名次"))) for r in baseline}
    recs = parse(rows)

    print("=" * 118)
    print("基线")
    print("=" * 118)
    base_ch = score(recs)
    B = evaluate(base_ch, official)
    show("v1.2.0 现行（EVP 8/6/4）", B)

    print("\n" + "=" * 118)
    print("L1 荣誉通道：统一 EVP 分（拟合校准口径 evp_ratio≈0.5 → 5 分）")
    print("=" * 118)
    for label, e1, e2, e3 in [
        ("EVP 统一 5 分", 5, 5, 5),
        ("EVP 统一 4 分", 4, 4, 4),
        ("EVP 统一 3 分", 3, 3, 3),
        ("EVP 统一 6 分", 6, 6, 6),
        ("EVP 8/6/4（现行）", 8, 6, 4),
    ]:
        r = evaluate(score(recs, evp1=e1, evp2=e2, evp3=e3), official)
        show(label, r, B)

    print("\n" + "=" * 118)
    print("L2 名次通道缩放（冠军队共享 +2 是否过强）")
    print("=" * 118)
    for ps in (0.0, 0.25, 0.5, 0.75, 1.0, 1.5):
        r = evaluate(score(recs, place_scale=ps), official)
        show(f"名次分 × {ps}", r, B)

    print("\n" + "=" * 118)
    print("L4 年度 z-score 归一化后排序（对齐拟合模型结构）")
    print("=" * 118)
    for ps in (0.0, 0.5, 1.0):
        r = evaluate(score(recs, place_scale=ps, z_normalize=True), official)
        show(f"z-norm + 名次分×{ps}", r, B)

    print("\n" + "=" * 118)
    print("L5+ 组合：最优候选")
    print("=" * 118)
    combos = [
        ("EVP5 + 名次×0.5", dict(evp1=5, evp2=5, evp3=5, place_scale=0.5)),
        ("EVP5 + 名次×0（去名次通道）", dict(evp1=5, evp2=5, evp3=5, place_scale=0.0)),
        ("EVP8/6/4 + 名次×0.5", dict(evp1=8, evp2=6, evp3=4, place_scale=0.5)),
        ("EVP5 + 名次×0 + znorm", dict(evp1=5, evp2=5, evp3=5, place_scale=0.0, z_normalize=True)),
        ("EVP5 + 名次×0.5 + znorm", dict(evp1=5, evp2=5, evp3=5, place_scale=0.5, z_normalize=True)),
        ("EVP8/6/4 + 名次×0", dict(evp1=8, evp2=6, evp3=4, place_scale=0.0)),
    ]
    for label, kw in combos:
        r = evaluate(score(recs, **kw), official)
        show(label, r, B)

    print("\n" + "=" * 118)
    print("诊断：官方中段 9 人 vs 模拟器的错误来源（基线算法）")
    print("=" * 118)
    ranked = sorted(base_ch.items(), key=lambda kv: -kv[1]["total"])
    pred = {nm: i + 1 for i, (nm, _) in enumerate(ranked)}
    for nm, rk in sorted(official.items(), key=lambda kv: kv[1]):
        if not (7 <= rk <= 20):
            continue
        c = base_ch.get(nm)
        if not c:
            continue
        print(f"  官方#{rk:<3} {nm:<14} 模拟#{pred[nm]:<4} 偏差={pred[nm]-rk:+3} "
              f"荣誉={c['honor']:6.2f} rating={c['rating']:5.2f} 名次={c['place']:6.2f} "
              f"均Rating={c['avg_rating']:.3f} 图数={c['maps']:.0f} 荣誉数={c['n_ev']}")


if __name__ == "__main__":
    main()
