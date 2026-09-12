# Doors-Ransom-A-90-Simulation

An unofficial, fan-made Windows desktop visual and audio simulator inspired by the Ransom/A-90 encounter in **DOORS**. It presents a deliberately intense encounter sequence: warning screens, a STOP phase, a downloading animation, a timed coin mini-game, and success or failure effects.

> This is a simulation, not ransomware. The application does not encrypt, delete, upload, or modify user files; it does not alter the wallpaper, taskbar, shortcuts, system icons, cursor, or input settings; and it does not require administrator privileges or use network communication.

This project is not affiliated with, endorsed by, or sponsored by LSPLASH or Roblox. See [docs/NOTICE.md](docs/NOTICE.md) for redistribution and asset-use information.

## Features

- Configurable encounter interval, required coins, STOP grace period, timer, and popup scale.
- Customizable global hotkeys for starting an encounter, restoring the desktop, and exiting.
- Drag-and-drop coin payment mini-game with optional honeypot coins.
- Visual and audio effects for encounter, success, and timeout states.
- Short pop-in and pop-out animations for interactive simulator windows.
- A portable release layout with separate simulator and settings applications.
- Built-in self-tests and automated regression tests.

## Safety and behavior

The simulator is designed for informed participants on an appropriate Windows system. It uses application-owned windows and normal input events delivered to those windows. It does not monitor arbitrary keyboard or mouse activity across the operating system.

The settings app includes an optional **Failure command**. It is empty by default. If configured, it may launch one absolute-path `.exe` with its arguments after a timeout only. Shells, batch files, and script hosts are rejected. Configure only software you trust.

The experience contains flashing visuals and loud sounds. Use with care.

## Running a release build

The portable release contains two folders which must remain intact:

| Path | Purpose |
| --- | --- |
| `release/ransom/ransom.exe` | Runs the encounter simulator. |
| `release/ransom_setting/ransom_setting.exe` | Edits and saves simulator settings. |

1. Start `ransom_setting.exe`, adjust settings, and choose **Save**.
2. Start `ransom.exe`. It waits in the background and starts encounters according to the configured interval.

Settings are stored per Windows user in `%LOCALAPPDATA%\DoorsRansomSafeSimulator\settings.json` and are shared by both applications.

### Default hotkeys

| Key | Action |
| --- | --- |
| `+` | Trigger an encounter immediately while waiting. |
| `-` | Restore the desktop and return to waiting. |
| `*` | Exit the application completely. |

The settings application can change these shortcuts. To launch the simulator without global hotkeys, use:

```powershell
.\ransom.exe --no-global-hotkeys
```

## Encounter flow

1. A face and STOP warning appear.
2. Input received by the STOP window during its detection period causes a failure sequence.
3. The downloading animation plays.
4. For coin requirements above 10, a timed RANSOM panel, glitch windows, and coins appear.
5. Drag coins onto the panel to reduce the balance. Reaching zero shows the success sequence; reaching the timer limit shows the failure sequence.

## Run from source

Requirements: Windows and Python 3.10 or later.

```powershell
python -m pip install -r requirements.txt
python ransom_setting.py
python doors_ransom.py
```

## Test

Run the complete test suite:

```powershell
.\run_tests.bat
```

Or run the simulator resource and runtime checks directly:

```powershell
python doors_ransom.py --self-test
python doors_ransom.py --runtime-self-test
python ransom_setting.py --self-test
```

Some GUI tests briefly show simulator effects. `shutdown_safety_test.py` only terminates child processes it creates; it does not shut down the computer.

## Build

Install the build dependencies and run the PowerShell build script:

```powershell
python -m pip install -r requirements-build.txt
powershell -NoProfile -ExecutionPolicy Bypass -File .\build_exe.ps1
```

The script builds portable folders under `release/`, runs checks against the packaged executables, and performs a local Microsoft Defender scan when the command-line scanner is available.

## Project layout

| Path | Description |
| --- | --- |
| `doors_ransom.py` | Main simulator application. |
| `ransom_setting.py` | Settings application. |
| `ransom_config.py` | Shared settings and validation. |
| `ransom_hotkeys.py` | Global hotkey support. |
| `assets/` and `sounds/` | Bundled visual, font, and audio assets. |
| `tests/` | Automated regression and smoke tests. |
| `docs/` | Notices, safety notes, and maintenance documentation. |

## License and credits

The source code is licensed under the [MIT License](LICENSE). Roboto Mono is distributed under the SIL Open Font License 1.1; its notice is in [assets/RobotoMono-OFL.txt](assets/RobotoMono-OFL.txt).

Third-party names, trademarks, images, and audio may have separate rights. Confirm you have permission for every included asset before redistributing a fork, release build, video, or asset bundle.
