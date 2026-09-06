"""Settings validation, atomic saves, live reload, and single native cursor."""

from pathlib import Path
import tempfile
import time
import tkinter as tk
import unittest
from types import SimpleNamespace
from unittest.mock import patch

from ransom_config import DEFAULT_SETTINGS, RansomSettings, load_settings, save_settings
from doors_ransom import RansomSimulator


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

    def test_old_settings_default_grace(self):
        with patch("ransom_config.Path.read_text", return_value=(
            '{"version":1,"required_coins":100,"min_spawn_seconds":5,"max_spawn_seconds":20}'
        )):
            self.assertEqual(load_settings(Path("legacy.json")), RansomSettings(100, 5, 20, 0.25))

    def test_atomic_save(self):
        with tempfile.TemporaryDirectory(prefix="ransom-config-") as folder:
            path = Path(folder) / "settings.json"
            self.assertEqual(load_settings(path), DEFAULT_SETTINGS)
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
            self.assertEqual(list(path.parent.glob("*.tmp")), [])

    def test_live_reload_and_cursor(self):
        with tempfile.TemporaryDirectory(prefix="ransom-live-settings-") as folder:
            path = Path(folder) / "settings.json"
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
