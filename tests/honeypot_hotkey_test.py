"""Deterministic collectible and configurable-command regression tests."""

from dataclasses import replace
from pathlib import Path
import tempfile
import tkinter as tk
from types import SimpleNamespace
import unittest
import sys; from pathlib import Path; sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from unittest.mock import patch

from PIL import Image
from doors_ransom import ASSET_DIR, RansomSimulator, WM_HOTKEY
from hotkey_test import wait_until
from ransom_config import DEFAULT_SETTINGS, RansomSettings, load_settings, save_settings
from ransom_hotkeys import (binding_combinations, capture_binding, command_hotkeys,
                            DEFAULT_COMMAND_HOTKEYS, settings_has_focus, check_available)
from ransom_setting import SettingsWindow


class SettingsPath:
    """A disposable settings path that works with managed Windows temp ACLs."""

    def __enter__(self) -> Path:
        handle = tempfile.NamedTemporaryFile(prefix="ransom-hotkey-", suffix=".json", delete=False)
        self.path = Path(handle.name)
        handle.close()
        self.path.unlink(missing_ok=True)
        return self.path

    def __exit__(self, _type, _value, _traceback) -> None:
        self.path.unlink(missing_ok=True)


class NewSettingsTests(unittest.TestCase):
    def test_validation_and_round_trip(self):
        expected = RansomSettings.from_values(900, 5, 20, .25, "F6", "Ctrl+F7", "Shift+F8", 2.5, 750)
        with SettingsPath() as path:
            save_settings(expected, path)
            self.assertEqual(load_settings(path), expected)
        for changes in ({"honeypot_chance_percent": -1}, {"honeypot_chance_percent": 101},
                        {"honeypot_chance_percent": float("nan")}, {"honeypot_value": 0},
                        {"honeypot_value": 2.5}, {"honeypot_value": True},
                        {"trigger_hotkey": "*"}, {"exit_hotkey": "Shift+Equals"},
                        {"exit_hotkey": "F12"}, {"exit_hotkey": "Alt+F4"}):
            with self.subTest(changes=changes), self.assertRaises(ValueError):
                replace(DEFAULT_SETTINGS, **changes).validated()
        self.assertEqual(command_hotkeys(DEFAULT_SETTINGS), DEFAULT_COMMAND_HOTKEYS)

    def test_local_key_capture(self):
        self.assertEqual(capture_binding(SimpleNamespace(keycode=71, state=5)), "Ctrl+Shift+G")
        self.assertEqual(capture_binding(SimpleNamespace(keycode=117, state=0)), "F6")
        self.assertEqual(capture_binding(SimpleNamespace(keycode=187, state=1)), "Shift+Equals")
        self.assertEqual(capture_binding(SimpleNamespace(keycode=71, state=0x20000)), "Alt+G")
        self.assertEqual(capture_binding(SimpleNamespace(keycode=106, state=0x20000)), "Alt+NumMultiply")
        self.assertIsNone(capture_binding(SimpleNamespace(keycode=16, state=1)))
        self.assertEqual(binding_combinations("Ctrl+Shift+G"), ((6, 71),))
        self.assertEqual(binding_combinations("Alt+NumMultiply"), ((1, 106),))
        self.assertEqual(
            command_hotkeys(replace(DEFAULT_SETTINGS, exit_hotkey="Alt+NumMultiply"))[0x5257],
            ("exit", 0x4001, 106),
        )

    def test_settings_buttons(self):
        with SettingsPath() as path:
            root = tk.Tk()
            root.withdraw()
            window = SettingsWindow(root, path)
            try:
                window.begin_capture("trigger")
                self.assertFalse(window.save(), "Save accepted an unfinished capture")
                window._capture_key(SimpleNamespace(keysym="Shift_L", keycode=16, state=1))
                self.assertEqual(window.capturing, "trigger")
                window._capture_key(SimpleNamespace(keysym="F6", keycode=117, state=0))
                self.assertEqual(window.hotkeys["trigger"].get(), "F6")
                self.assertIsNone(window.capturing)
                window.begin_capture("restore")
                window._capture_key(SimpleNamespace(keysym="Escape"))
                self.assertEqual(window.hotkeys["restore"].get(), "-")
                window.honeypot_chance.set("100")
                window.honeypot_value.set("750")
                self.assertTrue(window.save())
                saved = load_settings(window.path)
                self.assertEqual((saved.trigger_hotkey, saved.honeypot_value), ("F6", 750))
                window.hotkeys["exit"].set("F6")
                self.assertFalse(window.save(), "Duplicate commands were saved")
                self.assertEqual(load_settings(window.path), saved)
                window.reset_hotkeys()
                self.assertEqual([v.get() for v in window.hotkeys.values()], ["+", "-", "*"])
                root.update_idletasks()
                self.assertLess(root.winfo_reqheight(), root.winfo_screenheight())
            finally:
                root.destroy()


