# Ransom PC: Defender investigation (2026-09-07)

## Current report from the user

The continuing detection is on a friend's PC: after download, the EXE is
detected while present in Explorer and disappears. The friend's exact file
hash, security-intelligence version and event details have not been supplied.
This report cannot identify that file with the old local detection just from
its name. We did not access or modify the friend's computer.

## Confirmed locally

- Microsoft Defender is in Normal mode, with antivirus and real-time protection enabled.
- Current security-intelligence version at inspection: `1.459.79.0`.
- Ten detection-history records mention this project or its desktop copies.
- The latest matching detection was `2026-09-05 16:38:42` (local time), named
  `Trojan:Script/Wacatac.H!ml`, threat ID `2147814524`.
- Event 1116 identifies real-time protection / fast-path detection and
  `explorer.exe` accessing the release EXE. Its intelligence version was
  `1.459.58.0`. The threat record says `DidThreatExecute=False`.
- The pre-update EXE present today was last written at `2026-09-05 22:26:29`,
  later than the recorded detection. Its SHA-256 is
  `07128C3BC49B22BD9854A9DE50E81D0A206C9526224281BD97B7645FA20FF00D`.
- A custom Defender scan of that exact EXE returned exit code 0 and
  "found no threats". The diagnostic used `-DisableRemediation`, which leaves
  remediation off for this custom scan only and scans despite file exclusions.
  Real-time protection and other security settings were not changed.
- Both original release EXEs are unsigned. This is a verified packaging fact,
  **not proof that the missing signature caused this Trojan detection**.

## What this does and does not establish

The available event is a file-access detection, not evidence that the game
executed malicious behavior. However, a detection name is not sufficient to
declare an executable 100% safe or a false positive. Defender does not reveal
a matching Python line or its ML feature scores in these records.

The old detected bytes/hash are not available in the event, so the current
clean local result cannot establish that the previously detected build was
identical. Different builds, intelligence versions, download provenance and
cloud decisions remain possible explanations, not confirmed causes.
The history's IsActive field is retained as reported; it was not cleared or
used to infer that this current EXE is executing malware.

## Code and packaging review

Reviewed the current application, configuration editor, hotkey module, and
PyInstaller specifications. The current runtime contains no file encryption,
credential collection, network requests, startup persistence, UAC elevation,
keyboard hooks, driver loading, or real system wallpaper/icon/cursor changes.
The legacy recovery helper remains separate source and is not imported or
bundled by either executable.

Native window APIs operate on this application's own visual windows. Desktop
item count, taskbar/monitor bounds and foreground settings-window identity are
queried for placement and command suspension; these are not OS setting writes.
The application reads pointer positions for active STOP/drag interaction and
receives its own Tk input events. Only selected command keys are registered
globally via RegisterHotKey, not all keyboard input.

The single-file EXE is a standard PyInstaller package with UPX off and
`uac_admin=False`. No packer substitution, random padding, string hiding,
signature tampering, antivirus exclusion, or history deletion was used.

The behavior regression test now includes every application-owned runtime
module, including the new hotkey/settings code. The build gate now scans the
settings EXE as well as the game EXE. These checks are bounded regression and
local scan checks, not a guarantee of every antivirus/cloud decision.

## If the new build is detected elsewhere

Obtain the exact detection name, EXE SHA-256, antivirus/intelligence version,
and detection time. Compare the hash to the delivered build before assuming
the report concerns this version. Do not restore a quarantined EXE or disable
protection just to run it. If the reviewed exact build is incorrectly flagged,
submit it to Microsoft for analysis; no file was uploaded for analysis here.

Official references:

- [Get-MpThreatDetection](https://learn.microsoft.com/en-us/powershell/module/defender/get-mpthreatdetection)
- [Defender event IDs, including 1116](https://learn.microsoft.com/en-us/defender-endpoint/troubleshoot-microsoft-defender-antivirus)
- [Submit a file to Microsoft](https://www.microsoft.com/en-us/wdsi/filesubmission)

## Delivered 1.2.0 build

Both EXEs were rebuilt and passed their packaged self-tests. Defender custom
scans of each build and the candidate release directory returned exit code 0,
"found no threats", using the locally installed intelligence above.

| File | Bytes | SHA-256 |
| --- | ---: | --- |
| ransom.exe | 19,012,578 | `21357810D25F93E24B2526522FE06FE24C4B96E3BC4664CABB54A4B83D7A5DA7` |
| ransom_setting.exe | 11,138,030 | `0C19DF18594BE5AA3CDF66A51DED3A8E7F8B55EF9793745C961FC8B81796DDC4` |

These remain unsigned. A successful local scan is not a promise that the
friend's real-time/cloud detection will accept the same hash. The exact cause
of that remote detection remains unconfirmed.

Verification: all eight new collectible/configurable-hotkey regressions,
five existing settings tests, native default command delivery, runtime resource
checks, drag/payment and popup visibility tests passed. The forced-exit test
closed eight test-owned effect windows and left 40 desktop shortcuts, wallpaper,
taskbars and legacy recovery state unchanged. The interactive settings-focus
test initially could not acquire foreground focus due to Windows' foreground
lock; a later run acquired focus and passed, including actual Tk key capture
and release/re-registration of the existing command hotkeys.

## Image-edit provenance

`assets/honeypot.png` was produced with the built-in imagegen tool using the
user's attached honey-pot image as the edit target. Prompt: background-extraction
for a Windows collectible; remove only the black exterior background to actual
RGBA transparency; preserve the pot's low-poly shape, honey drips, colors,
lighting, orientation and full silhouette; add no text, new objects or shadow.
The generated alpha channel is preserved, and the image is stored in the
project rather than referenced from a temporary path.

Exact built-in imagegen prompt:

> Use case: background-extraction. Asset type: Windows minigame collectible sprite. Image 1 is the edit target. Remove only the black exterior background and produce a genuinely transparent RGBA PNG cutout. Preserve the exact honey pot: its low-poly shape, brown/orange material, olive-gold honey drips, current orientation, silhouette, original colors and lighting. Keep the entire pot visible, centered, tightly framed with a small transparent margin. Do not redesign, repaint, add details, add a shadow, add text, or put a checkerboard into the image. Change only the exterior background to actual alpha transparency; do not erase dark parts inside the pot.
