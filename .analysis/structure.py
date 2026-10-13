# -*- coding: utf-8 -*-
"""
只读诊断 4：结构性根因。

前面三个脚本证明：
  - 换连续 rating 项：几乎无改善
  - 调 EVP 分 / 名次通道缩放 / z-norm：全部让中段更差
  → 现行 v1.2.0 参数已在该结构下的局部最优。

那问题只能在"结构"本身。本脚本检验结构假设：

H1 信息缺失假设：官方中段排序依赖模拟器完全没有的维度。
   官方 HLTV 中段主要看：对手强度(TOP5/10/20 rating)、稳定性(大赛表现)、
   以及"全年聚合 rating"而非"逐赛事荣誉计数"。
   量化：模拟器输入里有哪些量？它们的上界区分度如何？

H2 荣誉计数假设：逐赛事加和把"荣誉事件数"当主信号，
   而官方中段更看重"rating 的相对位次"。
   检验：把荣誉通道完全去掉，只用 rating 通道（连续），中段排序如何？

H3 天花板假设：中段选手总分差只有 ~19 分，而实际排序噪声 > 单事件奖励。
   量化：改变一个 EVP 归属（约 4×0.8=3.2 分）能让中段移动几名？

H4 样本外假设：模拟器只有 2025 一年可验证的中段数据，
   参数是在这份数据上调出来的 → 无法泛化。
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


def main():
    rows = load_rows(os.path.join(DATA, "if_sim_2025_events.xlsx"))
    baseline = load_rows(os.path.join(DATA, "if_sim_2025_baseline.xlsx"))
    official = {str(r.get("选手名")).strip(): int(num(r.get("名次"))) for r in baseline}

    # ---------- 可用输入字段盘点 ----------
    print("=" * 100)
    print("H1 信息盘点：模拟器实际可用的输入维度")
    print("=" * 100)
    print(f"  赛事表列: {list(rows[0].keys())}")
    used = {"选手名", "赛事级别", "赛事权重", "队伍名次", "荣誉类型", "荣誉顺位",
            "Rating", "地图数"}
    allcols = set(rows[0].keys())
    print(f"  算法使用: {sorted(used & allcols)}")
    print(f"  未被使用: {sorted(allcols - used)}")
    print("\n  官方 HLTV 中段实际依赖但本数据集的缺失维度：")
    for x in ["对手强度分(top5/10/20 对手的 rating)", "大赛(Major)单独表现拆解",
              "稳定性/方差(逐月波动)", "地图类型细分", "KAST / Impact 等复合指标",
              "EVP 顺位（本表有顺位但拟合侧无法区分）"]:
        print(f"    - {x}")

    # ---------- H2 只保留 rating 通道 ----------
    print("\n" + "=" * 100)
    print("H2 通道消融：中段排序到底由哪个通道决定")
    print("=" * 100)
    ch = defaultdict(lambda: defaultdict(float))
    rec_ratings = defaultdict(list)
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
        rec_ratings[nm].append(num(r.get("Rating")))
        honor = str(r.get("荣誉类型") or "无").strip()
        rank = int(num(r.get("荣誉顺位")))
        hb = 10 if honor == "MVP" else ({1: 8, 2: 6, 3: 4}.get(rank, 0) if honor == "EVP" else 0)
        c["honor"] += hb * w
        c["rating"] += rating_bonus(num(r.get("Rating"))) * w
        c["place"] += PLACEMENT_ADJUST.get(str(r.get("队伍名次") or "").strip(), 0) * w

    def mk(use_honor, use_rating, use_place, w_rating=1.0):
        out = {}
        for nm, c in ch.items():
            if c["maps"] < 20:
                continue
            t = 0.0
            if use_honor:
                t += c["honor"]
            if use_rating:
                avg = float(np.mean(rec_ratings[nm]))
                t += (avg - 1.10) * 40 * w_rating
            if use_place:
                t += c["place"]
            out[nm] = t
        return out

    def ev(scores, label):
        ranked = sorted(scores.items(), key=lambda kv: -kv[1])
        pred = {nm: i + 1 for i, (nm, _) in enumerate(ranked)}
        mid = [nm for nm in official if 7 <= official[nm] <= 20 and nm in pred]
        head = [nm for nm in official if official[nm] <= 6 and nm in pred]
        top20 = len({nm for nm in official if nm in list(pred)[:20]})
        devs = {nm: pred[nm] - official[nm] for nm in mid}
        if len(mid) >= 2:
            a = np.array([official[nm] for nm in mid], float)
            b = np.array([pred[nm] for nm in mid], float)
            ra = np.argsort(np.argsort(a)).astype(float); rb = np.argsort(np.argsort(b)).astype(float)
            ra -= ra.mean(); rb -= rb.mean()
            d = np.sqrt((ra ** 2).sum() * (rb ** 2).sum())
            sp = float((ra * rb).sum() / d) if d else float("nan")
        else:
            sp = float("nan")
        mae = float(np.mean([abs(d) for d in devs.values()])) if devs else float("nan")
        hmae = float(np.mean([abs(pred[nm] - official[nm]) for nm in head])) if head else float("nan")
        print(f"  {label:<40} Top20={top20:>2}/20 头部MAE={hmae:4.2f} "
              f"中段MAE={mae:5.2f} 中段sp={sp:+.3f}")

    ev(mk(True, True, True), "荣誉 + rating档 + 名次（现行）")
    ev(mk(True, False, True), "仅 荣誉 + 名次")
    ev(mk(False, True, True), "仅 rating(连续) + 名次")
    ev(mk(False, True, False), "仅 rating(连续)")
    ev(mk(True, True, False), "仅 荣誉 + rating档")
    ev(mk(False, False, True), "仅 名次")

    # ---------- H3 灵敏度 ----------
    print("\n" + "=" * 100)
    print("H3 灵敏度：中段分数差 vs 单次荣誉事件的奖励量级")
    print("=" * 100)
    base = {}
    for nm, c in ch.items():
        if c["maps"] >= 20:
            base[nm] = c["honor"] + c["rating"] + c["place"]
    ranked = sorted(base.items(), key=lambda kv: -kv[1])
    pred = {nm: i + 1 for i, (nm, _) in enumerate(ranked)}
    mid_scores = sorted([(nm, base[nm], official[nm], pred[nm])
                         for nm in official if 7 <= official[nm] <= 20 and nm in base],
                        key=lambda x: -x[1])
    print("  中段分数梯度：")
    for i, (nm, s, ork, prk) in enumerate(mid_scores):
        gap = ""
        if i + 1 < len(mid_scores):
            gap = f"  与下一名差={s - mid_scores[i+1][1]:5.2f}"
        print(f"    官方#{ork:<3} {nm:<14} {s:7.2f}{gap}")
    scores = [s for _, s, _, _ in mid_scores]
    if len(scores) >= 2:
        print(f"\n  中段区间: {min(scores):.2f} ~ {max(scores):.2f}  跨度={max(scores)-min(scores):.2f}")
        print(f"  一个 EVP（4分 × 精英赛0.75）≈ 3.00 分权重")
        print(f"  一个 MVP（10分 × Major1.0）≈ 10.00 分权重")
        span = max(scores) - min(scores)
        print(f"  → 单个 MVP 事件 ≈ 中段总跨度的 {10.0/span*100:.0f}%")
        print(f"  → 单个 EVP 事件 ≈ 中段总跨度的 {3.0/span*100:.0f}%")

    # 微扰测试：把一个中段选手的某一个 EVP 改成无荣誉，看名次移动
    print("\n  扰动实验：把每位中段选手的 1 个 EVP（≈3 分）移除后的名次变化")
    for nm in [n for n in official if 7 <= official[n] <= 20 and n in base][:6]:
        vals = dict(base)
        vals[nm] = vals[nm] - 3.0
        r2 = sorted(vals.items(), key=lambda kv: -kv[1])
        p2 = {n: i + 1 for i, (n, _) in enumerate(r2)}
        print(f"    {nm:<14} 官方#{official[nm]:<3} 原模拟#{pred[nm]:<3} → 移除1个EVP后#{p2[nm]:<3} "
              f"(移动 {p2[nm]-pred[nm]:+d})")

    # ---------- H4 交叉验证 ----------
    print("\n" + "=" * 100)
    print("H4 样本外检验：2024 年数据能否复现中段？（参数是在类似数据上人工校准的）")
    print("=" * 100)
    p24 = os.path.join(DATA, "if_sim_2024_events.xlsx")
    b24 = os.path.join(DATA, "if_sim_2024_baseline.xlsx")
    if os.path.exists(p24) and os.path.exists(b24):
        rows24 = load_rows(p24)
        bl24 = load_rows(b24)
        official24 = {str(r.get("选手名")).strip(): int(num(r.get("名次"))) for r in bl24}
        ch24 = defaultdict(lambda: defaultdict(float))
        for r in rows24:
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
            c = ch24[nm]
            c["maps"] += maps
            honor = str(r.get("荣誉类型") or "无").strip()
            rank = int(num(r.get("荣誉顺位")))
            hb = 10 if honor == "MVP" else ({1: 8, 2: 6, 3: 4}.get(rank, 0) if honor == "EVP" else 0)
            c["honor"] += hb * w
            c["rating"] += rating_bonus(num(r.get("Rating"))) * w
            c["place"] += PLACEMENT_ADJUST.get(str(r.get("队伍名次") or "").strip(), 0) * w
        b24s = {nm: c["honor"] + c["rating"] + c["place"]
                for nm, c in ch24.items() if c["maps"] >= 20}
        rk24 = sorted(b24s.items(), key=lambda kv: -kv[1])
        pr24 = {nm: i + 1 for i, (nm, _) in enumerate(rk24)}
        mid24 = [nm for nm in official24 if 7 <= official24[nm] <= 20 and nm in pr24]
        head24 = [nm for nm in official24 if official24[nm] <= 6 and nm in pr24]
        top20_24 = len({nm for nm in official24 if nm in list(pr24)[:20]})
        print(f"  2024 年: Top20重叠={top20_24}/20  头部命中={len(head24)}/{len([n for n in official24 if official24[n]<=6])}")
        if mid24:
            mae24 = float(np.mean([abs(pr24[nm] - official24[nm]) for nm in mid24]))
            hmae24 = float(np.mean([abs(pr24[nm] - official24[nm]) for nm in head24])) if head24 else float("nan")
            a = np.array([official24[nm] for nm in mid24], float)
            b = np.array([pr24[nm] for nm in mid24], float)
            ra = np.argsort(np.argsort(a)).astype(float); rb = np.argsort(np.argsort(b)).astype(float)
            ra -= ra.mean(); rb -= rb.mean()
            d = np.sqrt((ra ** 2).sum() * (rb ** 2).sum())
            sp24 = float((ra * rb).sum() / d) if d else float("nan")
            print(f"  2024 中段MAE={mae24:.2f} 中段Spearman={sp24:+.3f} 头部MAE={hmae24:.2f}")
            print(f"  2024 中段逐名:")
            for nm in sorted(mid24, key=lambda n: official24[n]):
                print(f"    官方#{official24[nm]:<3} {nm:<14} 模拟#{pr24[nm]:<3} 偏差={pr24[nm]-official24[nm]:+3}")
    else:
        print("  未找到 2024 数据文件")


if __name__ == "__main__":
    main()