class CollectibleTests(unittest.TestCase):
    def setUp(self):
        self.root = tk.Tk()
        self.root.withdraw()
        self.app = RansomSimulator(self.root, use_saved_settings=False, enable_shell_effects=False)
        self.app.audio.set_volume(0)
        self.app.stage = "ransom"

    def tearDown(self):
        self.app.quit_app()

    def test_probability_boundaries(self):
        for chance, sample, expected in ((0, 0, "coin_token.png"), (1, .009999, "honeypot.png"),
                                         (1, .01, "coin_token.png"), (100, .999999, "honeypot.png")):
            self.app.settings = replace(DEFAULT_SETTINGS, honeypot_chance_percent=chance)
            with self.subTest(chance=chance, sample=sample), patch.object(self.app.rng, "random", return_value=sample):
                self.assertEqual(self.app._choose_collectible()[0], expected)
        with Image.open(ASSET_DIR / "honeypot.png") as source:
            self.assertEqual(source.mode, "RGBA")
            self.assertEqual(source.getchannel("A").getextrema(), (0, 255))
            self.assertEqual(source.getpixel((0, 0))[3], 0)

    def test_honey_payment_once_and_no_natural_overlap(self):
        self.app.settings = replace(DEFAULT_SETTINGS, honeypot_chance_percent=100, honeypot_value=500)
        self.app.balance = 900
        with patch.object(self.app, "_later"), patch.object(self.app, "_repair_ransom_visibility"), \
             patch.object(self.app, "_restack_ransom_windows"), \
             patch.object(self.app, "_ransom_success") as success:
            self.app._spawn_coin()
            coin_id, item = next(iter(self.app.coin_windows.items()))
            self.assertEqual((item["asset"], item["value"]), ("honeypot.png", 500))
            self.app._collect_coin(coin_id)
            self.assertEqual(self.app.balance, 900)
            self.assertIn(coin_id, self.app.coin_windows)
            self.app._begin_coin_drag(coin_id, SimpleNamespace(x_root=item["x"] + 5, y_root=item["y"] + 5))
            self.app.settings = replace(self.app.settings, honeypot_value=200)
            self.app._collect_coin(coin_id)
            self.app._collect_coin(coin_id)
            self.assertEqual(self.app.balance, 400, "The existing pot changed value or paid twice")
            success.assert_not_called()
            self.app._spawn_coin()
            cid, item = next(iter(self.app.coin_windows.items()))
            item["user_armed"] = True
            self.app.balance = 100
            self.app._collect_coin(cid)
            self.assertEqual(self.app.balance, 0)
            success.assert_called_once()

    def test_drag_and_throw_use_honey_value(self):
        self.app.settings = replace(DEFAULT_SETTINGS, honeypot_chance_percent=100)
        with patch.object(self.app, "_later"), patch.object(self.app, "_repair_ransom_visibility"), \
             patch.object(self.app, "_restack_ransom_windows"):
            self.app.balance = 2000
            for thrown in (False, True):
                self.app._spawn_coin()
                cid, item = next(iter(self.app.coin_windows.items()))
                event = SimpleNamespace(x_root=item["x"] + 5, y_root=item["y"] + 5)
                self.app._begin_coin_drag(cid, event)
                if thrown:
                    item["dragging"] = False
                    item["moving"] = True
                    item["velocity_x"] = 8
                    with patch.object(self.app, "_coin_hits_note", return_value=True):
                        self.app._animate_coin_motion(cid, item["motion_generation"])
                else:
                    with patch.object(self.app, "_coin_pointer_position", return_value=(150, 250)), \
                         patch.object(self.app, "_coin_hits_note", return_value=True):
                        self.app._animate_coin_drag(cid, item["motion_generation"])
                self.assertNotIn(cid, self.app.coin_windows)
            self.assertEqual(self.app.balance, 1000)


