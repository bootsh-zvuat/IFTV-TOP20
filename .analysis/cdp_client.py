# -*- coding: utf-8 -*-
"""
用 Edge 内置 CDP 驱动真实浏览器抓取 HLTV 选手页（零第三方依赖）。

原理：
  Edge 基于 Chromium，支持 --remote-debugging-port。
  通过 CDP（Chrome DevTools Protocol）可以：
    1. 打开真实窗口（非 headless）—— 真实浏览器能正常通过 Cloudflare JS 挑战
    2. Runtime.evaluate 读取渲染后的 DOM
    3. 逐个选手导航 + 取文本 + 保存 HTML

由真实 Edge 自行完成 Cloudflare 挑战，脚本只负责自动打开页面并读取结果。

依赖：仅标准库（手写 WebSocket 握手与帧解析）。
"""
import base64
import hashlib
import json
import os
import re
import secrets
import socket
import struct
import subprocess
import sys
import time
import urllib.request

EDGE = r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe"
PORT = 9411


# ---------------- 极简 WebSocket 客户端（RFC6455，仅客户端文本帧） ----------------
class WS:
    def __init__(self, url, timeout=20):
        m = re.match(r"ws://([^:/]+):(\d+)(/.*)", url)
        if not m:
            raise ValueError(f"bad ws url: {url}")
        host, port, path = m.group(1), int(m.group(2)), m.group(3)
        self.sock = socket.create_connection((host, port), timeout=timeout)
        self.sock.settimeout(timeout)
        key = base64.b64encode(secrets.token_bytes(16)).decode()
        req = (f"GET {path} HTTP/1.1\r\nHost: {host}:{port}\r\n"
               f"Upgrade: websocket\r\nConnection: Upgrade\r\n"
               f"Sec-WebSocket-Key: {key}\r\nSec-WebSocket-Version: 13\r\n\r\n")
        self.sock.sendall(req.encode())
        buf = b""
        while b"\r\n\r\n" not in buf:
            chunk = self.sock.recv(4096)
            if not chunk:
                raise ConnectionError("handshake closed")
            buf += chunk
        if b"101" not in buf.split(b"\r\n")[0]:
            raise ConnectionError(f"handshake failed: {buf.split(chr(13).encode())[0]}")
        self._buf = buf.split(b"\r\n\r\n", 1)[1]

    def _recv_exact(self, n):
        while len(self._buf) < n:
            chunk = self.sock.recv(65536)
            if not chunk:
                raise ConnectionError("closed")
            self._buf += chunk
        out, self._buf = self._buf[:n], self._buf[n:]
        return out

    def send(self, obj):
        payload = json.dumps(obj).encode()
        header = bytearray([0x81])  # FIN + text
        ln = len(payload)
        if ln < 126:
            header.append(0x80 | ln)
        elif ln < 65536:
            header.append(0x80 | 126)
            header += struct.pack(">H", ln)
        else:
            header.append(0x80 | 127)
            header += struct.pack(">Q", ln)
        mask = secrets.token_bytes(4)
        header += mask
        masked = bytes(b ^ mask[i % 4] for i, b in enumerate(payload))
        self.sock.sendall(bytes(header) + masked)

    def recv(self):
        b1, b2 = self._recv_exact(2)
        opcode = b1 & 0x0F
        ln = b2 & 0x7F
        if ln == 126:
            ln = struct.unpack(">H", self._recv_exact(2))[0]
        elif ln == 127:
            ln = struct.unpack(">Q", self._recv_exact(8))[0]
        data = self._recv_exact(ln)
        if opcode == 0x8:
            raise ConnectionError("ws closed by peer")
        if opcode == 0x9:  # ping：直接忽略，不回 pong
            return None
        return data.decode("utf-8", "ignore")

    def call(self, method, params=None, msg_id=1, timeout=30):
        self.send({"id": msg_id, "method": method, "params": params or {}})
        deadline = time.time() + timeout
        while time.time() < deadline:
            raw = self.recv()
            if raw is None:
                continue
            try:
                obj = json.loads(raw)
            except Exception:
                continue
            if obj.get("id") == msg_id:
                return obj
        raise TimeoutError(f"CDP {method} 超时")

    def close(self):
        try:
            self.sock.close()
        except Exception:
            pass


# ---------------- CDP HTTP ----------------
def cdp_get(path, port=PORT):
    with urllib.request.urlopen(f"http://127.0.0.1:{port}{path}", timeout=5) as r:
        return json.loads(r.read().decode())


def find_page_ws(port=PORT, want="hltv.org"):
    for t in cdp_get("/json/list", port):
        if t.get("type") == "page" and want in (t.get("url") or ""):
            return t.get("webSocketDebuggerUrl")
    return None


def eval_js(ws, expr, msg_id):
    r = ws.call("Runtime.evaluate",
                {"expression": expr, "returnByValue": True, "awaitPromise": True},
                msg_id=msg_id)
    res = r.get("result", {})
    if "exceptionDetails" in res:
        return None
    return res.get("result", {}).get("value")

