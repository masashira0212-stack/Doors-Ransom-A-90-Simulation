# Doors Ransom (A-90) Simulation

A fan-made recreation of the **Ransom / A-90-style experience from Roblox DOORS**, made as a harmless PC simulation.

> **Important:** This project is intended as a visual/gameplay simulation only. It is not real ransomware and should not encrypt, delete, steal, or lock user files.

## About

This project tries to recreate the look and feel of the DOORS Ransom/A-90 sequence as closely as possible on Windows.

- Fan-made recreation
- Focused on visual and audio accuracy
- Made for entertainment
- About 20% of the assets were created with AI assistance

## Download

### PC source code (before building)

[**Download the Windows source ZIP**](https://github.com/masashira0212-stack/Doors-Ransom-A-90-Simulation/archive/refs/heads/main.zip)

You can also click **Code → Download ZIP**. This contains the editable Python source for both `ransom.exe` and `ransom_setting.exe`, the images/audio/font, tests and build configuration. It is the **PC version**, not the Android project. EXEs, caches and personal settings are not included.

Source version: **1.1.6**. The download follows the latest code on `main`.

### Ready-to-run EXEs

Prebuilt downloads belong in the [Releases](https://github.com/masashira0212-stack/Doors-Ransom-A-90-Simulation/releases) section. Downloading source does not install or start the app.

If Windows SmartScreen shows a warning, that can happen with unsigned indie executables. Only download builds from this repository's official Releases page.

## Run or build the PC source

Extract the ZIP first. On Windows, open PowerShell in the extracted folder. Install Python with Tcl/Tk support; the tested build uses **CPython 3.13 x64**.

```powershell
py -3.13 -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements-build-tested.txt
.\.venv\Scripts\python.exe .\doors_ransom.py --self-test
.\.venv\Scripts\python.exe .\ransom_setting.py --self-test
```

Run the settings editor or game directly:

```powershell
.\.venv\Scripts\python.exe .\ransom_setting.py
.\.venv\Scripts\python.exe .\doors_ransom.py
```

Build both EXEs using the virtual environment's Python (activation is not required):

```powershell
$env:PATH = "$PWD\.venv\Scripts;$env:PATH"
powershell -NoProfile -ExecutionPolicy Bypass -File .\build_exe.ps1
```

The results are `release/ransom.exe` and `release/ransom_setting.exe`. Assets are already included; there is no need to regenerate images or audio. The script runs self-tests and, where available, checks the resulting main EXE with Microsoft Defender. It does not disable protection or add exclusions.

| File | Purpose |
| --- | --- |
| `doors_ransom.py` | Encounter, windows, coins, audio and hotkeys |
| `ransom_setting.py` | Simple settings editor |
| `ransom_config.py` | Settings validation and storage |
| `assets/`, `sounds/` | Required graphics, font and audio |
| `ransom.spec`, `ransom_setting.spec`, `build_exe.ps1` | EXE build configuration |
| `*_test.py`, `system_effects_smoke.py` | Verification scripts |
| `recovery_watchdog.py` | Optional manual recovery utility for older versions; not bundled or run by the current game |

Controls: **+** triggers an encounter, **-** dismisses it without exiting, **\*** exits completely. Configure coins, minimum/maximum interval and STOP grace in the settings editor. See [the detailed PC guide (Japanese)](PC_GUIDE_JA.md), [publication notice](NOTICE.md) and [false-positive information](FALSE_POSITIVE.md).

## Safety

This project is meant to remain a **harmless simulation**.

It should not:

- Encrypt or modify personal files
- Delete files
- Steal passwords or other data
- Install persistence
- Spread to other devices

If you fork or modify this project, please keep it safe and clearly label modified builds.

## Credits

- **Project:** CosMicExit
- **DOORS:** LSPLASH

This is an unofficial fan project and is **not affiliated with or endorsed by LSPLASH or Roblox**.

## AI Disclosure

This project was partially **vibe coded** with the help of AI tools during development.

## License

The source code in this repository is licensed under the [MIT License](LICENSE).

Game names, characters, sounds, images, and other third-party assets remain the property of their respective owners where applicable.