class NativeHotkeyTests(unittest.TestCase):
    def test_settings_focus_pauses_actions_except_exit(self):
        with SettingsPath() as path:
            root = tk.Tk()
            root.withdraw()
            app = RansomSimulator(root, use_saved_settings=False, enable_global_hotkeys=True,
                                  enable_shell_effects=False)
            settings_root = tk.Toplevel(root)
            editor = SettingsWindow(settings_root, path)
            try:
                self.assertTrue(app.global_hotkey_ready.wait(2))
                root.update()
                app.settings = replace(app.settings, exit_hotkey="Alt+NumMultiply")
                app._sync_global_hotkeys()
                wait_until(root, lambda: 0x5257 in app.global_hotkey_registered_ids)
                settings_root.focus_force()
                root.update()
                if not settings_has_focus():
                    self.skipTest("Windows foreground lock prevents this interactive focus test")
                expected_exit_ids = {
                    command_id for command_id, row in app.global_hotkeys.items()
                    if row[0] == "exit"
                }
                wait_until(root, lambda: app.global_hotkey_registered_ids == expected_exit_ids)
                # Exit must still be routed while the editor owns focus; this
                # is the path used by Alt+NumMultiply (Alt+*) too.
                with patch.object(app, "quit_app") as quit_app:
                    app.global_hotkey_events.put((app.global_hotkey_revision, "exit"))
                    wait_until(root, lambda: quit_app.call_count == 1)
                editor.begin_capture("trigger")
                root.update()
                editor.hotkey_buttons["trigger"].event_generate("<KeyPress-F6>")
                root.update()
                self.assertEqual(editor.hotkeys["trigger"].get(), "F6")
                self.assertIsNone(editor.capturing)
                settings_root.destroy()
                wait_until(root, lambda: app.global_hotkey_registered_ids == set(app.global_hotkeys))
            finally:
                if settings_root.winfo_exists():
                    settings_root.destroy()
                app.quit_app()

    def test_live_rebind_suspend_resume_and_stale_messages(self):
        import ctypes
        with SettingsPath() as path, patch("doors_ransom.settings_has_focus", return_value=False) as focus:
            root = tk.Tk()
            root.withdraw()
            app = RansomSimulator(root, settings_path=path, enable_global_hotkeys=True, enable_shell_effects=False)
            app.audio.set_volume(0)
            try:
                self.assertTrue(app.global_hotkey_ready.wait(2))
                revision = app.global_hotkey_revision
                updated = replace(DEFAULT_SETTINGS, trigger_hotkey="Ctrl+F6", restore_hotkey="Ctrl+F7", exit_hotkey="Ctrl+F8")
                save_settings(updated, path)
                app._refresh_saved_settings()
                expected = command_hotkeys(updated)
                wait_until(root, lambda: app.global_hotkey_registered_ids == set(expected))
                with patch.object(app, "_run_command") as run:
                    app.global_hotkey_events.put((revision, "exit"))
                    # A replaced key's queued native message must not invoke the new binding.
                    ctypes.windll.user32.PostThreadMessageW(app.global_hotkey_thread_id, WM_HOTKEY, 0x5253, 0x6B << 16)
                    drained = []
                    root.after(75, lambda: drained.append(True))
                    wait_until(root, lambda: bool(drained))
                    run.assert_not_called()
                    command, modifiers, key = expected[0x5253]
                    ctypes.windll.user32.PostThreadMessageW(app.global_hotkey_thread_id, WM_HOTKEY, 0x5253,
                                                          (key << 16) | (modifiers & 0xF))
                    wait_until(root, lambda: run.call_count == 1)
                    run.assert_called_with(command)
                focus.return_value = True
                app._sync_global_hotkeys()
                expected_exit_ids = {
                    command_id for command_id, row in expected.items()
                    if row[0] == "exit"
                }
                wait_until(root, lambda: app.global_hotkey_registered_ids == expected_exit_ids)
                with patch.object(app, "_run_command") as run:
                    app.global_hotkey_events.put((app.global_hotkey_revision, "exit"))
                    wait_until(root, lambda: run.call_count == 1)
                    run.assert_called_once_with("exit")
                focus.return_value = False
                app._sync_global_hotkeys()
                wait_until(root, lambda: app.global_hotkey_registered_ids == set(expected))
                # Replaced keys are now ordinary input inside the game too.
                with patch.object(app, "_run_command") as run:
                    app._on_key_press(SimpleNamespace(keysym="asterisk", char="*", keycode=106, state=0))
                    run.assert_not_called()
                    app._on_key_press(SimpleNamespace(keysym="F8", char="", keycode=119, state=4))
                    run.assert_called_once_with("exit")
            finally:
                app.quit_app()


if __name__ == "__main__":
    unittest.main(verbosity=2)
