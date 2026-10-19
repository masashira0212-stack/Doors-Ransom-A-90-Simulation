"""Settings validation, atomic saves, live reload, and single native cursor."""

from pathlib import Path
import tempfile
import time
import tkinter as tk
import unittest
import sys; from pathlib import Path; sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
import sys
import sys; from pathlib import Path; sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
from types import SimpleNamespace
from unittest.mock import patch

from ransom_config import (DEFAULT_SETTINGS, RansomSettings, failure_command_arguments,
                           load_settings, save_settings)
from doors_ransom import RansomSimulator, music_start_seconds


class SettingsPath:
    """One disposable path in the normal temp folder for atomic-save tests."""

    def __enter__(self) -> Path:
        handle = tempfile.NamedTemporaryFile(prefix="ransom-config-", suffix=".json", delete=False)
        self.path = Path(handle.name)
        handle.close()
        self.path.unlink(missing_ok=True)
        return self.path

    def __exit__(self, _type, _value, _traceback) -> None:
        self.path.unlink(missing_ok=True)


class ConfigTests(unittest.TestCase):
    def test_validation(self):
        self.assertEqual(RansomSettings.from_values("100", "5.5", "20"), RansomSettings(100, 5.5, 20))
        self.assertEqual(RansomSettings.from_values(9990, 1, 86400), RansomSettings(9990, 1, 86400))
        self.assertEqual(RansomSettings.from_values(0, 5, 20, 0), RansomSettings(0, 5, 20, 0))
        self.assertEqual(RansomSettings.from_values(5, 5, 20, "0.6"), RansomSettings(5, 5, 20, 0.6))
        for values in ((-1, 5, 20), (105, 5, 20), (10000, 5, 20), (True, 5, 20),
                       (100, 0, 20), (100, 30, 20), (100, 5, 86401),
                       (float("inf"), 5, 20), (100, "nan", 20), (100, 5, None),
                       (100, 5, 20, -0.1), (100, 5, 20, 5.1),
                       (100, 5, 20, "nan"), (100, 5, 20, True)):
            with self.subTest(values=values), self.assertRaises(ValueError):
                RansomSettings.from_values(*values)
        configured = RansomSettings.from_values(
            100, 5, 20, 0.25, "+", "-", "*", 1, 500, 75, 125,
            '"C:\\Program Files\\Example\\game.exe" --from-ransom',
        )
        self.assertEqual(configured.ransom_seconds, 75)
        self.assertEqual(configured.popup_scale_percent, 125)
        self.assertEqual(
            failure_command_arguments(configured.failure_command),
            ["C:\\Program Files\\Example\\game.exe", "--from-ransom"],
        )
        for command in ("game.exe", "cmd.exe /c whoami", "C:\\test.bat", "C:\\Windows\\System32\\WindowsPowerShell\\v1.0\\powershell.exe -Command x"):
            with self.subTest(command=command), self.assertRaises(ValueError):
                RansomSettings.from_values(100, 5, 20, failure_command=command)
        for duration, scale in ((9, 100), (101, 100), (90, 49), (90, 151), (90, 99.5)):
            with self.subTest(duration=duration, scale=scale), self.assertRaises(ValueError):
                RansomSettings.from_values(100, 5, 20, ransom_seconds=duration, popup_scale_percent=scale)

    def test_old_settings_default_grace(self):
        with patch("ransom_config.Path.read_text", return_value=(
            '{"version":1,"required_coins":100,"min_spawn_seconds":5,"max_spawn_seconds":20}'
        )):
            self.assertEqual(load_settings(Path("legacy.json")), RansomSettings(100, 5, 20, 0.25))

    def test_atomic_save(self):
        with SettingsPath() as path:
            self.assertEqual(load_settings(path), DEFAULT_SETTINGS)
            before_temporary_files = set(path.parent.glob("settings-*.tmp"))
            expected = RansomSettings(100, 5, 20, 0.65)
            save_settings(expected, path)
            before = path.read_bytes()
            with self.assertRaises(ValueError):
                save_settings(RansomSettings(105, 5, 20), path)
            self.assertEqual(path.read_bytes(), before)
            with patch("ransom_config.os.replace", side_effect=OSError("test interruption")):
                with self.assertRaises(OSError):
                    save_settings(RansomSettings(500, 45, 120), path)
            self.assertEqual(load_settings(path), expected)
            self.assertEqual(set(path.parent.glob("settings-*.tmp")), before_temporary_files)

    def test_live_reload_and_cursor(self):
        with SettingsPath() as path:
            save_settings(RansomSettings(100, 5, 20), path)
            root = tk.Tk()
            root.withdraw()
            app = RansomSimulator(root, settings_path=path, enable_shell_effects=False)
            app.audio.set_volume(0)
            app.volume_var.set(0)
            try:
                self.assertEqual(app.STARTING_BALANCE, 100)
                self.assertEqual(float(app.min_wait_var.get()), 5)
                app.arm()
                self.assertTrue(4.9 <= app.wait_deadline - time.monotonic() <= 20)
                old_sequence = app.wait_sequence
                save_settings(RansomSettings(200, 2, 2), path)
                app._refresh_saved_settings()
                self.assertEqual(app.STARTING_BALANCE, 200)
                self.assertGreater(app.wait_sequence, old_sequence)
                self.assertTrue(1.8 <= app.wait_deadline - time.monotonic() <= 2)
                waiting_deadline = app.wait_deadline
                save_settings(RansomSettings(200, 2, 2, 0.65), path)
                app._refresh_saved_settings()
                self.assertEqual(app.REACTION_ARM_DELAY_MS, 650)
                self.assertEqual(app.wait_deadline, waiting_deadline,
                                 "Changing STOP grace reset the spawn countdown")
                app._show_intro(old_sequence)
                self.assertEqual(app.stage, "waiting", "stale timer launched an encounter")

                # Do not change the active game's balance or deadline on save.
                app.start_ransom_preview()
                root.update()
                self.assertEqual(app.balance, 200)
                deadline = app.ransom_deadline
                save_settings(RansomSettings(100, 5, 20), path)
                app._refresh_saved_settings()
                self.assertEqual(app.balance, 200)
                self.assertEqual(app.ransom_deadline, deadline)
                self.assertEqual(app.STARTING_BALANCE, 100)
                self.assertEqual(app.REACTION_ARM_DELAY_MS, 250)
                self.assertIsNone(app.cursor_overlay)
                surfaces = [app.note_canvas] + [r["label"] for r in app.glitch_windows]
                surfaces += [r["canvas"] for r in app.coin_windows.values()]
                for surface in surfaces:
                    self.assertIn("red_cursor.cur", str(surface.cget("cursor")))
                coin_id, coin = next(iter(app.coin_windows.items()))
                event = SimpleNamespace(x_root=int(coin["x"] + 10), y_root=int(coin["y"] + 10))
                app._begin_coin_drag(coin_id, event)
                self.assertIn("red_cursor.cur", str(coin["canvas"].cget("cursor")))
                app._release_coin(coin_id, event)
                self.assertIn("red_cursor.cur", str(coin["canvas"].cget("cursor")))

                # A malformed update must not change the active configuration.
                with patch("doors_ransom.settings_signature", return_value=(1, 123)), \
                     patch("doors_ransom.load_settings", side_effect=ValueError("test malformed file")):
                    app._refresh_saved_settings()
                self.assertEqual(app.settings, RansomSettings(100, 5, 20))
                self.assertTrue(app.settings_error)
                app.start_ransom_preview()
                self.assertEqual(app.balance, 100)
            finally:
                app.quit_app()

    def test_failure_command_runs_once_without_shell(self):
        root = tk.Tk()
        root.withdraw()
        app = RansomSimulator(root, enable_shell_effects=False, use_saved_settings=False)
        app.audio.set_volume(0)
        command = f'"{Path(sys.executable)}" --version'
        app.encounter_settings = RansomSettings.from_values(100, 5, 20, failure_command=command)
        try:
            with patch("doors_ransom.subprocess.Popen") as launch:
                app._run_failure_command()
                app._run_failure_command()
            launch.assert_called_once()
            args, kwargs = launch.call_args
            self.assertEqual(args[0], [sys.executable, "--version"])
            self.assertFalse(kwargs["shell"])
            self.assertTrue(kwargs["close_fds"])
            self.assertEqual(kwargs["cwd"], str(Path(sys.executable).parent))
        finally:
            app.quit_app()

    def test_timer_music_sync_popup_scale_and_startup_guide(self):
        self.assertAlmostEqual(music_start_seconds(90), 11.55, places=2)
        self.assertAlmostEqual(music_start_seconds(10), 91.55, places=2)
        self.assertAlmostEqual(music_start_seconds(100), 1.55, places=2)
        root = tk.Tk()
        root.withdraw()
        app = RansomSimulator(root, enable_shell_effects=False, use_saved_settings=False)
        app.audio.set_volume(0)
        try:
            app.settings = RansomSettings.from_values(100, 5, 20, ransom_seconds=75, popup_scale_percent=50)
            app.stage = "ransom"
            app.encounter_settings = app.settings
            app._fit_note_to_screen()
            self.assertEqual(app.current_ransom_seconds, 90)
            self.assertLessEqual(app.note_scale, 0.5)
            app.show_startup_popup()
            root.update()
            self.assertTrue(app._window_exists(app.startup_window))
            def collect_text(widget: tk.Misc) -> list[str]:
                values: list[str] = []
                if "text" in widget.keys():
                    values.append(str(widget.cget("text")))
                for child in widget.winfo_children():
                    values.extend(collect_text(child))
                return values

            text = "\n".join(collect_text(app.startup_window))
            self.assertIn("ransom.exe started", text)
            self.assertIn(app.settings.exit_hotkey, text)
            app._dismiss_startup_popup()
            self.assertFalse(app._closing)
            self.assertFalse(app._window_exists(app.startup_window))
        finally:
            app.quit_app()

    def test_downloading_only_and_stop_grace(self):
        root = tk.Tk()
        root.withdraw()
        app = RansomSimulator(root, enable_shell_effects=False, use_saved_settings=False)
        app.audio.set_volume(0)
        app.volume_var.set(0)
        app.screen_width, app.screen_height = 640, 360
        try:
            for coins in (0, 1, 5, 10):
                with self.subTest(coins=coins):
                    app.stop_session()
                    app.STARTING_BALANCE = coins
                    app.armed = True
                    app.stage = "downloading"
                    app.overlay = tk.Toplevel(root)
                    app.overlay.withdraw()
                    app.overlay_canvas = tk.Canvas(app.overlay)
                    overlay = app.overlay
                    callbacks = []
                    with patch.object(app, "_later", side_effect=lambda delay, callback: callbacks.append((delay, callback))):
                        app._animate_downloading(app.DOWNLOADING_FRAMES - 1)
                    self.assertEqual(len(callbacks), 1)
                    self.assertEqual(callbacks[0][0], app.DOWNLOADING_END_DELAY_MS)
                    self.assertEqual(app.stage, "downloading", "Skipped the last bar frame")
                    with patch.object(app, "_create_note_window") as note, \
                         patch.object(app, "_ransom_success") as win, \
                         patch.object(app.audio, "play") as sound, \
                         patch.object(app.audio, "play_music") as music, \
                         patch.object(app.audio, "stop_all") as cut_audio:
                        callbacks[0][1]()
                        note.assert_not_called()
                        win.assert_not_called()
                        sound.assert_not_called()
                        music.assert_not_called()
                        cut_audio.assert_not_called()
                    self.assertEqual(app.stage, "waiting")
                    self.assertTrue(app.armed)
                    self.assertFalse(overlay.winfo_exists())
                    self.assertIsNone(app.thank_window)
                    self.assertFalse(app.coin_windows or app.glitch_windows)
                    self.assertGreater(app.wait_deadline, time.monotonic())

            app.stop_session()
            app.stage = "centering"
            app.REACTION_ARM_DELAY_MS = 650
            app.overlay = tk.Toplevel(root)
            app.overlay.withdraw()
            app.overlay_canvas = tk.Canvas(app.overlay)
            callbacks = []
            with patch.object(app, "_later", side_effect=lambda delay, callback: callbacks.append((delay, callback))):
                app._show_stop()
                self.assertEqual(app.stage, "reaction_grace")
                self.assertEqual(callbacks[0][0], 650)
                # A save while STOP is already visible must not reschedule it.
                app.REACTION_ARM_DELAY_MS = 0
                self.assertEqual(callbacks[0][0], 650)
                with patch.object(app, "_poll_pointer"):
                    callbacks[0][1]()
                self.assertEqual(app.stage, "reaction")
                self.assertEqual(callbacks[-1][0], 150)
        finally:
            app.quit_app()


if __name__ == "__main__":
    unittest.main(verbosity=2)
