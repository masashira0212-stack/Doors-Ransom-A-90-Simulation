"""Standalone editor for Ransom's payment target and random encounter delay."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys
import tempfile
import tkinter as tk
from tkinter import ttk

from ransom_config import DEFAULT_SETTINGS, RansomSettings, default_settings_path, load_settings, save_settings


class SettingsWindow:
    def __init__(self, root: tk.Tk, path: Path | None = None) -> None:
        self.root = root
        self.path = path if path is not None else default_settings_path()
        root.title("Ransom settings")
        root.resizable(False, False)
        asset_root = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
        try:
            root.iconbitmap(str(asset_root / "assets" / "ransom.ico"))
        except tk.TclError:
            pass

        # Use the default Windows controls without custom colors or branding.
        body = ttk.Frame(root, padding=12)
        body.grid(sticky="nsew")
        self.coins = tk.StringVar()
        self.minimum = tk.StringVar()
        self.maximum = tk.StringVar()
        self.stop_grace = tk.StringVar()
        self.status = tk.StringVar()

        ttk.Label(body, text="Required coins").grid(row=0, column=0, sticky="w", padx=(0, 12))
        self.coins_input = ttk.Spinbox(body, from_=0, to=9990, increment=10, textvariable=self.coins, width=12)
        self.coins_input.grid(row=0, column=1, sticky="ew", pady=4)
        ttk.Label(body, text="Minimum interval (seconds)").grid(row=1, column=0, sticky="w", padx=(0, 12))
        self.minimum_input = ttk.Spinbox(body, from_=1, to=86400, increment=1, textvariable=self.minimum, width=12)
        self.minimum_input.grid(row=1, column=1, sticky="ew", pady=4)
        ttk.Label(body, text="Maximum interval (seconds)").grid(row=2, column=0, sticky="w", padx=(0, 12))
        self.maximum_input = ttk.Spinbox(body, from_=1, to=86400, increment=1, textvariable=self.maximum, width=12)
        self.maximum_input.grid(row=2, column=1, sticky="ew", pady=4)
        ttk.Label(body, text="STOP grace (seconds)").grid(row=3, column=0, sticky="w", padx=(0, 12))
        self.stop_grace_input = ttk.Spinbox(body, from_=0, to=5, increment=0.05,
                                          textvariable=self.stop_grace, width=12)
        self.stop_grace_input.grid(row=3, column=1, sticky="ew", pady=4)
        ttk.Label(body, text="10 coins or less: end after Downloading.\nEach collected coin pays 10.").grid(
            row=4, column=0, columnspan=2, sticky="w", pady=(6, 0))
        self.status_label = ttk.Label(body, textvariable=self.status, justify="left", anchor="w", wraplength=330, width=47)
        self.status_label.grid(row=5, column=0, columnspan=2, sticky="ew", pady=(8, 10))
        buttons = ttk.Frame(body)
        buttons.grid(row=6, column=0, columnspan=2, sticky="e")
        ttk.Button(buttons, text="Save", command=self.save).pack(side="left", padx=(0, 6))
        ttk.Button(buttons, text="Close", command=root.destroy).pack(side="left")
        root.bind("<Control-s>", lambda event: self.save())
        root.bind("<Escape>", lambda event: root.destroy())
        try:
            self.fill(load_settings(self.path))
            self.status.set("Save to apply. Active minigames are not changed.")
        except (OSError, ValueError) as error:
            self.fill(DEFAULT_SETTINGS)
            self.status.set(f"Could not load settings: {error}")
        root.update_idletasks()
        width, height = root.winfo_reqwidth(), root.winfo_reqheight()
        # Keep automatic sizing so a wrapped validation error cannot hide Save.
        root.geometry(f"+{max(0, (root.winfo_screenwidth()-width)//2)}+{max(0, (root.winfo_screenheight()-height)//2)}")

    def fill(self, settings: RansomSettings) -> None:
        self.coins.set(str(settings.required_coins))
        self.minimum.set(f"{settings.min_spawn_seconds:g}")
        self.maximum.set(f"{settings.max_spawn_seconds:g}")
        self.stop_grace.set(f"{settings.stop_grace_seconds:g}")

    def save(self) -> bool:
        try:
            settings = RansomSettings.from_values(self.coins.get(), self.minimum.get(),
                                                  self.maximum.get(), self.stop_grace.get())
            save_settings(settings, self.path)
        except (ValueError, OSError) as error:
            self.status.set(str(error))
            return False
        self.status.set("Saved. The running app reloads automatically.")
        return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Ransom settings")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()
    if args.self_test:
        with tempfile.TemporaryDirectory(prefix="ransom-setting-test-") as directory:
            path = Path(directory) / "settings.json"
            root = tk.Tk()
            root.withdraw()
            window = SettingsWindow(root, path)
            expected = RansomSettings(10, 5, 20, 0.6)
            window.fill(expected)
            if not window.save() or load_settings(path) != expected:
                raise RuntimeError("Settings save/reload failed")
            window.minimum.set("30")
            if window.save() or load_settings(path) != expected:
                raise RuntimeError("Invalid settings overwrote the saved values")
            root.destroy()
        return 0
    root = tk.Tk()
    SettingsWindow(root)
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
