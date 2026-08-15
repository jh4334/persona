from _common import ROOT, CHROMIUM
"""Cycle 18 verification: icons, manifest, favicon route."""
import json, sys, os
sys.path.insert(0, f"{ROOT}/src")
os.chdir(ROOT)

from fastapi.testclient import TestClient
import classroom_sim.web.server as server

client = TestClient(server.app)

# ① /favicon.ico가 200 (콘솔 404 노이즈 제거)
r = client.get("/favicon.ico")
assert r.status_code == 200 and r.headers["content-type"].startswith("image/"), r.status_code
print("① /favicon.ico OK")

# ② 매니페스트 제공 + 필수 필드
r = client.get("/static/manifest.webmanifest")
assert r.status_code == 200, r.status_code
m = json.loads(r.text)
assert m["display"] == "standalone" and m["short_name"] == "보이는 교실"
assert len(m["icons"]) >= 2
for icon in m["icons"]:
    ri = client.get(icon["src"])
    assert ri.status_code == 200, f"아이콘 없음: {icon['src']}"
print("② 매니페스트 + 아이콘 파일 OK")

# ③ index.html에 링크가 걸려 있는지
html = client.get("/").text
for needle in ('rel="manifest"', 'rel="apple-touch-icon"', 'rel="icon"', 'name="theme-color"'):
    assert needle in html, f"index.html에 {needle} 없음"
print("③ index.html 링크 OK")

# ④ 아이콘 크기 규격
from PIL import Image
from io import BytesIO
for path, size in (("/static/icon-192.png", 192), ("/static/icon-512.png", 512),
                   ("/static/apple-touch-icon.png", 180)):
    img = Image.open(BytesIO(client.get(path).content))
    assert img.size == (size, size), f"{path}: {img.size}"
    assert img.mode == "RGBA"
print("④ 아이콘 크기 규격 OK")

print("CYCLE18 ALL PASS")
