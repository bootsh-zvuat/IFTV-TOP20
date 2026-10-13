# -*- coding: utf-8 -*-
"""
只读验证：用"连续 rating 项"替代"3 档离散加分"，中段能否改善？

关键证据（来自 rootcause.py）：
- 中段 14 人平均 rating 极差只有 0.126，却要区分 14 个名次
- 离散档位把 14 人压成 3 种取值（0 / 0.5 / 1.0），区分度信息被丢掉
- 中段内 rating 通道与官方名次的 Spearman 只有 -0.288（方向也弱）

本脚本做网格扫描：在保持其他通道不变的前提下，把 rating 通道换成
  (avg_rating - baseline) * k
比较中段 Spearman / 平均绝对偏差的变化。纯计算，不写任何项目文件。
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
HONOR_BASE = {"MVP": 10, "1": 8, "2": 6, "3": 4}
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


def build(rows, mode, k=0.0, base=1.10):
    """mode='tier' 用现行离散档；mode='linear' 用连续 rating 项"""
    ch = defaultdict(lambda: {"honor": 0.0, "rating": 0.0, "place": 0.0,
                              "ratings": [], "maps": 0.0, "n_ev": 0})
    for r in rows:
        nm = str(r.get("选手名") or "").strip()
        if not nm:
            continue
        maps = num(r.get("地图数"))
        if maps and maps < 3:
            continue
        w = num(r.get("赛事权重")) or EVENT_LEVEL_WEIGHTS.get(
            str(r.get("赛事级别") or "").strip(), 0)
        if w == 0:
            continue
        c = ch[nm]
        c["maps"] += maps
        rat = num(r.get("Rating"))
        c["ratings"].append(rat)
        honor = str(r.get("荣誉类型") or "无").strip()
        rank = int(num(r.get("荣誉顺位")))
        hb = HONOR_BASE["MVP"] if honor == "MVP" else (
            HONOR_BASE.get(str(rank), 0) if honor == "EVP" else 0)
        if honor in ("MVP", "EVP"):
            c["n_ev"] += 1
        place = str(r.get("队伍名次") or "").strip()
        c["honor"] += hb * w
        if mode == "tier":
            c["rating"] += rating_bonus(rat) * w
        else:
            # 连续项：相对基准的线性偏离，按赛事权重累加
            c["rating"] += (rat - base) * k * w
        c["place"] += PLACEMENT_ADJUST.get(place, 0) * w
    for nm, c in ch.items():
        c["total"] = c["honor"] + c["rating"] + c["place"]
        c["avg_rating"] = float(np.mean(c["ratings"])) if c["ratings"] else 0.0
    return ch


def spearman(a, b):
    a, b = np.asarray(a, float), np.asarray(b, float)
    ra = np.argsort(np.argsort(a)).astype(float)
    rb = np.argsort(np.argsort(b)).astype(float)
    ra -= ra.mean(); rb -= rb.mean()
    d = np.sqrt((ra ** 2).sum() * (rb ** 2).sum())
    return float((ra * rb).sum() / d) if d else float("nan")


def evaluate(ch, official, label):
    ranked = sorted(ch.items(), key=lambda kv: -kv[1]["total"])
    pred = {nm: i + 1 for i, (nm, _) in enumerate(ranked)}
    common = [nm for nm in official if nm in pred]
    devs = {nm: pred[nm] - official[nm] for nm in common}
    mid = [nm for nm in common if 7 <= official[nm] <= 20]
    head = [nm for nm in common if official[nm] <= 6]
    res = {
        "label": label,
        "top5": len({nm for nm in official if official[nm] <= 5} & set(list(pred)[:5])),
        "top10": len({nm for nm in official if official[nm] <= 10} & set(list(pred)[:10])),
        "top20": len(set(common[:20]) & {nm for nm in official}) if len(common) >= 20 else len(
            {nm for nm in official if nm in list(pred)[:20]}),
        "mid_mae": float(np.mean([abs(devs[nm]) for nm in mid])) if mid else float("nan"),
        "mid_sp": spearman([official[nm] for nm in mid], [pred[nm] for nm in mid]) if mid else float("nan"),
        "head_mae": float(np.mean([abs(devs[nm]) for nm in head])) if head else float("nan"),
        "mid_max": int(max(abs(devs[nm]) for nm in mid)) if mid else 0,
    }
    return res


def main():
    rows = load_rows(os.path.join(DATA, "if_sim_2025_events.xlsx"))
    baseline = load_rows(os.path.join(DATA, "if_sim_2025_baseline.xlsx"))
    official = {str(r.get("选手名")).strip(): int(num(r.get("名次"))) for r in baseline}

    print("=" * 96)
    print("基线（现行 v1.2.0 离散档位）")
    print("=" * 96)
    base_ch = build(rows, "tier")
    b = evaluate(base_ch, official, "v1.2.0 现行")
    print(f"  Top5={b['top5']}/5  Top10={b['top10']}/10  Top20={b['top20']}/20")
    print(f"  头部MAE={b['head_mae']:.2f}  中段MAE={b['mid_mae']:.2f}  "
          f"中段Spearman={b['mid_sp']:+.3f}  中段最大偏差={b['mid_max']}")

    print("\n" + "=" * 96)
    print("替换为连续 rating 项：(rating - base) * k  —— 扫描 base / k")
    print("=" * 96)
    print(f"{'base':>6} {'k':>6} {'Top5':>5} {'Top10':>6} {'Top20':>6} "
          f"{'头部MAE':>8} {'中段MAE':>8} {'中段Spearman':>13} {'中段max':>8}")
    results = []
    for base_v in (1.00, 1.05, 1.10, 1.15):
        for k in (5, 8, 10, 12, 15, 20, 25, 30):
            ch = build(rows, "linear", k=k, base=base_v)
            r = evaluate(ch, official, f"linear base={base_v} k={k}")
            results.append((r, base_v, k))
            print(f"{base_v:>6.2f} {k:>6} {r['top5']:>5} {r['top10']:>6} {r['top20']:>6} "
                  f"{r['head_mae']:>8.2f} {r['mid_mae']:>8.2f} {r['mid_sp']:>+13.3f} "
                  f"{r['mid_max']:>8}")

    print("\n" + "=" * 96)
    print("按中段 MAE 排序的前 8 名配置")
    print("=" * 96)
    results.sort(key=lambda x: -x[0]["mid_mae"])
    for r, bv, k in results[:8]:
        print(f"  base={bv:.2f} k={k:<3} Top20={r['top20']}/20 头部MAE={r['head_mae']:.2f} "
              f"中段MAE={r['mid_mae']:.2f} 中段Spearman={r['mid_sp']:+.3f} max={r['mid_max']}")

    print("\n对比基线: 头部MAE=%.2f 中段MAE=%.2f 中段Spearman=%+.3f max=%d"
          % (b["head_mae"], b["mid_mae"], b["mid_sp"], b["mid_max"]))


if __name__ == "__main__":
    main()
