# False-positive handling

`ransom.exe` is a local, fan-made visual simulator. Its runtime does not
encrypt, modify, or delete user files; create persistence; elevate privileges;
download code; use the network; or change the Windows wallpaper, taskbar,
desktop icons, or system cursor. It reads only its bundled artwork/audio and
the simulator settings file in `%LOCALAPPDATA%`; it may query the Windows work
area and desktop-item count solely to position its own visual windows.

The runtime has no OS-wide keyboard/mouse polling or hooks. It does register
only the three documented commands (`+`, `-`, and `*`) through the standard
Windows hotkey-message API, so the hidden simulator can be started, restored,
or closed without reading any other user input. The source and build
instructions are included in this project so a release can be inspected and
reproduced. `security_behavior_test.py` prevents these limits from accidentally
being broadened.

## If Microsoft Defender reports `Trojan:Script/Wacatac.H!ml`

Do not add a broad antivirus exclusion and do not disable protection. First
record the exact detection name, Defender security-intelligence version, and
SHA-256 of the exact `ransom.exe` release.

Then submit the exact EXE as a **good file / false positive** through the
[Microsoft Security Intelligence submission portal](https://www.microsoft.com/wdsi/filesubmission).
Select **No** when asked whether the file contains malware, include the exact
detection name, and retain the submission ID. Microsoft documents that it
reviews incorrectly detected files and can correct a false-positive detection:
[official submission guidance](https://learn.microsoft.com/en-us/unified-secops/submission-guide).

The local Defender scan included in `build_exe.ps1` is a check for the built
file on the build PC only. It cannot guarantee that cloud ML, SmartScreen, or a
different antivirus vendor will make the same decision. For public releases,
publish source, release hashes, and eventually distribute a code-signed build
from a verified publisher identity.
