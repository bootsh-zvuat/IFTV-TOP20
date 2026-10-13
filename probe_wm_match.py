# -*- coding: utf-8 -*-
"""探查7：calender/eventList 与 getMatchList 结构"""
import json
import sys
import time

sys.path.insert(0, r"d:\demo\iftv")
from crawler import wm_get, log

# 1. calender/eventList 各种参数
log("=== 1. calender/eventList ===")
for params in ({"year": 2025}, {}):
    try:
        r = wm_get("/calender/eventList", params)
        s = json.dumps(r, ensure_ascii=False)
        log(f"params={params} -> len={len(s)}")
        log(s[:1200])
    except Exception as e:
        log(f"params={params} -> ERROR: {e}")
    time.sleep(0.4)

# 2. getMatchList 各种参数
log("\n=== 2. getMatchList ===")
for params in ({"eventId": 7524}, {"page": 1, "pageSize": 5}):
    try:
        r = wm_get("/getMatchList", params)
        s = json.dumps(r, ensure_ascii=False)
        log(f"params={params} -> len={len(s)}")
        log(s[:1200])
    except Exception as e:
        log(f"params={params} -> ERROR: {e}")
    time.sleep(0.4)
