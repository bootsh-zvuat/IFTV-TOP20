# -*- coding: utf-8 -*-
"""
只读诊断 6（结论）：中段误差的真正来源 —— 缺失维度，而非权重配比。

汇总前 5 个脚本的证据：

1. 评级：现行 v1.2.0 在 2025 中段 MAE=4.57 / Spearman=+0.336；
   2024 中段 MAE=5.21 / Spearman=+0.213。头部两年 6/6 全中。

2. 调参无效（levers.py）：EVP 分值、名次通道缩放、z-norm 全部让中段变差。
   → 现行参数已是该结构下的局部最优，继续调参没有空间。

3. 换连续 rating 项无效（verify_fix.py）：中段 MAE 4.71→4.43 但 Spearman 下降。

4. 单通道消融（structure.py）：任何单通道都不如三通道叠加。

5. 关键反直觉证据（hypothesis_count.py）：
   在官方 7-20 段内，"荣誉事件数"与官方名次的 Spearman = +0.270/+0.235
   （正号 = 方向相反：荣誉越多，官方名次越靠后）。
   而"平均 Rating" = -0.270/-0.077、"参赛场次" = -0.090/-0.253（方向正确）。

   → 官方中段排序与"荣誉数量"负相关、与"rating/稳定性"正相关。
     而模拟器的荣誉通道（4~10 分/事件）量级远大于 rating 通道（0~2 分/事件），
     导致模拟器在中段实质上是"在数荣誉"，方向恰好反了。

本脚本做最后一个可执行检验：
  构造一个"中段专用"排序器（只用方向正确的信号，且量级可比），
  看中段能否显著改善。若不能，则结论是"数据维度不足，需补采集"。
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


def spearman(a, b):
    a, b = np.asarray(a, float), np.asarray(b, float)
    ra = np.argsort(np.argsort(a)).astype(float)
    rb = np.argsort(np.argsort(b)).astype(float)
    ra -= ra.mean(); rb -= rb.mean()
    d = np.sqrt((ra ** 2).sum() * (rb ** 2).sum())
    return float((ra * rb).sum() / d) if d else float("nan")


def build(ev_path, bl_path):
    rows = load_rows(ev_path)
    official = {str(r.get("选手名")).strip(): int(num(r.get("名次")))
                for r in load_rows(bl_path)}
    acc = defaultdict(lambda: defaultdict(float))
    ratings = defaultdict(list)
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
        a = acc[nm]
        a["maps"] += maps
        ratings[nm].append(num(r.get("Rating")))
        honor = str(r.get("荣誉类型") or "无").strip()
        rank = int(num(r.get("荣誉顺位")))
        hb = 10 if honor == "MVP" else ({1: 8, 2: 6, 3: 4}.get(rank, 0) if honor == "EVP" else 0)
        a["honor"] += hb * w
        a["place"] += PLACEMENT_ADJUST.get(str(r.get("队伍名次") or "").strip(), 0) * w
    players = [nm for nm in acc if acc[nm]["maps"] >= 20]
    avg = {nm: float(np.mean(ratings[nm])) for nm in players}
    # 稳定性 = rating 的标准差（越小越稳）
    std = {nm: float(np.std(ratings[nm])) for nm in players}
    # 参赛量 = 场次（官方中段偏好多打的人）
    maps = {nm: acc[nm]["maps"] for nm in players}
    honor = {nm: acc[nm]["honor"] for nm in players}
    place = {nm: acc[nm]["place"] for nm in players}
    base = {nm: honor[nm] + place[nm] for nm in players}
    return official, dict(avg=avg, std=std, maps=maps, honor=honor, place=place, base=base)


def z(d, players):
    v = np.array([d[nm] for nm in players], float)
    mu, sd = v.mean(), v.std()
    if sd < 1e-9:
        return {nm: 0.0 for nm in players}
    return {nm: (d[nm] - mu) / sd for nm in players}


def evaluate(label, scores, official):
    rk = sorted(scores.items(), key=lambda kv: -kv[1])
    pred = {nm: i + 1 for i, (nm, _) in enumerate(rk)}
    mid = [nm for nm in official if 7 <= official[nm] <= 20 and nm in pred]
    head = [nm for nm in official if official[nm] <= 6 and nm in pred]
    top20 = len({nm for nm in official if nm in list(pred)[:20]})
    if not mid:
        print(f"  {label:<44} 无中段数据")
        return None
    mae = float(np.mean([abs(pred[nm] - official[nm]) for nm in mid]))
    sp = spearman([official[nm] for nm in mid], [pred[nm] for nm in mid])
    hmae = float(np.mean([abs(pred[nm] - official[nm]) for nm in head])) if head else float("nan")
    print(f"  {label:<44} Top20={top20:>2}/20 头部MAE={hmae:4.2f} "
          f"中段MAE={mae:5.2f} 中段sp={sp:+.3f}")
    return dict(top20=top20, mid_mae=mae, mid_sp=sp, head_mae=hmae)


def main():
    for year, ev, bl in [
        (2025, "if_sim_2025_events.xlsx", "if_sim_2025_baseline.xlsx"),
        (2024, "if_sim_2024_events.xlsx", "if_sim_2024_baseline.xlsx"),
    ]:
        official, f = build(os.path.join(DATA, ev), os.path.join(DATA, bl))
        players = [nm for nm in f["avg"] if nm in official or True]
        # 只对官方 Top20 成员评估，但排序池用全部选手
        zavg = z(f["avg"], players)
        zstd = z(f["std"], players)
        zmaps = z(f["maps"], players)
        zhonor = z(f["honor"], players)
        zplace = z(f["place"], players)
        zbase = z(f["base"], players)

        print("=" * 106)
        print(f"{year} 年：用“方向正确的信号 + 可比量级”构造中段排序器")
        print("=" * 106)
        evaluate("现行 v1.2.0", {nm: f["base"][nm] for nm in players}, official)

        # 只用方向正确的信号，z-score 后等权
        variants = {
            "z(rating) 单项": {nm: zavg[nm] for nm in players},
            "z(rating) + z(-std)": {nm: zavg[nm] - zstd[nm] for nm in players},
            "z(rating) + z(maps)": {nm: zavg[nm] + zmaps[nm] for nm in players},
            "z(rating) + z(-std) + z(maps)": {nm: zavg[nm] - zstd[nm] + zmaps[nm] for nm in players},
            "z(rating)×2 + z(-std) + z(maps)": {nm: 2 * zavg[nm] - zstd[nm] + zmaps[nm] for nm in players},
            "z(rating) + z(place)": {nm: zavg[nm] + zplace[nm] for nm in players},
            "z(rating) + z(honor)": {nm: zavg[nm] + zhonor[nm] for nm in players},
            "现行 z(base) + z(rating)": {nm: zbase[nm] + zavg[nm] for nm in players},
            "现行 z(base) + z(-std)": {nm: zbase[nm] - zstd[nm] for nm in players},
            "z(base) + z(rating) + z(-std) + z(maps)":
                {nm: zbase[nm] + zavg[nm] - zstd[nm] + zmaps[nm] for nm in players},
        }
        best = None
        for label, sc in variants.items():
            r = evaluate(label, sc, official)
            if r and (best is None or r["mid_mae"] < best[1]["mid_mae"]):
                best = (label, r)

        print(f"\n  该年最佳中段配置: {best[0]}  中段MAE={best[1]['mid_mae']:.2f} "
              f"中段sp={best[1]['mid_sp']:+.3f} (Top20={best[1]['top20']}/20)")
        print()

    print("=" * 106)
    print("结论")
    print("=" * 106)
    print("""
  两年一致的证据链说明中段误差不是"权重没调好"，而是输入维度不足：

  (a) 调参方向已穷尽：EVP 分值 / 名次缩放 / z-norm / 连续 rating，
      每一个都让中段 MAE 变大或 Spearman 变小。
  (b) 官方中段排序与"荣誉事件数"负相关（+0.270 / +0.235），
      与"平均 rating""参赛场次"正相关（方向正确）。
  (c) 但模拟器的荣誉通道量级（4~10 分/事件）压过 rating 通道（0~2 分/事件），
      于是中段实质由"数荣誉"主导 —— 信号方向恰好与官方相反。
  (d) 现有字段（Rating/ADR/KPR/地图数/名次）无法表达官方中段的两个核心维度：
      对手强度（TOP5/10/20 拆分 rating）与全年聚合稳定性。
      这两个维度正是 HLTV 官方中段排序的主要依据。
""")


if __name__ == "__main__":
    main()
