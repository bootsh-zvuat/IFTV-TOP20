# -*- coding: utf-8 -*-
"""探查21：5E 赛事列表候选端点"""
import os
import sys
import time

# 让 tools/ 下的脚本能导入 ../src/ 的模块（相对本文件，跨机器可用）
sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "src"))
from crawler import request_post, request_get, HEADERS_5E, E5_BASE, log

candidates = [
    "/v1/api/csgo/events/list",
    "/v1/api/csgo/event/list",
    "/v1/api/csgo/tournament",
    "/v1/api/csgo/match/events",
    "/v1/api/csgo/mfilter/tournament/list",
    "/v1/api/csgo/mfilter/events",
]
for path in candidates:
    url = path if path.startswith("http") else ("https://esports-data.5eplaycdn.com" + path)
    try:
        r = request_post(url, {"page": 1, "time_value": "2025-01-01 00:00:00_2025-12-31 23:59:59"}, HEADERS_5E)
        log(f"POST {path} -> {r.status_code} {r.text[:300]}")
    except Exception as e:
        log(f"POST {path} -> ERROR: {e}")
    time.sleep(0.3)

# 顺带试 GET /csgo/events 页面里嵌入的数据
try:
    html = request_get("https://event.5eplay.com/csgo/events", headers=HEADERS_5E).text
    log(f"\nevents page len={len(html)}")
    import re
    for m in re.finditer(r"(esports-data[^\"']+|/v1/api[^\"']+)", html):
        log(m.group(0)[:120])
except Exception as e:
    log(f"events page ERROR: {e}")
