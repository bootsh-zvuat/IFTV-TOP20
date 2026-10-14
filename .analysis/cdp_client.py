# -*- coding: utf-8 -*-
"""
鐢?Edge 鍐呯疆 CDP 椹卞姩鐪熷疄娴忚鍣ㄦ姄鍙?HLTV 閫夋墜椤碉紙闆剁涓夋柟渚濊禆锛夈€?
鍘熺悊锛?  Edge 鍩轰簬 Chromium锛屾敮鎸?--remote-debugging-port銆?  閫氳繃 CDP锛圕hrome DevTools Protocol锛夊彲浠ワ細
    1. 鎵撳紑鐪熷疄绐楀彛锛堥潪 headless锛夆€斺€?鐪熷疄娴忚鍣ㄨ兘姝ｅ父閫氳繃 Cloudflare JS 鎸戞垬
    2. Runtime.evaluate 璇诲彇娓叉煋鍚庣殑 DOM
    3. 閫愪釜閫夋墜瀵艰埅 + 鍙栨枃鏈?+ 淇濆瓨 HTML

涓嶇粫杩囦换浣曚繚鎶わ細鐢辩湡瀹?Edge 鑷瀹屾垚鎸戞垬锛岃剼鏈彧鏄?鑷姩鐐瑰紑椤甸潰骞惰缁撴灉"銆?
渚濊禆锛氫粎鏍囧噯搴擄紙鎵嬪啓 WebSocket 鎻℃墜涓庡抚瑙ｆ瀽锛夈€?"""
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


# ---------------- 鏋佺畝 WebSocket 瀹㈡埛绔紙RFC6455锛屼粎瀹㈡埛绔枃鏈抚锛?----------------
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
        if opcode == 0x9:  # ping -> 鍥?pong
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
        raise TimeoutError(f"CDP {method} 瓒呮椂")

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

