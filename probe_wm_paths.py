# -*- coding: utf-8 -*-
"""探查6：完美 bundle 全部 API 路径"""
import re
import sys

sys.path.insert(0, r"d:\demo\iftv")
from crawler import request_get, HEADERS_WM, log

js = request_get("https://data.wanmei.com/asset/csgo/js/csgo-9ee1dfe5.js", headers=HEADERS_WM).text
log(f"bundle size: {len(js)}")
paths = sorted(set(re.findall(r'["\'](/[a-zA-Z0-9_/]+)["\']', js)))
for p in paths:
    log(p)
