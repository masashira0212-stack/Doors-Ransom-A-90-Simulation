# -*- mode: python ; coding: utf-8 -*-
from pathlib import Path

project_dir = Path(SPECPATH).resolve()
a = Analysis(
    [str(project_dir / "ransom_setting.py")],
    pathex=[str(project_dir)], binaries=[],
    datas=[(str(project_dir / "assets" / "ransom.ico"), "assets")],
    hiddenimports=[], hookspath=[], hooksconfig={}, runtime_hooks=[],
    excludes=["PIL", "pygame", "numpy", "pytest", "unittest"],
    noarchive=False, optimize=2,
)
pyz = PYZ(a.pure)
exe = EXE(
    pyz, a.scripts, a.binaries, a.datas,
    [("O", None, "OPTION"), ("O", None, "OPTION")],
    name="ransom_setting", debug=False, bootloader_ignore_signals=False,
    strip=False, upx=False, runtime_tmpdir=None, console=False,
    icon=[str(project_dir / "assets" / "ransom.ico")],
    version=str(project_dir / "settings_version_info.txt"),
    uac_admin=False, uac_uiaccess=False,
)
