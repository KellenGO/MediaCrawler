# -*- mode: python ; coding: utf-8 -*-
"""PyInstaller onedir build for the node-free Windows executable."""

from pathlib import Path
import shutil

from PyInstaller.utils.hooks import collect_all, collect_submodules


ROOT = Path(SPECPATH).resolve()

if not (ROOT / "webui" / "dist" / "index.html").is_file():
    raise SystemExit("webui/dist/index.html is required; run npm run build first")

node_exe = shutil.which("node")
if not node_exe:
    raise SystemExit("Node.js is required only on the build machine to bundle node.exe")

datas = [
    (str(ROOT / "webui" / "dist"), "webui/dist"),
    (str(ROOT / "webui" / "package.json"), "webui"),
]
datas.extend((str(path), "libs") for path in (ROOT / "libs").glob("*.js"))
binaries = [(node_exe, ".")]
hiddenimports = []

for package in ("playwright", "cv2", "PIL", "xhshow"):
    package_datas, package_binaries, package_hidden = collect_all(package)
    datas.extend(package_datas)
    binaries.extend(package_binaries)
    hiddenimports.extend(package_hidden)

for package in (
    "api",
    "aggregate_search",
    "base",
    "cache",
    "config",
    "constant",
    "media_platform",
    "model",
    "proxy",
    "tools",
    "uvicorn",
):
    hiddenimports.extend(collect_submodules(package))

hiddenimports.extend([
    "desktop_main",
    "base.frozen_runtime_smoke",
    "execjs",
    "fastapi",
    "httpx",
    "pydantic",
    "anyio",
    "websockets",
])

a = Analysis(
    [str(ROOT / "desktop_main.py")],
    pathex=[str(ROOT)],
    binaries=binaries,
    datas=datas,
    hiddenimports=sorted(set(hiddenimports)),
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=["tkinter"],
    noarchive=False,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz,
    a.scripts,
    exclude_binaries=True,
    name="MediaCrawler",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=True,
)
coll = COLLECT(
    exe,
    a.binaries,
    a.datas,
    a.zipfiles,
    strip=False,
    upx=False,
    name="MediaCrawler",
)
