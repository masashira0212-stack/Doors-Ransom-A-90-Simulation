# PC v1.2.0: antivirus notes and release hashes

The application is a visual minigame. Reports of
`Trojan:Script/Wacatac.H!ml` have not been reproduced with this exact release
on the build PC. The cause of detection on other PCs remains unconfirmed.
This is not a claim that every detection is a false positive.

Both v1.2.0 EXEs passed their packaged self-tests and local Microsoft Defender
custom scans, which reported no threats (exit code 0; security-intelligence
version `1.459.79.0`). The builds are unsigned. A local clean scan does not
guarantee another antivirus, real-time scan or cloud decision.

| File | Bytes | SHA-256 |
| --- | ---: | --- |
| ransom.exe | 19,012,578 | `21357810D25F93E24B2526522FE06FE24C4B96E3BC4664CABB54A4B83D7A5DA7` |
| ransom_setting.exe | 11,138,030 | `0C19DF18594BE5AA3CDF66A51DED3A8E7F8B55EF9793745C961FC8B81796DDC4` |
| ransom_file.zip | 29,560,475 | `F6E22B173879645CFF3206843E9222A72ADAC6FCEE258F5FA3D43734FD0F3879` |

If a file is detected, preserve the detection name, exact file hash and antivirus
version. Do not disable protection, add exclusions or restore a quarantined
file merely to run the game. The exact file can be submitted to
[Microsoft for analysis](https://www.microsoft.com/en-us/wdsi/filesubmission).
Detection names alone do not identify a particular source-code line.

The runtime uses only explicit user-selected global command registrations;
key capture in the settings editor is local to that editor. The current
application does not encrypt files, steal data, install persistence, request
administrator rights, load drivers, or change system wallpaper/icon settings.
The legacy recovery helper is separate source, not bundled into the EXEs.
The source regression checks cover the game, configuration editor and hotkey
module. Packaging uses standard PyInstaller without UPX, obfuscation, random
padding or antivirus modifications.

This public document contains release facts only; personal settings, local
event logs and private diagnostic history are not part of the source download.
