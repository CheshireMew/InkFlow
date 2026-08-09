# Build the frontend first: cd frontend && npm ci && npm run build

from PyInstaller.utils.hooks import collect_submodules


hiddenimports = collect_submodules("keyring.backends")
datas = [
    ("frontend/dist", "frontend/dist"),
    ("src/inkflow/migrations", "inkflow/migrations"),
    ("src/inkflow/prompt_files", "inkflow/prompt_files"),
]

analysis = Analysis(
    ["src/inkflow/cli.py"],
    pathex=["src"],
    binaries=[],
    datas=datas,
    hiddenimports=hiddenimports,
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
)
pyz = PYZ(analysis.pure)
executable = EXE(
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="inkflow",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    console=True,
)
bundle = COLLECT(
    executable,
    analysis.binaries,
    analysis.datas,
    strip=False,
    upx=True,
    name="InkFlow",
)
