# -*- mode: python ; coding: utf-8 -*-

from pathlib import Path


project_dir = Path(SPECPATH).resolve()
runtime_script = project_dir / "doors_ransom.py"

safe_asset_names = [
    "attack_face.png",
    "coin_token.png",
    "final_face.png",
    "flash_face.png",
    "glitch_1.png",
    "glitch_2.png",
    "glitch_3.png",
    "glitch_4.png",
    "glitch_5.png",
    "glitch_6.png",
    "ransom.ico",
    "red_cursor.cur",
    "ransom_face.png",
    "ransom_note.png",
    "ransom_note_reference.png",
    "stop.png",
    "stop_reference.png",
    "thank_you.png",
    "RobotoMono-VariableFont_wght.ttf",
    "RobotoMono-OFL.txt",
]

excluded_modules = [
    "numpy",
    "ssl",
    "hashlib",
    "asyncio",
    "multiprocessing",
    "PIL.AvifImagePlugin",
    "PIL.ImageCms",
    "PIL._imagingft",
    "PIL.WebPImagePlugin",
    "PIL.ImageMath",
    "pygame.freetype",
    "pygame.font",
    "pygame.image",
    "pygame.imageext",
    "pygame.camera",
    "pygame.joystick",
    "pygame.midi",
    "pygame.scrap",
    "pygame.surfarray",
    "pygame._sdl2",
    "pygame.examples",
    "pygame.tests",
    "pygame.display",
    "pygame.draw",
    # pygame.event is a runtime dependency of pygame.mixer.
    "pygame.key",
    "pygame.mouse",
    "pygame.cursors",
    "pygame.sprite",
    "pygame.threads",
    "pygame.pixelcopy",
    "pygame.surface",
    "pygame.mask",
    "pygame.pixelarray",
    "pygame.overlay",
    "pygame.time",
    "pygame.transform",
    "pygame.sndarray",
    "pygame.fastevent",
]

a = Analysis(
    [str(runtime_script)],
    pathex=[str(project_dir)],
    binaries=[],
    datas=[
        *[(str(project_dir / "assets" / name), "assets") for name in safe_asset_names],
        (str(project_dir / "sounds"), "sounds"),
    ],
    hiddenimports=[],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=excluded_modules,
    noarchive=False,
    optimize=2,
)

# PyInstaller's generic Pillow/pygame hooks collect every optional codec,
# renderer and font backend. This app uses Pillow only for PNG operations and
# pygame only for its mixer. Keep the mixer, its event dependency and pygame's
# required core modules; discard optional binaries plus duplicate root DLLs.
drop_root_binaries = {
    "sdl2.dll",
    "sdl2_mixer.dll",
    "sdl2_ttf.dll",
    "sdl2_image.dll",
    "freetype.dll",
    "libjpeg-9.dll",
    "libpng16-16.dll",
    "libwebp-7.dll",
    "libtiff-5.dll",
}
drop_pygame_modules = {
    "_freetype",
    "display",
    "draw",
    "key",
    "mask",
    "mouse",
    "pixelarray",
    "pixelcopy",
    "surface",
    "time",
    "transform",
}
drop_pygame_files = {
    "freetype.dll",
    "libjpeg-9.dll",
    "zlib1.dll",
}


def keep_binary(entry):
    destination = entry[0].replace("/", "\\").lower()
    if "\\" not in destination:
        return destination not in drop_root_binaries
    if not destination.startswith("pygame\\"):
        return True
    filename = destination.rsplit("\\", 1)[-1]
    module_name = filename.split(".", 1)[0]
    return filename not in drop_pygame_files and module_name not in drop_pygame_modules


a.binaries = [entry for entry in a.binaries if keep_binary(entry)]
a.datas = [
    entry
    for entry in a.datas
    if entry[0].replace("/", "\\").lower()
    not in {"pygame\\freesansbold.ttf", "pygame\\pygame_icon.bmp"}
]

pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [("O", None, "OPTION"), ("O", None, "OPTION")],
    name="ransom",
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=False,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=[str(project_dir / "assets" / "ransom.ico")],
    version=str(project_dir / "version_info.txt"),
    uac_admin=False,
    uac_uiaccess=False,
)
