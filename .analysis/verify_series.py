# -*- coding: utf-8 -*-
"""实测：用真实 API 数据验证逐图时间序列与稳定性指标。

只跑一个赛事（7909），确认：
  1. series 能正确累积
  2. 时间戳不缺失
  3. stability_metrics 输出合理（std 量级、trend 分布）
"""
import os
import sys
import importlib.util
import numpy as np

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))  # 项目根 = .analysis/ 的上一级
sys.path.insert(0, os.path.join(ROOT, "src"))
spec = importlib.util.spec_from_file_location("g", os.path.join(ROOT, "src", "gen_if_data_2025.py"))
g = importlib.util.module_from_spec(spec)
spec.loader.exec_module(g)

EID = 7909
print(f"=== 拉取赛事 {EID} ===")
matches = g.fetch_event_matches(EID)
print(f"比赛数={len(matches)}")
stats, n_calls = g.aggregate_player_stats(matches)
print(f"取数调用={n_calls}  选手数={len(stats)}")

n_ts_missing = 0
n_series = 0
lens = []
stds = []
trends = []
cvs = []
for pid, s in stats.items():
    ser = s.get("series") or []
    lens.append(len(ser))
    if any(ts is None for ts, _, _, _ in ser):
        n_ts_missing += 1
    m = g.stability_metrics(ser)
    if m:
        n_series += 1
        stds.append(m["std_r"])
        cvs.append(m["cv"])
        trends.append(m["trend"])

print(f"\n=== 序列健康度 ===")
print(f"有序列的选手={n_series}/{len(stats)}")
print(f"时间戳缺失的选手={n_ts_missing}")
print(f"逐图样本数: min={min(lens)} max={max(lens)} mean={np.mean(lens):.1f}")

print(f"\n=== 稳定性分布 ===")
print(f"std_r : min={min(stds):.3f} 中位={np.median(stds):.3f} max={max(stds):.3f}")
print(f"cv    : min={min(cvs):.3f} 中位={np.median(cvs):.3f} max={max(cvs):.3f}")
print(f"trend : min={min(trends):+.3f} 中位={np.median(trends):+.3f} max={max(trends):+.3f}")

print(f"\n=== 样例（按图数取前 5） ===")
top = sorted(stats.items(), key=lambda kv: -len(kv[1].get("series") or []))[:5]
for pid, s in top:
    m = g.stability_metrics(s.get("series") or [])
    rating = s["rating_w"] / s["rounds"] if s["rounds"] else 0
    print(f"  {s['name']:<14} 图数={s['maps']:<3} 赛内Rating={rating:.3f} "
          f"std={m['std_r']:.3f} cv={m['cv']:.3f} trend={m['trend']:+.3f}")

# 关键：std 是否与 rating 水平高度共线（若共线则信息冗余）
print(f"\n=== 冗余检查：std_r 与 赛内Rating 的相关性 ===")
pairs = []
for pid, s in stats.items():
    m = g.stability_metrics(s.get("series") or [])
    if m and s["rounds"]:
        pairs.append((s["rating_w"] / s["rounds"], m["std_r"]))
if len(pairs) > 3:
    a = np.array([p[0] for p in pairs])
    b = np.array([p[1] for p in pairs])
    print(f"  Pearson r = {np.corrcoef(a, b)[0,1]:+.3f}  (n={len(pairs)})")
    print(f"  若 |r| 接近 1 → std 只是 rating 的代理，无独立信息")
