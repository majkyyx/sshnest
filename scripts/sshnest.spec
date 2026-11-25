# Build with: .venv/bin/python -m PyInstaller --noconfirm --clean scripts/sshnest.spec
from pathlib import Path

root = Path(SPECPATH).parent
analysis = Analysis(
    [str(root / "scripts/pyinstaller_entry.py")],
    pathex=[str(root / "src")],
    datas=[(str(root / "assets/sshnest.svg"), "share/icons/hicolor/scalable/apps")],
    hiddenimports=[
        "gi.repository.Adw",
        "gi.repository.Gtk",
        "gi.repository.Gdk",
        "gi.repository.Gsk",
        "gi.repository.Pango",
    ],
    excludes=["PySide6", "PyQt6", "PyQt5", "tkinter"],
    hooksconfig={
        "gi": {
            "module-versions": {"Gtk": "4.0", "Gdk": "4.0"},
            "icons": ["Adwaita", "hicolor"],
            "themes": [],
            "languages": ["en"],
        }
    },
)
pyz = PYZ(analysis.pure)
exe = EXE(
    pyz,
    analysis.scripts,
    [],
    exclude_binaries=True,
    name="SshNest",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    console=False,
)
bundle = COLLECT(
    exe, analysis.binaries, analysis.datas, strip=False, upx=False, name="SshNest"
)
