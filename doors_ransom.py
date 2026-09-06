from __future__ import annotations

import argparse
import ctypes
import math
import os
import queue
import random
import sys
import threading
import time
import wave
from pathlib import Path
from typing import Any, Callable

import tkinter as tk
import tkinter.font as tkfont
from PIL import Image, ImageDraw, ImageOps, ImageTk

from ransom_config import DEFAULT_SETTINGS, default_settings_path, load_settings, settings_signature


APP_NAME = "RANSOM"
ASSET_NAMES = (
    "ransom_face.png",
    "attack_face.png",
    "final_face.png",
    "flash_face.png",
    "stop.png",
    "stop_reference.png",
    "glitch_1.png",
    "glitch_2.png",
    "glitch_3.png",
    "glitch_4.png",
    "glitch_5.png",
    "glitch_6.png",
    "ransom_note.png",
    "coin_token.png",
    "thank_you.png",
)
SYNTH_SOUND_NAMES = (
    "stop_static.wav",
    "attack.wav",
    "ransom_loop.wav",
    "coin.wav",
    "failure.wav",
)
USER_SOUND_NAMES = (
    "jumpscare1.mp3",
    "jumpscare2.mp3",
    "ransom_ost_to_jumpscare.mp3",
    "ransom_success.ogg",
)
SOUND_NAMES = SYNTH_SOUND_NAMES + USER_SOUND_NAMES
MUSIC_NAME = "ransom_ost_to_jumpscare.mp3"
# Play the original compressed source from its late section. Its supplied final
# jump begins at 101.55s, exactly 90 seconds after this seek point.
MUSIC_START_SECONDS = 11.55
TRANSPARENT_KEY = "#010203"
RANSOM_FONT_BOLD = "Roboto Mono SemiBold"
RANSOM_FONT_MEDIUM = "Roboto Mono Medium"

# These are the only OS-wide input registrations in the app.  They are
# explicit user commands, not a keyboard/mouse hook and not state polling.
# A user can therefore trigger or close the hidden simulator without the
# program observing any other input in Windows.
WM_HOTKEY = 0x0312
WM_QUIT = 0x0012
MOD_SHIFT = 0x0004
MOD_NOREPEAT = 0x4000
GLOBAL_COMMAND_HOTKEYS: dict[int, tuple[str, int, int]] = {
    0x5253: ("test", MOD_NOREPEAT, 0x6B),  # numpad +
    0x5254: ("test", MOD_NOREPEAT | MOD_SHIFT, 0xBB),  # main +
    0x5255: ("restore", MOD_NOREPEAT, 0x6D),  # numpad -
    0x5256: ("restore", MOD_NOREPEAT, 0xBD),  # main -
    0x5257: ("exit", MOD_NOREPEAT, 0x6A),  # numpad *
    0x5258: ("exit", MOD_NOREPEAT | MOD_SHIFT, 0x38),  # Shift+8
    0x5259: ("exit", MOD_NOREPEAT | MOD_SHIFT, 0xBA),  # Japanese Shift+:/*
    0x525A: ("test", MOD_NOREPEAT, 0xBB),  # + labelled key, as in previous releases
}

def resource_root() -> Path:
    bundled = getattr(sys, "_MEIPASS", None)
    if bundled:
        return Path(bundled)
    return Path(__file__).resolve().parent


RESOURCE_ROOT = resource_root()
ASSET_DIR = RESOURCE_ROOT / "assets"
SOUND_DIR = RESOURCE_ROOT / "sounds"
RANSOM_FONT_FILE = ASSET_DIR / "RobotoMono-VariableFont_wght.ttf"


def install_private_ransom_font() -> bool:
    """Load the bundled UI font for this process without installing it in Windows."""
    if os.name != "nt" or not RANSOM_FONT_FILE.is_file():
        return False
    try:
        gdi32 = ctypes.windll.gdi32
        gdi32.AddFontResourceExW.argtypes = [ctypes.c_wchar_p, ctypes.c_uint, ctypes.c_void_p]
        gdi32.AddFontResourceExW.restype = ctypes.c_int
        return bool(gdi32.AddFontResourceExW(str(RANSOM_FONT_FILE), 0x10, None))  # FR_PRIVATE
    except Exception:
        return False




def resample_lanczos() -> int:
    return getattr(Image.Resampling, "LANCZOS", Image.LANCZOS)


def format_clock(seconds: float) -> str:
    whole = max(0, int(math.ceil(seconds)))
    minutes, remainder = divmod(whole, 60)
    return f"{minutes:02d}:{remainder:02d}"


def validate_resources() -> list[str]:
    problems: list[str] = []
    if not (ASSET_DIR / "red_cursor.cur").is_file():
        problems.append("missing application-local red cursor")
    if not RANSOM_FONT_FILE.is_file() or RANSOM_FONT_FILE.stat().st_size < 10_000:
        problems.append(f"missing or invalid UI font: {RANSOM_FONT_FILE}")
    for name in ASSET_NAMES:
        path = ASSET_DIR / name
        if not path.is_file():
            problems.append(f"missing asset: {path}")
            continue
        try:
            with Image.open(path) as image:
                image.verify()
        except Exception as exc:  # pragma: no cover - defensive startup check
            problems.append(f"invalid image {path}: {exc}")
    for name in SOUND_NAMES:
        path = SOUND_DIR / name
        if not path.is_file():
            problems.append(f"missing sound: {path}")
            continue
        suffix = path.suffix.lower()
        if suffix == ".mp3":
            try:
                prefix = path.read_bytes()[:3]
                if path.stat().st_size < 1024 or not (prefix == b"ID3" or prefix[:1] == b"\xff"):
                    problems.append(f"invalid MP3 sound: {path}")
            except OSError as exc:
                problems.append(f"invalid sound {path}: {exc}")
            continue
        if suffix == ".ogg":
            try:
                if path.stat().st_size < 1024 or path.read_bytes()[:4] != b"OggS":
                    problems.append(f"invalid OGG sound: {path}")
            except OSError as exc:
                problems.append(f"invalid sound {path}: {exc}")
            continue
        try:
            with wave.open(str(path), "rb") as wav_file:
                if wav_file.getnframes() <= 0:
                    problems.append(f"empty sound: {path}")
        except Exception as exc:  # pragma: no cover - defensive startup check
            problems.append(f"invalid sound {path}: {exc}")
    return problems


class AudioBank:
    """Small pygame wrapper. The visual experience still works if audio is unavailable."""

    def __init__(self, volume: float = 0.95) -> None:
        self.available = False
        self.volume = volume
        self._pygame: Any = None
        self._sounds: dict[str, Any] = {}
        self._channels: dict[str, Any] = {}
        self.music_active = False
        try:
            os.environ.setdefault("PYGAME_HIDE_SUPPORT_PROMPT", "1")
            import pygame

            pygame.mixer.pre_init(44_100, -16, 2, 512)
            pygame.mixer.init()
            pygame.mixer.set_num_channels(5)
            self._pygame = pygame
            self._channels = {
                "loop": pygame.mixer.Channel(0),
                "event": pygame.mixer.Channel(1),
                "coin": pygame.mixer.Channel(2),
                "warning": pygame.mixer.Channel(3),
                "attack": pygame.mixer.Channel(4),
            }
            for name in SOUND_NAMES:
                if name == MUSIC_NAME:
                    continue
                self._sounds[name] = pygame.mixer.Sound(str(SOUND_DIR / name))
            self.available = True
            self.set_volume(volume)
        except Exception:
            self.available = False

    def set_volume(self, volume: float) -> None:
        self.volume = max(0.0, min(1.0, volume))
        if not self.available:
            return
        self._channels["loop"].set_volume(self.volume * 0.52)
        self._channels["event"].set_volume(self.volume)
        self._channels["coin"].set_volume(self.volume * 0.32)
        self._channels["warning"].set_volume(self.volume)
        self._channels["attack"].set_volume(self.volume)
        self._pygame.mixer.music.set_volume(self.volume * 0.64)

    def ensure_ready(self) -> None:
        """Reopen the mixer if Windows suspended/lost the device during a long wait."""
        try:
            ready = bool(self.available and self._pygame is not None and self._pygame.mixer.get_init())
        except Exception:
            ready = False
        if not ready:
            self.__init__(self.volume)
        elif self.available:
            self.set_volume(self.volume)

    def reopen(self) -> None:
        """Force a fresh Windows audio-device connection after an idle wait."""
        volume = self.volume
        pygame_module = self._pygame
        if pygame_module is not None:
            try:
                pygame_module.mixer.quit()
            except Exception:
                pass
        self.__init__(volume)

    def play(
        self,
        name: str,
        channel: str = "event",
        loops: int = 0,
        fade_ms: int = 0,
    ) -> None:
        self.ensure_ready()
        if not self.available:
            return
        sound = self._sounds.get(name)
        output = self._channels.get(channel)
        if sound is not None and output is not None:
            try:
                output.play(sound, loops=loops, fade_ms=max(0, int(fade_ms)))
                if output.get_busy():
                    return
            except Exception:
                pass
        # A mixer can still report itself initialized after Windows has dropped
        # the idle audio endpoint. Reopen once and retry the requested sound.
        self.reopen()
        if not self.available:
            return
        sound = self._sounds.get(name)
        output = self._channels.get(channel)
        if sound is not None and output is not None:
            try:
                output.play(sound, loops=loops, fade_ms=max(0, int(fade_ms)))
            except Exception:
                pass

    def stop_channel(self, channel: str) -> None:
        if self.available and channel in self._channels:
            try:
                self._channels[channel].stop()
            except Exception:
                pass

    def play_music(self, name: str, start: float = 0.0) -> None:
        self.ensure_ready()
        if not self.available:
            return
        try:
            self._pygame.mixer.music.load(str(SOUND_DIR / name))
            self._pygame.mixer.music.set_volume(self.volume * 0.64)
            self._pygame.mixer.music.play(loops=0, start=max(0.0, start))
            self.music_active = True
        except Exception:
            self.music_active = False

    def music_is_playing(self) -> bool:
        if not self.available or not self.music_active:
            return False
        return bool(self._pygame.mixer.music.get_busy())

    def stop_all(self) -> None:
        if self.available:
            self._pygame.mixer.stop()
            self._pygame.mixer.music.stop()
            self.music_active = False

    def close(self) -> None:
        if self.available:
            self.stop_all()
            self._pygame.mixer.quit()


class RansomSimulator:
    DEFAULT_MIN_WAIT_SECONDS = DEFAULT_SETTINGS.min_spawn_seconds
    DEFAULT_MAX_WAIT_SECONDS = DEFAULT_SETTINGS.max_spawn_seconds
    INTRO_MIN_MS = 320
    INTRO_MAX_MS = 400
    INTRO_EXTRA_MAX_MS = 300
    # The face/centering phase never checks input. STOP is shown first, then a
    # brief human reaction allowance passes before the actual stop check begins.
    # Default STOP: 0.25s configured grace, followed by 0.15s detection.
    REACTION_ARM_DELAY_MS = 250
    REACTION_MS = 150
    POINTER_DEADZONE_PX = 14
    POINTER_CONFIRM_SAMPLES = 2
    RANSOM_SECONDS = 90.0
    STARTING_BALANCE = DEFAULT_SETTINGS.required_coins
    COIN_VALUE = 10
    COIN_HITBOX_PADDING = 36
    COIN_POPUP_BOUNCE = 0.78
    # Direct pointer sampling removes stale-motion jitter; 60fps is enough to
    # feel smooth without needlessly moving a native top-level window.
    COIN_DRAG_FRAME_MS = 16
    COIN_RETIRE_DELAY_MS = 24
    MAX_GLITCH_WINDOWS = 5
    MAX_COIN_WINDOWS = 8
    # Large redraw based on the supplied 315x185 layout reference.
    NOTE_WIDTH = 945
    NOTE_HEIGHT = 555
    GLITCH_FADE_STEP = 0.07
    ATTACK_DURATION_MS = 800
    ATTACK_FRAME_MS = 16
    FAILURE_DURATION_MS = 800
    FAILURE_FRAME_MS = 16
    FAILURE_FACE_SCALE = 0.82
    THANK_DISPLAY_MS = 1800
    THANK_CENTER_MS = 420
    THANK_INSERT_HOLD_MS = 90
    THANK_GROW_MS = 420
    THANK_FRAME_MS = 16
    THANK_MAX_WIDTH = 1020
    FRAME_DOT_SIZE = 4
    FRAME_DOT_SPACING = 4
    FRAME_OPACITY = 0.62
    DOWNLOADING_FRAMES = 31
    DOWNLOADING_SEGMENTS = 12
    # 30 frame intervals plus the final hold make the visual exactly 1.500s.
    # The untrimmed 2.612s attack MP3 stays on its own channel and continues
    # through the following RANSOM stage instead of being cut at this boundary.
    DOWNLOADING_FRAME_MS = 48
    DOWNLOADING_END_DELAY_MS = 60
    WAIT_WATCHDOG_MS = 250
    VISIBILITY_WATCHDOG_MS = 100

    def __init__(
        self,
        root: tk.Tk,
        demo_defaults: bool = False,
        headless: bool = True,
        enable_shell_effects: bool = True,
        bridge_result_path: Path | None = None,
        force_stop_failure: bool = False,
        exit_after_downloading: bool = False,
        settings_path: Path | None = None,
        use_saved_settings: bool = True,
        enable_global_hotkeys: bool = False,
    ) -> None:
        self.root = root
        self.settings_path = settings_path if settings_path is not None else default_settings_path()
        self.use_saved_settings = use_saved_settings
        self.settings_stamp = settings_signature(self.settings_path)
        self.settings_error = ""
        self.settings = DEFAULT_SETTINGS
        if use_saved_settings:
            try:
                self.settings = load_settings(self.settings_path)
            except (OSError, ValueError) as error:
                self.settings_error = str(error)
        self.STARTING_BALANCE = self.settings.required_coins
        self.REACTION_ARM_DELAY_MS = round(self.settings.stop_grace_seconds * 1000)
        # A one-element Tcl list preserves cursor paths containing spaces.
        # This replaces the native pointer only over our own widgets; Windows'
        # cursor scheme is never edited and there is no second pointer window.
        self.minigame_cursor = ("@" + (ASSET_DIR / "red_cursor.cur").as_posix(),) if os.name == "nt" else "arrow"
        self.rng = random.Random()
        self.audio = AudioBank()
        self.headless = headless
        self.enable_shell_effects = enable_shell_effects
        self.bridge_result_path = bridge_result_path
        self.bridge_result_written = False
        self.force_stop_failure = force_stop_failure
        self.exit_after_downloading = exit_after_downloading
        self.enable_global_hotkeys = enable_global_hotkeys and os.name == "nt"
        self.private_font_loaded = install_private_ransom_font()
        self.screen_width = root.winfo_screenwidth()
        self.screen_height = root.winfo_screenheight()
        self._fit_note_to_screen()
        try:
            self.root.iconbitmap(default=str(ASSET_DIR / "ransom.ico"))
        except tk.TclError:
            pass

        self.stage = "idle"
        self.armed = False
        self.after_ids: set[str] = set()
        self.preparation_after_ids: set[str] = set()
        self.wait_watchdog_after_id: str | None = None
        self.global_hotkey_after_id: str | None = None
        self.wait_deadline = 0.0
        self.wait_sequence = 0
        # Only input events delivered to this application's own Tk windows are
        # recorded.  There is deliberately no operating-system-wide keyboard
        # or mouse polling/hook, so the simulator cannot observe other apps.
        self.app_held_inputs: set[tuple[str, str]] = set()
        self.global_hotkey_events: queue.SimpleQueue[str] = queue.SimpleQueue()
        self.global_hotkey_stop = threading.Event()
        self.global_hotkey_ready = threading.Event()
        self.global_hotkey_thread: threading.Thread | None = None
        self.global_hotkey_thread_id = 0
        self.global_hotkey_registered_ids: set[int] = set()
        self.overlay: tk.Toplevel | None = None
        self.overlay_canvas: tk.Canvas | None = None
        self.intro_window: tk.Toplevel | None = None
        self.intro_sequence_id = 0
        self.intro_visible_since = 0.0
        self.intro_deadline = 0.0
        self.note_window: tk.Toplevel | None = None
        self.note_canvas: tk.Canvas | None = None
        self.note_base_x = 0
        self.note_base_y = 0
        self.note_jitter_tick = 0
        self.ransom_frame_window: tk.Toplevel | None = None
        self.ransom_frame_canvas: tk.Canvas | None = None
        self.ransom_frame_photos: list[tuple[ImageTk.PhotoImage, ImageTk.PhotoImage, ImageTk.PhotoImage, ImageTk.PhotoImage]] = []
        self.ransom_frame_items: list[int] = []
        self.ransom_frame_thickness = 0
        self.ransom_frame_tick = 0
        self.thank_window: tk.Toplevel | None = None
        self.thank_photo: ImageTk.PhotoImage | None = None
        self.thank_image_item: int | None = None
        self.thank_phase = ""
        self.glitch_windows: list[dict[str, Any]] = []
        self.glitch_window_target = 5
        self.coin_windows: dict[int, dict[str, Any]] = {}
        self.retiring_coin_windows: list[dict[str, Any]] = []
        self.face_flash_windows: list[dict[str, Any]] = []
        self.next_coin_id = 1
        self.photos: dict[str, ImageTk.PhotoImage] = {}
        self.source_images: dict[str, Image.Image] = {}
        self.face_red_source: Image.Image | None = None
        self.reaction_started = 0.0
        self.reaction_failed = False
        self.preheld_input_at_stop = False
        self.pointer_outside_samples = 0
        self.attack_deadline = 0.0
        self.failure_deadline = 0.0
        self.pointer_origin = (0, 0)
        self.balance = self.STARTING_BALANCE
        self.ransom_deadline = 0.0
        self.balance_item: int | None = None
        self.time_item: int | None = None
        self.event_count = 0
        self._closing = False
        self._recovering_callback_error = False
        self.error_log_path = (
            Path(os.environ.get("LOCALAPPDATA", str(Path.home())))
            / "DoorsRansomSafeSimulator"
            / "error.log"
        )

        self.desktop_overlay: tk.Toplevel | None = None
        self.desktop_canvas: tk.Canvas | None = None
        self.taskbar_overlay: tk.Toplevel | None = None
        self.taskbar_canvas: tk.Canvas | None = None
        self.cursor_overlay: tk.Toplevel | None = None
        self.cursor_canvas: tk.Canvas | None = None
        self.cursor_item: int | None = None
        self.shell_icon_records: list[dict[str, Any]] = []
        self.shell_photo_cache: dict[int, list[ImageTk.PhotoImage]] = {}
        self.secondary_monitor_overlays: list[dict[str, Any]] = []
        self.secondary_monitor_photos: dict[tuple[int, int], ImageTk.PhotoImage] = {}
        self.system_effects_active = False

        self.min_wait_var = tk.StringVar(
            value="3" if demo_defaults else str(self.settings.min_spawn_seconds)
        )
        self.max_wait_var = tk.StringVar(
            value="5" if demo_defaults else str(self.settings.max_spawn_seconds)
        )
        self.repeat_var = tk.BooleanVar(value=True)
        self.volume_var = tk.IntVar(value=95)
        self.status_var = tk.StringVar(value="停止中")

        self._load_sources()
        # Prepare the four edge cels while the app is still hidden/waiting.  The
        # encounter can then switch real textures without stalling its audio.
        self.preparation_after_ids.add(self.root.after_idle(self._prepare_ransom_border_textures))
        self.preparation_after_ids.add(self.root.after_idle(self._prepare_secondary_monitor_photos))
        if self.headless:
            self.root.withdraw()
        else:
            self._build_controller()
        self.root.bind_all("<KeyPress>", self._on_key_press, add="+")
        self.root.bind_all("<KeyRelease>", self._on_key_release, add="+")
        self.root.bind_all("<ButtonPress>", self._on_pointer_press, add="+")
        self.root.bind_all("<ButtonRelease>", self._on_pointer_release, add="+")
        self.root.bind_all("<MouseWheel>", self._on_pointer_press, add="+")
        self.root.protocol("WM_DELETE_WINDOW", self.quit_app)
        self.root.report_callback_exception = self._handle_tk_callback_exception
        self._start_global_command_listener()
        self._poll_waiting_deadline()

    # ---------- controller ----------

    def _start_global_command_listener(self) -> None:
        """Register only the documented +, -, and * commands on Windows.

        The listener receives WM_HOTKEY messages for these exact combinations;
        it never enumerates keys, captures text, or reads mouse state.  Tk is
        only touched on its main thread after the command is queued.
        """
        if not self.enable_global_hotkeys or self._closing:
            return
        self.global_hotkey_thread = threading.Thread(
            target=self._global_command_listener,
            name="RansomCommandHotkeys",
            daemon=True,
        )
        self.global_hotkey_thread.start()
        self.global_hotkey_after_id = self.root.after(25, self._drain_global_commands)

    def _global_command_listener(self) -> None:
        if os.name != "nt":
            self.global_hotkey_ready.set()
            return

        class POINT(ctypes.Structure):
            _fields_ = [("x", ctypes.c_long), ("y", ctypes.c_long)]

        class MSG(ctypes.Structure):
            _fields_ = [
                ("hwnd", ctypes.c_void_p),
                ("message", ctypes.c_uint),
                ("wParam", ctypes.c_size_t),
                ("lParam", ctypes.c_ssize_t),
                ("time", ctypes.c_uint),
                ("pt", POINT),
                ("lPrivate", ctypes.c_uint),
            ]

        user32 = ctypes.windll.user32
        kernel32 = ctypes.windll.kernel32
        message = MSG()
        try:
            # Make this worker's message queue before registering hotkeys.
            user32.PeekMessageW(ctypes.byref(message), None, 0, 0, 0)
            self.global_hotkey_thread_id = int(kernel32.GetCurrentThreadId())
            user32.RegisterHotKey.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_uint, ctypes.c_uint]
            user32.RegisterHotKey.restype = ctypes.c_bool
            user32.UnregisterHotKey.argtypes = [ctypes.c_void_p, ctypes.c_int]
            user32.GetMessageW.argtypes = [ctypes.POINTER(MSG), ctypes.c_void_p, ctypes.c_uint, ctypes.c_uint]
            user32.GetMessageW.restype = ctypes.c_int
            for command_id, (_command, modifiers, virtual_key) in GLOBAL_COMMAND_HOTKEYS.items():
                if user32.RegisterHotKey(None, command_id, modifiers, virtual_key):
                    self.global_hotkey_registered_ids.add(command_id)
            self.global_hotkey_ready.set()
            while not self.global_hotkey_stop.is_set():
                result = user32.GetMessageW(ctypes.byref(message), None, 0, 0)
                if result <= 0:
                    break
                if message.message != WM_HOTKEY:
                    continue
                hotkey = GLOBAL_COMMAND_HOTKEYS.get(int(message.wParam))
                if hotkey is not None:
                    self.global_hotkey_events.put(hotkey[0])
        except Exception:
            self.global_hotkey_ready.set()
        finally:
            for command_id in tuple(self.global_hotkey_registered_ids):
                try:
                    user32.UnregisterHotKey(None, command_id)
                except Exception:
                    pass
            self.global_hotkey_registered_ids.clear()
            self.global_hotkey_thread_id = 0

    def _drain_global_commands(self) -> None:
        self.global_hotkey_after_id = None
        while True:
            try:
                command = self.global_hotkey_events.get_nowait()
            except queue.Empty:
                break
            self._run_command(command)
            if self._closing:
                return
        if not self._closing and self.global_hotkey_thread is not None:
            self.global_hotkey_after_id = self.root.after(25, self._drain_global_commands)

    def _stop_global_command_listener(self) -> None:
        if self.global_hotkey_after_id is not None:
            try:
                self.root.after_cancel(self.global_hotkey_after_id)
            except tk.TclError:
                pass
            self.global_hotkey_after_id = None
        self.global_hotkey_stop.set()
        thread_id = self.global_hotkey_thread_id
        if thread_id and os.name == "nt":
            try:
                user32 = ctypes.windll.user32
                user32.PostThreadMessageW(thread_id, WM_QUIT, 0, 0)
            except Exception:
                pass
        listener = self.global_hotkey_thread
        if listener is not None and listener is not threading.current_thread():
            listener.join(timeout=0.5)
        self.global_hotkey_thread = None

    def _run_command(self, command: str) -> None:
        if command == "exit":
            self.quit_app()
            return
        if command == "restore":
            self.restore_and_continue()
            return
        if command == "test":
            if self.stage in {"idle", "waiting"}:
                self._trigger_test_hotkey()
            elif self.stage == "reaction":
                self._input_violation()

    def _build_controller(self) -> None:
        self.root.title("RANSOM")
        self.root.geometry("540x570")
        self.root.minsize(520, 550)
        self.root.configure(bg="#090909")

        tk.Label(
            self.root,
            text="RANSOM",
            font=("Arial Black", 34),
            fg="#ff2525",
            bg="#090909",
        ).pack(pady=(22, 0))
        tk.Label(
            self.root,
            text="DOORS デスクトップ・エンカウンター",
            font=("Yu Gothic UI", 13, "bold"),
            fg="#e7e7e7",
            bg="#090909",
        ).pack(pady=(0, 16))

        safety = tk.Frame(self.root, bg="#22120d", highlightbackground="#ff9b38", highlightthickness=1)
        safety.pack(fill="x", padx=28, pady=(0, 16))
        tk.Label(
            safety,
            text="安全機能：- で復元 / * でアプリを完全終了",
            font=("Yu Gothic UI", 11, "bold"),
            fg="#ffd08c",
            bg="#22120d",
        ).pack(padx=14, pady=(10, 2))
        tk.Label(
            safety,
            text="ファイル変更・暗号化・入力ロック・自動起動は行いません。\n点滅と大きめの合成音を含みます。",
            font=("Yu Gothic UI", 9),
            justify="center",
            fg="#d8c7b2",
            bg="#22120d",
        ).pack(padx=14, pady=(0, 10))

        settings = tk.Frame(self.root, bg="#111111", highlightbackground="#333333", highlightthickness=1)
        settings.pack(fill="x", padx=28)
        tk.Label(
            settings,
            text="出現までのランダム待機時間（秒）",
            font=("Yu Gothic UI", 10, "bold"),
            fg="#dddddd",
            bg="#111111",
        ).grid(row=0, column=0, columnspan=4, sticky="w", padx=16, pady=(14, 7))
        tk.Label(settings, text="最短", fg="#aaaaaa", bg="#111111").grid(row=1, column=0, padx=(16, 6))
        tk.Entry(
            settings,
            width=8,
            textvariable=self.min_wait_var,
            justify="center",
            bg="#202020",
            fg="white",
            insertbackground="white",
            relief="flat",
        ).grid(row=1, column=1, padx=(0, 18), ipady=4)
        tk.Label(settings, text="最長", fg="#aaaaaa", bg="#111111").grid(row=1, column=2, padx=(0, 6))
        tk.Entry(
            settings,
            width=8,
            textvariable=self.max_wait_var,
            justify="center",
            bg="#202020",
            fg="white",
            insertbackground="white",
            relief="flat",
        ).grid(row=1, column=3, padx=(0, 16), ipady=4)

        tk.Checkbutton(
            settings,
            text="入力せず回避した場合は、次の出現を再予約する",
            variable=self.repeat_var,
            activebackground="#111111",
            activeforeground="white",
            selectcolor="#222222",
            fg="#cccccc",
            bg="#111111",
            highlightthickness=0,
        ).grid(row=2, column=0, columnspan=4, sticky="w", padx=12, pady=(14, 8))

        tk.Label(settings, text="音量", fg="#aaaaaa", bg="#111111").grid(
            row=3, column=0, sticky="w", padx=16, pady=(4, 14)
        )
        tk.Scale(
            settings,
            from_=0,
            to=100,
            orient="horizontal",
            variable=self.volume_var,
            command=self._on_volume,
            length=285,
            showvalue=True,
            bg="#111111",
            fg="#dddddd",
            troughcolor="#2a2a2a",
            activebackground="#ff3333",
            highlightthickness=0,
        ).grid(row=3, column=1, columnspan=3, sticky="w", pady=(4, 14))

        buttons = tk.Frame(self.root, bg="#090909")
        buttons.pack(fill="x", padx=28, pady=18)
        tk.Button(
            buttons,
            text="待機を開始",
            command=self.arm,
            bg="#b90c13",
            activebackground="#e51b24",
            fg="white",
            activeforeground="white",
            font=("Yu Gothic UI", 11, "bold"),
            relief="flat",
            cursor="hand2",
        ).pack(side="left", expand=True, fill="x", padx=(0, 6), ipady=8)
        tk.Button(
            buttons,
            text="3秒テスト",
            command=lambda: self.arm(test=True),
            bg="#353535",
            activebackground="#4a4a4a",
            fg="white",
            activeforeground="white",
            font=("Yu Gothic UI", 11, "bold"),
            relief="flat",
            cursor="hand2",
        ).pack(side="left", expand=True, fill="x", padx=6, ipady=8)
        tk.Button(
            buttons,
            text="停止",
            command=self.stop_session,
            bg="#222222",
            activebackground="#383838",
            fg="#dddddd",
            activeforeground="white",
            font=("Yu Gothic UI", 11),
            relief="flat",
            cursor="hand2",
        ).pack(side="left", expand=True, fill="x", padx=(6, 0), ipady=8)

        tk.Label(
            self.root,
            textvariable=self.status_var,
            font=("Consolas", 10, "bold"),
            fg="#76e08d",
            bg="#090909",
        ).pack(pady=(0, 7))
        tk.Label(
            self.root,
            text="入力してしまうと、16個までの実ウィンドウと\nクリック可能な実コインウィンドウが出現します。",
            font=("Yu Gothic UI", 9),
            justify="center",
            fg="#777777",
            bg="#090909",
        ).pack()

    def _on_volume(self, _value: str = "") -> None:
        self.audio.set_volume(self.volume_var.get() / 100.0)

    def arm(self, test: bool = False) -> None:
        self._refresh_saved_settings()
        try:
            minimum = float(self.min_wait_var.get())
            maximum = float(self.max_wait_var.get())
            if minimum < 1 or maximum < minimum:
                raise ValueError
        except ValueError:
            minimum = float(self.DEFAULT_MIN_WAIT_SECONDS)
            maximum = float(self.DEFAULT_MAX_WAIT_SECONDS)
            self.min_wait_var.set(str(self.DEFAULT_MIN_WAIT_SECONDS))
            self.max_wait_var.set(str(self.DEFAULT_MAX_WAIT_SECONDS))

        self._reset_event_windows()
        self._cancel_callbacks()
        self.audio.stop_all()
        self.app_held_inputs.clear()
        self.armed = True
        wait_s = 0.06 if test else self.rng.uniform(minimum, maximum)
        self.status_var.set(
            f"待機中：およそ {wait_s:.1f} 秒後（-で復元 / +で即時表示 / *で完全終了）"
        )
        if self.headless:
            self.root.withdraw()
        else:
            self.root.iconify()
        self._queue_intro(wait_s)

    def _trigger_test_hotkey(self) -> None:
        if self.stage not in {"idle", "waiting"}:
            return
        self._refresh_saved_settings()
        self._cancel_callbacks()
        self._reset_event_windows()
        self.audio.stop_all()
        self.armed = True
        self.stage = "waiting"
        self._show_intro()

    def start_ransom_preview(self) -> None:
        """Developer preview used by the packaged smoke test and visual QA."""
        self._cancel_callbacks()
        self._reset_event_windows()
        self.audio.stop_all()
        self.armed = True
        self.stage = "attack"
        if not self.headless:
            self.root.iconify()
        self._create_shell_overlays()
        self._start_ransom()

    def _schedule_next(self) -> None:
        if not self.armed:
            return
        if not self.repeat_var.get():
            self.stage = "idle"
            self.armed = False
            self.status_var.set("回避成功。待機を終了しました")
            if not self.headless:
                self.root.deiconify()
                self.root.lift()
            return
        try:
            minimum = max(1.0, float(self.min_wait_var.get()))
            maximum = max(minimum, float(self.max_wait_var.get()))
        except ValueError:
            minimum = float(self.DEFAULT_MIN_WAIT_SECONDS)
            maximum = float(self.DEFAULT_MAX_WAIT_SECONDS)
        wait_s = self.rng.uniform(minimum, maximum)
        self.status_var.set(f"回避成功。次回までおよそ {wait_s:.1f} 秒")
        self._queue_intro(wait_s)

    def _queue_intro(self, wait_seconds: float) -> None:
        """Schedule an encounter and retain a deadline for the backup poller."""
        delay_seconds = max(0.001, float(wait_seconds))
        self.wait_sequence += 1
        token = self.wait_sequence
        self.wait_deadline = time.monotonic() + delay_seconds
        self.stage = "waiting"
        self._later(
            max(1, math.ceil(delay_seconds * 1000.0)),
            lambda sequence=token: self._show_intro(sequence),
        )

    def _poll_waiting_deadline(self) -> None:
        """Recover a timed encounter if another callback was unexpectedly lost."""
        if self._closing:
            return
        try:
            self._refresh_saved_settings()
            if (
                self.armed
                and self.stage == "waiting"
                and self.wait_deadline > 0.0
                and time.monotonic() >= self.wait_deadline
            ):
                self._show_intro(self.wait_sequence)
        finally:
            if not self._closing:
                self.wait_watchdog_after_id = self.root.after(
                    self.WAIT_WATCHDOG_MS,
                    self._poll_waiting_deadline,
                )

    def _refresh_saved_settings(self) -> None:
        """Hot-reload validated settings without changing an active payment."""
        if not self.use_saved_settings:
            return
        stamp = settings_signature(self.settings_path)
        if stamp == self.settings_stamp:
            return
        self.settings_stamp = stamp
        try:
            updated = load_settings(self.settings_path)
        except (OSError, ValueError) as error:
            self.settings_error = str(error)
            return  # retain the last valid configuration
        self.settings_error = ""
        if updated == self.settings:
            return
        intervals_changed = (
            updated.min_spawn_seconds != self.settings.min_spawn_seconds
            or updated.max_spawn_seconds != self.settings.max_spawn_seconds
        )
        self.settings = updated
        self.STARTING_BALANCE = updated.required_coins
        self.REACTION_ARM_DELAY_MS = round(updated.stop_grace_seconds * 1000)
        self.min_wait_var.set(str(updated.min_spawn_seconds))
        self.max_wait_var.set(str(updated.max_spawn_seconds))
        if intervals_changed and self.armed and self.stage == "waiting":
            delay = self.rng.uniform(updated.min_spawn_seconds, updated.max_spawn_seconds)
            self._queue_intro(delay)
            self.status_var.set(f"設定を反映：次回までおよそ {delay:.1f} 秒")

    # ---------- warning sequence ----------

    def _show_intro(self, wait_sequence: int | None = None) -> None:
        if wait_sequence is not None and wait_sequence != self.wait_sequence:
            return
        if not self.armed or self.stage != "waiting":
            return
        self.wait_deadline = 0.0
        self.intro_sequence_id += 1
        sequence_id = self.intro_sequence_id
        self.intro_visible_since = 0.0
        self.intro_deadline = 0.0
        self.event_count += 1
        self.stage = "intro"
        self.screen_width = self.root.winfo_screenwidth()
        self.screen_height = self.root.winfo_screenheight()
        # Normal encounters may arrive several minutes after launch. Always
        # reacquire the Windows endpoint here so the timed path is as reliable
        # as the immediate plus-key test path.
        self.audio.reopen()
        self.audio.stop_channel("loop")
        size = min(250, max(180, self.screen_height // 4))

        window = tk.Toplevel(self.root)
        self.intro_window = window
        window.withdraw()
        window.overrideredirect(True)
        window.configure(bg=TRANSPARENT_KEY)
        window.attributes("-topmost", True)
        try:
            window.attributes("-transparentcolor", TRANSPARENT_KEY)
        except tk.TclError:
            pass
        # Build while hidden, measure the actual Tk window, and only then pick
        # a random coordinate. Reserving a small edge margin also covers DWM's
        # invisible resize/shadow area on scaled Windows desktops.
        window.geometry(f"{size}x{size}+0+0")
        photo = self._photo("ransom_face.png", (size, size))
        tk.Label(window, image=photo, bg=TRANSPARENT_KEY, borderwidth=0).pack(fill="both", expand=True)
        window.update_idletasks()
        measured_width = max(1, window.winfo_width(), window.winfo_reqwidth())
        measured_height = max(1, window.winfo_height(), window.winfo_reqheight())
        x, y = self._random_position_in_work_area(measured_width, measured_height, margin=12)
        window.geometry(f"{measured_width}x{measured_height}+{x}+{y}")
        # update_idletasks() alone does not guarantee that Windows has mapped
        # and painted a new top-level. Automatic encounters could therefore
        # reach STOP while the warning face had never appeared. Force the map,
        # verify it, and start the warning duration only after that point.
        try:
            window.deiconify()
            window.attributes("-topmost", True)
            window.lift()
            window.update()
            mapped = bool(window.winfo_ismapped())
            if mapped:
                self._clamp_window_to_work_area(window, margin=12)
                window.update_idletasks()
        except tk.TclError:
            mapped = False
        if not mapped:
            self._destroy_window(window)
            self.intro_window = None
            self.stage = "waiting"
            self._later(30, self._show_intro)
            return
        # Keep the warning sound isolated so jumpscare1 can overlap without
        # truncating its tail.
        self.audio.play("jumpscare2.mp3", channel="warning")
        # Keep the existing warning time, then add an unpredictable 0-0.3s.
        delay = self.rng.randint(self.INTRO_MIN_MS, self.INTRO_MAX_MS)
        delay += self.rng.randint(0, self.INTRO_EXTRA_MAX_MS)
        self.intro_visible_since = time.monotonic()
        self.intro_deadline = self.intro_visible_since + delay / 1000.0
        self._later(delay, lambda token=sequence_id: self._center_warning(token))

    def _primary_work_area(self) -> tuple[int, int, int, int]:
        """Return the usable primary-screen rectangle in Tk-compatible pixels."""
        left, top, right, bottom = 0, 0, self.screen_width, self.screen_height
        if os.name != "nt":
            return left, top, right, bottom
        try:
            class RECT(ctypes.Structure):
                _fields_ = [
                    ("left", ctypes.c_long),
                    ("top", ctypes.c_long),
                    ("right", ctypes.c_long),
                    ("bottom", ctypes.c_long),
                ]

            rect = RECT()
            spi = ctypes.windll.user32.SystemParametersInfoW
            if spi(0x0030, 0, ctypes.byref(rect), 0):  # SPI_GETWORKAREA
                if rect.right > rect.left and rect.bottom > rect.top:
                    left, top, right, bottom = rect.left, rect.top, rect.right, rect.bottom
        except Exception:
            pass
        return left, top, right, bottom

    def _random_position_in_work_area(
        self,
        width: int,
        height: int,
        margin: int = 0,
    ) -> tuple[int, int]:
        left, top, right, bottom = self._primary_work_area()
        minimum_x = left + margin
        minimum_y = top + margin
        maximum_x = max(minimum_x, right - margin - width)
        maximum_y = max(minimum_y, bottom - margin - height)
        return self.rng.randint(minimum_x, maximum_x), self.rng.randint(minimum_y, maximum_y)

    def _clamp_window_to_work_area(self, window: tk.Toplevel, margin: int = 0) -> None:
        """Correct a mapped window using its final, measured dimensions."""
        if not self._window_exists(window):
            return
        window.update_idletasks()
        width = max(1, window.winfo_width())
        height = max(1, window.winfo_height())
        border = max(0, window.winfo_rootx() - window.winfo_x())
        chrome_height = max(0, window.winfo_rooty() - window.winfo_y()) + border
        left, top, right, bottom = self._primary_work_area()
        minimum_x = left + margin
        minimum_y = top + margin
        maximum_x = max(minimum_x, right - margin - width - border * 2)
        maximum_y = max(minimum_y, bottom - margin - height - chrome_height)
        x = min(max(window.winfo_x(), minimum_x), maximum_x)
        y = min(max(window.winfo_y(), minimum_y), maximum_y)
        window.geometry(f"{width}x{height}+{x}+{y}")

    def _center_warning(self, sequence_id: int | None = None) -> None:
        if self.stage != "intro":
            return
        if sequence_id is not None and sequence_id != self.intro_sequence_id:
            return
        if not self._window_exists(self.intro_window):
            # Never skip directly to STOP when the warning could not be shown.
            self.intro_window = None
            self.stage = "waiting"
            self._later(30, self._show_intro)
            return
        try:
            mapped = bool(self.intro_window.winfo_ismapped())
        except tk.TclError:
            mapped = False
        if not mapped:
            self._destroy_window(self.intro_window)
            self.intro_window = None
            self.stage = "waiting"
            self._later(30, self._show_intro)
            return
        remaining_ms = math.ceil((self.intro_deadline - time.monotonic()) * 1000.0)
        if remaining_ms > 0:
            self._later(
                remaining_ms,
                lambda token=self.intro_sequence_id: self._center_warning(token),
            )
            return
        self._destroy_window(self.intro_window)
        self.intro_window = None
        self.intro_visible_since = 0.0
        self.intro_deadline = 0.0
        self.stage = "centering"
        self._create_overlay()
        if self.overlay_canvas is None or self.overlay is None:
            return
        face_size = min(320, max(220, self.screen_height // 3))
        face = self._photo("ransom_face.png", (face_size, face_size))
        self.overlay_canvas.create_image(
            self.screen_width // 2,
            self.screen_height // 2,
            image=face,
            tags=("entity",),
        )
        self.overlay.focus_force()
        self._later(35, self._show_stop)

    def _show_stop(self) -> None:
        if self.stage != "centering" or self.overlay_canvas is None:
            return
        # Face appearance/centering is always safe to move through. STOP becomes
        # visible now; actual movement checking starts after the reaction allowance.
        self.stage = "reaction_grace"
        self.overlay_canvas.configure(bg="#100000")
        self.overlay_canvas.delete("stop_background")
        stop_background = self._stop_background_photo()
        self.overlay_canvas.create_image(
            self.screen_width // 2,
            self.screen_height // 2,
            image=stop_background,
            tags=("stop_background",),
        )
        self.overlay_canvas.tag_lower("stop_background")
        self.overlay_canvas.itemconfigure("entity", state="hidden")
        stop_size = min(420, max(300, int(self.screen_height * 0.38)))
        stop_photo = self._photo("stop_reference.png", (stop_size, stop_size))
        self.overlay_canvas.create_image(
            self.screen_width // 2,
            self.screen_height // 2,
            image=stop_photo,
            tags=("stop",),
        )
        # Snapshot only events that this application's focused windows have
        # received.  This preserves STOP's pre-held-key behavior inside the
        # simulator without inspecting keyboard or mouse state globally.
        self.preheld_input_at_stop = bool(self.app_held_inputs)
        self._later(self.REACTION_ARM_DELAY_MS, self._arm_reaction)

    def _arm_reaction(self) -> None:
        if self.stage != "reaction_grace":
            return
        self.stage = "reaction"
        self.reaction_failed = (
            self.force_stop_failure
            or self.preheld_input_at_stop
        )
        self.reaction_started = time.monotonic()
        self.pointer_origin = self.root.winfo_pointerxy()
        self.pointer_outside_samples = 0
        self._poll_pointer()
        self._later(self.REACTION_MS, self._safe_avoid)

    def _poll_pointer(self) -> None:
        if self.stage != "reaction":
            return
        current = self.root.winfo_pointerxy()
        dx = current[0] - self.pointer_origin[0]
        dy = current[1] - self.pointer_origin[1]
        if (dx * dx + dy * dy) >= self.POINTER_DEADZONE_PX**2:
            self.pointer_outside_samples += 1
            if self.pointer_outside_samples >= self.POINTER_CONFIRM_SAMPLES:
                self._input_violation()
                return
        else:
            self.pointer_outside_samples = 0
        self._later(16, self._poll_pointer)

    def _on_key_press(self, event: tk.Event) -> None:
        keysym = getattr(event, "keysym", "")
        character = getattr(event, "char", "")
        self.app_held_inputs.add(("key", keysym))
        if keysym in {"asterisk", "KP_Multiply"} or character == "*":
            self._run_command("exit")
            return
        if keysym in {"minus", "KP_Subtract"} or character == "-":
            self._run_command("restore")
            return
        plus_pressed = keysym in {"plus", "KP_Add"} or character == "+"
        if plus_pressed:
            self._run_command("test")
            return
        if self.stage != "reaction":
            return
        self._input_violation()

    def _on_key_release(self, event: tk.Event) -> None:
        self.app_held_inputs.discard(("key", getattr(event, "keysym", "")))

    def _on_pointer_press(self, event: tk.Event) -> None:
        self.app_held_inputs.add(("button", str(getattr(event, "num", 0))))
        if self.stage != "reaction":
            return
        self._input_violation()

    def _on_pointer_release(self, event: tk.Event) -> None:
        self.app_held_inputs.discard(("button", str(getattr(event, "num", 0))))

    def _safe_avoid(self) -> None:
        if self.stage != "reaction" or self.overlay_canvas is None:
            return
        if self.reaction_failed:
            self.stage = "attack"
            self.audio.stop_channel("loop")
            # Paint the first jumpscare frame before starting its sound. The
            # heavier reversible shell effects are deferred so audio cannot run
            # ahead while the STOP picture is still visible.
            self._animate_attack(0)
            self.overlay_canvas.update_idletasks()
            # Play every sample from the supplied MP3 without trimming. Its
            # first strong transient is about 52ms into the file; a short
            # channel gain ramp removes the recorded "pop" while preserving
            # the complete 2.612s source. The 2.400s visual sequence now hands
            # off sooner, but this dedicated channel keeps playing the tail.
            self.audio.play("jumpscare1.mp3", channel="attack", fade_ms=120)
            self._later(1, self._create_secondary_monitor_overlays)
            self._later(1, self._create_shell_overlays)
            return
        self.stage = "avoided"
        self.audio.stop_channel("loop")
        self.overlay_canvas.delete("stop")
        self.overlay_canvas.delete("noise")
        self.overlay_canvas.delete("stop_background")
        self.overlay_canvas.configure(bg="black")
        self.overlay_canvas.itemconfigure("entity", state="normal")
        self._later(100, self._finish_avoid)

    def _finish_avoid(self) -> None:
        if self.stage != "avoided":
            return
        self._destroy_overlay()
        self.preheld_input_at_stop = False
        self.app_held_inputs.clear()
        if self.bridge_result_path is not None:
            self._write_bridge_result("avoided")
            self.root.after(25, self.quit_app)
            return
        self._schedule_next()

    def _input_violation(self) -> None:
        if self.stage != "reaction":
            return
        # Do not interrupt STOP. Remember the movement and transition only when
        # the fixed STOP phase reaches its end.
        self.reaction_failed = True

    def _animate_attack(self, frame: int) -> None:
        if self.stage != "attack" or self.overlay_canvas is None:
            return
        now = time.monotonic()
        if frame == 0:
            self.attack_deadline = now + self.ATTACK_DURATION_MS / 1000.0
        elif now >= self.attack_deadline:
            self._show_downloading()
            return
        size = int(min(self.screen_width, self.screen_height) * 0.66)
        # Reuse one pre-scaled photo. Resizing the 120px source on every frame
        # can stall Tk long enough to make the first frame look frozen.
        photo = self._photo("attack_face.png", (size, size))
        self.overlay_canvas.delete("all")
        self.overlay_canvas.configure(bg="#4b0000")
        shake_x = self.rng.randint(-7, 7)
        shake_y = self.rng.randint(-6, 6)
        self.overlay_canvas.create_image(
            self.screen_width // 2 + shake_x,
            self.screen_height // 2 + shake_y,
            image=photo,
        )
        remaining_ms = max(1, math.ceil((self.attack_deadline - time.monotonic()) * 1000.0))
        self._later(min(self.ATTACK_FRAME_MS, remaining_ms), lambda: self._animate_attack(frame + 1))

    def _show_downloading(self) -> None:
        if self.stage != "attack" or self.overlay_canvas is None:
            return
        self.stage = "downloading"
        self._animate_downloading(0)

    def _downloading_background_photo(self, width: int, height: int) -> ImageTk.PhotoImage:
        key = f"downloading-background-transparent:{width}x{height}"
        photo = self.photos.get(key)
        if photo is None:
            # Cover the complete overlay with one translucent grain texture.
            # The former small opaque panel made the area around the bar a
            # visibly different red from the rest of the screen.
            sample_width = max(320, min(720, width // 3))
            sample_height = max(180, round(sample_width * height / max(1, width)))
            noise = Image.effect_noise((sample_width, sample_height), 38.0).convert("L")
            noise = noise.resize((width, height), Image.Resampling.NEAREST)
            background = ImageOps.colorize(noise, black="#4f0000", white="#ef2525").convert("RGBA")
            background.putalpha(148)
            photo = ImageTk.PhotoImage(background)
            self.photos[key] = photo
        return photo

    def _animate_downloading(self, frame: int) -> None:
        if self.stage != "downloading" or self.overlay_canvas is None:
            return
        total_frames = self.DOWNLOADING_FRAMES
        progress = min(1.0, frame / max(1, total_frames - 1))
        canvas = self.overlay_canvas
        canvas.delete("all")
        canvas.configure(bg="#790000")
        background = self._downloading_background_photo(self.screen_width, self.screen_height)
        canvas.create_image(0, 0, image=background, anchor="nw", tags=("download_background",))

        # The text and segmented bar float directly over the same full-screen
        # texture, with no opaque panel boundary around them.
        width = min(1120, self.screen_width - 64)
        height = max(190, round(width * 124 / 525))
        left = (self.screen_width - width) // 2
        top = (self.screen_height - height) // 2

        # The ellipsis animates independently: ., .., ... and repeat.
        dot_count = 1 + (frame // 3) % 3
        text_x = self.screen_width // 2 + self.rng.randint(-2, 2)
        text_y = top + round(height * 0.31) + self.rng.randint(-2, 2)
        canvas.create_text(
            text_x,
            text_y,
            text="DOWNLOADING" + "." * dot_count,
            fill="#ffffff",
            font=("Consolas", max(30, round(width * 0.052)), "bold"),
            tags=("download_text",),
        )

        # Recreate the reference bar: a red outer frame, solid black interior,
        # and discrete red blocks that fill strictly one at a time. The whole
        # bar jitters by a few pixels independently from the heading.
        bar_dx = self.rng.randint(-3, 3)
        bar_dy = self.rng.randint(-2, 2)
        bar_left = left + round(width * 0.035) + bar_dx
        bar_right = left + round(width * 0.985) + bar_dx
        bar_top = top + round(height * 0.49) + bar_dy
        bar_height = max(42, round(height * 0.27))
        canvas.create_rectangle(
            bar_left,
            bar_top,
            bar_right,
            bar_top + bar_height,
            fill="#050000",
            outline="#ff1425",
            width=4,
            tags=("download_bar",),
        )
        inner_left = bar_left + 6
        inner_right = bar_right - 6
        inner_top = bar_top + 6
        inner_bottom = bar_top + bar_height - 6
        segment_count = self.DOWNLOADING_SEGMENTS
        gap = max(2, round(width * 0.004))
        available_width = inner_right - inner_left
        segment_width = (available_width - gap * (segment_count - 1)) / segment_count
        filled_segments = min(segment_count, int(progress * segment_count + 0.999999))
        for segment in range(filled_segments):
            segment_left = round(inner_left + segment * (segment_width + gap))
            segment_right = round(segment_left + segment_width)
            canvas.create_rectangle(
                segment_left,
                inner_top,
                segment_right,
                inner_bottom,
                fill="#e61b27",
                outline="#8d000d",
                width=1,
                tags=("download_bar_segment",),
            )
        if frame + 1 < total_frames:
            self._later(self.DOWNLOADING_FRAME_MS, lambda: self._animate_downloading(frame + 1))
        else:
            next_stage = (
                self._finish_bridge_downloading
                if self.exit_after_downloading
                else self._start_ransom
            )
            self._later(self.DOWNLOADING_END_DELAY_MS, next_stage)

    def _finish_bridge_downloading(self) -> None:
        """Return an infected result without opening the standalone coin game."""
        if self.stage != "downloading":
            return
        self.stage = "bridge_complete"
        self._destroy_overlay()
        self._destroy_ransom_windows()
        self._destroy_shell_overlays()
        self._write_bridge_result("infected")
        # jumpscare1 is intentionally longer than the 0.8s attack plus 1.5s
        # download animation. Keep this process alive briefly so its untrimmed
        # tail is audible before the launcher restores and shakes DELTARUNE.
        self.root.after(350, self.quit_app)

    # ---------- ransom windows ----------

    def _fit_note_to_screen(self) -> None:
        """Fit the 315:185 note to the current work area, including its frame."""
        left, top, right, bottom = self._primary_work_area()
        self.note_scale = max(0.1, min(1.0, (right - left - 32) / 945, (bottom - top - 64) / 555))
        self.NOTE_WIDTH = max(1, round(945 * self.note_scale))
        self.NOTE_HEIGHT = max(1, round(555 * self.note_scale))

    def _start_ransom(self) -> None:
        if self.stage not in {"attack", "downloading"}:
            return
        if self.STARTING_BALANCE <= self.COIN_VALUE:
            self._finish_without_payment()
            return
        self._destroy_overlay()
        self.stage = "ransom"
        self.screen_width = self.root.winfo_screenwidth()
        self.screen_height = self.root.winfo_screenheight()
        self._fit_note_to_screen()
        # Open the red desktop layers only after the fullscreen attack and
        # download finish, so they cannot cover either animation.
        if self.enable_shell_effects and self.system_effects_active:
            self._create_visual_shell_overlays()
        self.balance = self.STARTING_BALANCE
        self.ransom_deadline = time.monotonic() + self.RANSOM_SECONDS
        coin_count = self.STARTING_BALANCE // self.COIN_VALUE
        self.status_var.set(
            f"RANSOM進行中：コインを{coin_count}枚ドラッグ／投げて支払う（-で復元）"
        )
        self.audio.play_music(MUSIC_NAME, start=MUSIC_START_SECONDS)
        self.glitch_window_target = self.rng.choice((4, 5))
        for index in range(self.glitch_window_target):
            self._create_glitch_window(index)
        self._create_note_window()
        self._create_ransom_border_frame()
        self._later(self.rng.randint(4000, 6000), self._move_note_window)
        self._animate_glitch_windows()
        self._spawn_coin()
        self._later(self.rng.randint(1800, 4200), self._flash_random_face)
        self._later(self.rng.randint(2600, 5200), self._flash_desktop_face)
        self._update_ransom_clock()
        self.root.update_idletasks()
        self._maintain_ransom_visibility()

    def _finish_without_payment(self) -> None:
        """End this encounter after downloading, with no coin game or result UI."""
        self.stage = "completed"
        self._cancel_callbacks()
        self._reset_event_windows()
        self.preheld_input_at_stop = False
        self.reaction_failed = False
        self.app_held_inputs.clear()
        # Leave the attack channel alone so the original downloading sound
        # can finish its tail. Do not play music or a victory sound here.
        self._schedule_next()

    def _flash_random_face(self) -> None:
        if self.stage != "ransom":
            return
        size = self.rng.randint(58, 108)
        x = self.rng.randint(0, max(0, self.screen_width - size))
        y = self.rng.randint(0, max(0, self.screen_height - size))
        self._create_face_flash("screen", x, y, size)
        self._later(self.rng.randint(2300, 5700), self._flash_random_face)

    def _flash_desktop_face(self) -> None:
        if self.stage != "ransom":
            return
        size = self.rng.randint(48, 72)
        rows = max(1, (self.screen_height - 58) // 82)
        max_columns = max(1, min(4, self.screen_width // 92))
        column = self.rng.randrange(max_columns)
        row = self.rng.randrange(rows)
        x = max(0, min(self.screen_width - size, 45 + column * 92 - size // 2))
        y = max(0, min(self.screen_height - size, 45 + row * 82 - size // 2))
        self._create_face_flash("desktop", x, y, size)
        self._later(self.rng.randint(3500, 7600), self._flash_desktop_face)

    def _create_face_flash(self, kind: str, x: int, y: int, size: int) -> None:
        if self.stage != "ransom":
            return
        window = tk.Toplevel(self.root)
        window.overrideredirect(True)
        window.configure(bg=TRANSPARENT_KEY)
        window.attributes("-topmost", True)
        try:
            window.attributes("-transparentcolor", TRANSPARENT_KEY)
        except tk.TclError:
            pass
        window.geometry(f"{size}x{size}+{x}+{y}")
        photo = self._photo("flash_face.png", (size, size))
        tk.Label(window, image=photo, bg=TRANSPARENT_KEY, borderwidth=0).pack(fill="both", expand=True)
        record: dict[str, Any] = {
            "window": window,
            "kind": kind,
            "x": x,
            "y": y,
            "size": size,
        }
        self.face_flash_windows.append(record)
        if not self._make_clickthrough(window):
            self._expire_face_flash(record)
            return
        window.lift()
        self._later(self.rng.randint(75, 135), lambda: self._expire_face_flash(record))

    def _expire_face_flash(self, record: dict[str, Any]) -> None:
        if record in self.face_flash_windows:
            self.face_flash_windows.remove(record)
        self._destroy_window(record.get("window"))

    def _create_ransom_border_frame(self) -> None:
        if self.ransom_frame_window is not None or os.name != "nt":
            return
        self._prepare_ransom_border_textures()
        if not self.ransom_frame_photos:
            return
        window = tk.Toplevel(self.root)
        self.ransom_frame_window = window
        window.overrideredirect(True)
        window.configure(bg=TRANSPARENT_KEY)
        window.attributes("-topmost", True)
        try:
            window.attributes("-transparentcolor", TRANSPARENT_KEY)
        except tk.TclError:
            pass
        window.geometry(f"{self.screen_width}x{self.screen_height}+0+0")
        canvas = tk.Canvas(
            window,
            width=self.screen_width,
            height=self.screen_height,
            bg=TRANSPARENT_KEY,
            highlightthickness=0,
        )
        self.ransom_frame_canvas = canvas
        canvas.pack(fill="both", expand=True)
        if not self._make_clickthrough(window):
            self._destroy_ransom_border_frame()
            return
        thickness = self.ransom_frame_thickness
        first = self.ransom_frame_photos[0]
        self.ransom_frame_items = [
            canvas.create_image(0, 0, image=first[0], anchor="nw"),
            canvas.create_image(self.screen_width - thickness, 0, image=first[1], anchor="nw"),
            canvas.create_image(0, self.screen_height - thickness, image=first[2], anchor="nw"),
            canvas.create_image(
                self.screen_width - thickness,
                self.screen_height - thickness,
                image=first[3],
                anchor="nw",
            ),
        ]
        self.ransom_frame_tick = 0
        self._animate_ransom_border_frame()

    def _prepare_ransom_border_textures(self) -> None:
        """Build four different red-dot cels limited to the four corners."""
        if self.ransom_frame_photos or os.name != "nt" or self._closing:
            return
        # Keep the effect corner-focused, but let each L-shaped texture travel
        # a little farther along the adjoining top/bottom and left/right edges.
        thickness = max(170, min(300, min(self.screen_width, self.screen_height) // 5))
        frames: list[
            tuple[ImageTk.PhotoImage, ImageTk.PhotoImage, ImageTk.PhotoImage, ImageTk.PhotoImage]
        ] = []
        for frame in range(4):
            frames.append(
                (
                    ImageTk.PhotoImage(self._render_dot_corner(thickness, "top_left", frame, 11)),
                    ImageTk.PhotoImage(self._render_dot_corner(thickness, "top_right", frame, 23)),
                    ImageTk.PhotoImage(self._render_dot_corner(thickness, "bottom_left", frame, 37)),
                    ImageTk.PhotoImage(self._render_dot_corner(thickness, "bottom_right", frame, 53)),
                )
            )
        self.ransom_frame_thickness = thickness
        self.ransom_frame_photos = frames

    @staticmethod
    def _render_dot_corner(size: int, corner: str, frame: int, salt: int) -> Image.Image:
        """Render one dense pixel-art corner using only equal 4x4 dots."""
        image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
        draw = ImageDraw.Draw(image)
        dot_size = RansomSimulator.FRAME_DOT_SIZE
        # Adjacent occupied cells now touch exactly; there is no fixed clear
        # gutter between dots. Random missing cells still form the animated
        # pixel texture seen in the reference.
        spacing = RansomSimulator.FRAME_DOT_SPACING
        colors = ("#ff061d", "#e00018", "#c00016", "#920011", "#ff3040")

        def noise(x: int, y: int, seed: int) -> int:
            value = (x * 73_856_093) ^ (y * 19_349_663) ^ (seed * 83_492_791)
            value = (value ^ (value >> 13)) * 1_274_126_177
            return value & 0xFFFFFFFF

        for grid_y in range(0, max(1, size - dot_size + 1), spacing):
            for grid_x in range(0, max(1, size - dot_size + 1), spacing):
                distance_x = grid_x if "left" in corner else size - dot_size - grid_x
                distance_y = grid_y if "top" in corner else size - dot_size - grid_y
                # A narrow edge-depth falloff plus a gentler along-edge falloff
                # makes an L-shaped corner cloud. It remains confined to the
                # corner region but extends farther along both adjoining edges.
                edge_depth = min(distance_x, distance_y)
                along_edge = max(distance_x, distance_y)
                depth_ratio = min(1.0, edge_depth / max(1.0, size * 0.46))
                along_ratio = min(1.0, along_edge / max(1, size - dot_size))
                probability = (
                    0.94
                    * ((1.0 - depth_ratio) ** 1.65)
                    * ((1.0 - along_ratio) ** 0.92)
                    + 0.012
                )
                cell_x, cell_y = grid_x // spacing, grid_y // spacing
                base_value = noise(cell_x, cell_y, salt)
                variant_value = noise(cell_x, cell_y, salt + 101 * (frame + 1))
                selector = noise(cell_x, cell_y, salt + 10_003)
                # About 58% of the grid follows a stable base texture and 42%
                # follows a different per-cel texture.  Density stays constant,
                # but the actual occupied pixels change on every animation cel.
                value = base_value if (selector & 0xFFFF) < 38_010 else variant_value
                if (value & 0xFFFF) / 65535.0 >= probability:
                    continue
                color = colors[(value >> 24) % len(colors)]
                draw.rectangle(
                    (grid_x, grid_y, grid_x + dot_size - 1, grid_y + dot_size - 1),
                    fill=color,
                )
        return image

    def _animate_ransom_border_frame(self) -> None:
        window = self.ransom_frame_window
        canvas = self.ransom_frame_canvas
        if self.stage != "ransom" or not self._window_exists(window) or canvas is None:
            self._destroy_ransom_border_frame()
            return
        thickness = self.ransom_frame_thickness
        frame = self.ransom_frame_photos[self.ransom_frame_tick % len(self.ransom_frame_photos)]
        try:
            for item, photo in zip(self.ransom_frame_items, frame):
                canvas.itemconfigure(item, image=photo)
            canvas.coords(self.ransom_frame_items[0], 0, 0)
            canvas.coords(self.ransom_frame_items[1], self.screen_width - thickness, 0)
            canvas.coords(self.ransom_frame_items[2], 0, self.screen_height - thickness)
            canvas.coords(
                self.ransom_frame_items[3],
                self.screen_width - thickness,
                self.screen_height - thickness,
            )
            window.attributes("-alpha", self.FRAME_OPACITY)
        except tk.TclError:
            return
        self.ransom_frame_tick += 1
        if self.ransom_frame_tick % 8 == 0:
            try:
                window.attributes("-topmost", True)
                window.lift()
            except tk.TclError:
                pass
        self._later(67, self._animate_ransom_border_frame)

    def _destroy_ransom_border_frame(self) -> None:
        self._destroy_window(self.ransom_frame_window)
        self.ransom_frame_window = None
        self.ransom_frame_canvas = None
        self.ransom_frame_items.clear()
        self.ransom_frame_tick = 0

    def _create_glitch_window(self, index: int) -> None:
        if self.stage != "ransom":
            return
        image_name = f"glitch_{self.rng.randint(1, 6)}.png"
        width = self.rng.randint(240, 420)
        height = self.rng.randint(round(width * 0.56), round(width * 0.70))
        x = self.rng.randint(0, max(0, self.screen_width - width - 20))
        y = self.rng.randint(20, max(20, self.screen_height - height - 60))
        window = tk.Toplevel(self.root)
        window.title(self.rng.choice(("I FOUND YOU", "IMG.JPG", "RANSOM", "STOP MOVING", "CORRUPTED", "ERROR")))
        window.configure(bg="black", cursor=self.minigame_cursor)
        window.attributes("-topmost", True)
        window.resizable(False, False)
        window.geometry(f"{width}x{height}+{x}+{y}")
        self._make_non_minimizable(window)
        photo = self._new_photo(image_name, (width, height))
        label = tk.Label(window, image=photo, bg="black", borderwidth=0, cursor=self.minigame_cursor)
        label.pack(fill="both", expand=True)
        record: dict[str, Any] = {
            "window": window,
            "label": label,
            "photo": photo,
            "image": image_name,
            "width": width,
            "height": height,
            "x": x,
            "y": y,
            "base_x": x,
            "base_y": y,
            "visible": True,
            "alpha": 1.0,
            "fade_direction": 0.0,
            "next_toggle": time.monotonic() + self.rng.uniform(4.5, 5.5),
        }
        self.glitch_windows.append(record)
        window.protocol("WM_DELETE_WINDOW", lambda item=record: self._close_glitch(item))

    def _close_glitch(self, record: dict[str, Any]) -> None:
        self._destroy_window(record.get("window"))
        if record in self.glitch_windows:
            self.glitch_windows.remove(record)

    def _animate_glitch_windows(self) -> None:
        if self.stage != "ransom":
            return
        now = time.monotonic()
        for record in list(self.glitch_windows):
            window = record["window"]
            if not self._window_exists(window):
                self.glitch_windows.remove(record)
                continue
            if now >= record["next_toggle"] and record["fade_direction"] == 0.0:
                record["fade_direction"] = -self.GLITCH_FADE_STEP
            if record["fade_direction"] < 0.0:
                record["alpha"] = max(0.0, min(1.0, record["alpha"] + record["fade_direction"]))
                try:
                    window.attributes("-alpha", record["alpha"])
                except tk.TclError:
                    pass
                if record["alpha"] <= 0.0:
                    # The old popup never changes its assigned image. Once it
                    # has fully faded, destroy it and immediately create a new
                    # independently sized/positioned popup.
                    self._close_glitch(record)
                    self._create_glitch_window(self.rng.randint(100, 9999))
                    continue
            record["x"] = max(
                0,
                min(self.screen_width - record["width"] - 10, record["base_x"] + self.rng.randint(-4, 4)),
            )
            record["y"] = max(
                20,
                min(self.screen_height - record["height"] - 45, record["base_y"] + self.rng.randint(-3, 3)),
            )
            window.geometry(f"+{record['x']}+{record['y']}")

        while len(self.glitch_windows) < self.glitch_window_target and self.stage == "ransom":
            self._create_glitch_window(len(self.glitch_windows) + self.rng.randint(20, 80))
        self._later(16, self._animate_glitch_windows)

    def _create_note_window(self) -> None:
        width, height = self.NOTE_WIDTH, self.NOTE_HEIGHT
        scale = self.note_scale * 3.0
        p = lambda value: round(value * scale)
        left, top, right, _bottom = self._primary_work_area()
        x, y = max(left + 12, right - width - 24), top + 12
        window = tk.Toplevel(self.root)
        self.note_window = window
        self.note_base_x, self.note_base_y = x, y
        self.note_jitter_tick = 0
        window.title("RANSOM")
        window.configure(cursor=self.minigame_cursor)
        window.attributes("-topmost", True)
        window.resizable(False, False)
        window.geometry(f"{width}x{height}+{x}+{y}")
        window.protocol("WM_DELETE_WINDOW", lambda: None)
        self._make_non_minimizable(window)
        canvas = tk.Canvas(window, width=width, height=height, bg="#ff0000", highlightthickness=0, cursor=self.minigame_cursor)
        self.note_canvas = canvas
        canvas.pack(fill="both", expand=True)

        # Reference proportions, live text, and pixel-sized fonts keep the
        # layout identical across Windows display scaling settings.
        bold = RANSOM_FONT_BOLD if self.private_font_loaded else "Consolas"
        medium = RANSOM_FONT_MEDIUM if self.private_font_loaded else "Consolas"
        font = lambda family, size: (family, -max(1, p(size)))
        canvas.create_rectangle(p(0.5), p(0.5), width - p(0.5), height - p(0.5),
                                fill="#ff0000", outline="#dddddd", width=max(1, p(0.5)))
        face = self._photo("ransom_face.png", (p(99), p(96)))
        canvas.create_image(p(70), p(51), image=face)
        canvas.create_text(p(141), p(10), text="YOUR FILES\nHAVE BEEN\nENCRYPTED",
                           anchor="nw", justify="center", fill="white", font=font(bold, 22))
        canvas.create_rectangle(p(7), p(99), p(308), p(144), fill="#000000",
                                outline="#eeeeee", width=max(1, p(1)))
        canvas.create_text(p(157.5), p(121.5),
                           text="IF YOU DO NOT PAY THIS RANSOM BY THE END\n"
                                "OF THE TIMER, YOUR FILES WILL BE\n"
                                "UNRECOVERABLE BY ANY MEANS.",
                           justify="center", fill="white", font=font(medium, 10))
        canvas.create_rectangle(p(7), p(146), p(116), p(181), fill="#000000",
                                outline="#dddddd", width=max(1, p(1)))
        canvas.create_rectangle(p(118), p(146), p(308), p(181), fill="#ff0000",
                                outline="#b80000", width=max(1, p(1)))
        self.balance_item = canvas.create_text(p(12), p(163.5), text=str(self.balance),
                                               anchor="w", fill="#ffe51c", font=font(bold, 25))
        coin = self._photo("coin_token.png", (p(32), p(32)))
        canvas.create_image(p(97), p(163.5), image=coin)
        canvas.create_text(p(128), p(163.5), text="TIME:", anchor="w",
                           fill="#000000", font=font(bold, 24))
        self.time_item = canvas.create_text(p(299), p(163.5), text=format_clock(self.RANSOM_SECONDS),
                                            anchor="e", fill="#000000", font=font(bold, 24))
        window.update_idletasks()
        self._clamp_window_to_work_area(window, margin=12)
        self.note_base_x, self.note_base_y = window.winfo_x(), window.winfo_y()
        window.lift()
        self._animate_note_jitter()

    def _animate_note_jitter(self) -> None:
        if self.stage != "ransom" or not self._window_exists(self.note_window):
            return
        offsets = ((0, 0), (1, -1), (-1, 1), (2, 0), (-2, -1), (0, 1))
        dx, dy = offsets[self.note_jitter_tick % len(offsets)]
        self.note_jitter_tick += 1
        left, top, right, bottom = self._primary_work_area()
        max_x = max(left + 8, right - self.NOTE_WIDTH - 16)
        max_y = max(top + 8, bottom - self.NOTE_HEIGHT - 48)
        x = max(left + 8, min(max_x, self.note_base_x + dx))
        y = max(top + 8, min(max_y, self.note_base_y + dy))
        try:
            self.note_window.geometry(f"{self.NOTE_WIDTH}x{self.NOTE_HEIGHT}+{x}+{y}")
        except tk.TclError:
            return
        self._later(16, self._animate_note_jitter)

    def _move_note_window(self) -> None:
        if self.stage != "ransom" or not self._window_exists(self.note_window):
            return
        width, height = self.NOTE_WIDTH, self.NOTE_HEIGHT
        current_x, current_y = self.note_base_x, self.note_base_y
        left, top, right, bottom = self._primary_work_area()
        min_x, min_y = left + 8, top + 8
        max_x = max(min_x, right - width - 16)
        max_y = max(min_y, bottom - height - 48)
        x, y = current_x, current_y
        for _ in range(8):
            x = self.rng.randint(min_x, max_x)
            y = self.rng.randint(min_y, max_y)
            if abs(x - current_x) + abs(y - current_y) >= 100:
                break
        if x == current_x and y == current_y:
            x = min_x if current_x > (min_x + max_x) // 2 else max_x
            y = min_y if current_y > (min_y + max_y) // 2 else max_y
        self.note_base_x = x
        self.note_base_y = y
        self.note_window.geometry(f"{width}x{height}+{x}+{y}")
        # Apply the move before raising the topmost window. On Windows, an
        # immediate lift can otherwise restore the window manager's old bounds.
        self.note_window.update_idletasks()
        self.note_window.lift()
        self._later(self.rng.randint(4000, 6000), self._move_note_window)

    def _spawn_coin(self) -> None:
        if self.stage != "ransom":
            return
        if len(self.coin_windows) < self.MAX_COIN_WINDOWS:
            coin_id = self.next_coin_id
            self.next_coin_id += 1
            size = self.rng.randint(58, 72)
            x, y = self._coin_position(size)
            key_color = "#010203"
            window = tk.Toplevel(self.root)
            window.withdraw()
            window.overrideredirect(True)
            window.configure(bg=key_color)
            window.attributes("-topmost", True)
            try:
                window.attributes("-transparentcolor", key_color)
            except tk.TclError:
                pass
            window.geometry(f"{size}x{size}+{x}+{y}")
            canvas = tk.Canvas(
                window,
                width=size,
                height=size,
                bg=key_color,
                highlightthickness=0,
                cursor=self.minigame_cursor,
            )
            canvas.pack(fill="both", expand=True)
            coin_photo = self._photo("coin_token.png", (size, size))
            canvas.create_image(size // 2, size // 2, image=coin_photo)
            # A clicked coin must not become the active top-level window.
            # Otherwise destroying it on payment can activate/raise the red
            # backdrop while Windows selects a replacement active window.
            if os.name == "nt":
                self._configure_visual_layer(window, pointer_passthrough=False)
            window.deiconify()
            window.update_idletasks()
            self.coin_windows[coin_id] = {
                "window": window,
                "canvas": canvas,
                "photo": coin_photo,
                "x": float(x),
                "y": float(y),
                "size": size,
                "dragging": False,
                "user_armed": False,
                "moving": False,
                "drag_offset_x": 0.0,
                "drag_offset_y": 0.0,
                "drag_target_x": float(x),
                "drag_target_y": float(y),
                "drag_animation_pending": False,
                "drag_samples": [],
                "velocity_x": 0.0,
                "velocity_y": 0.0,
                "motion_generation": 0,
                "native_hwnd": self._native_window_handle(window) if os.name == "nt" else None,
                "expires": time.monotonic() + self.rng.uniform(3.8, 5.8),
            }
            canvas.bind("<ButtonPress-1>", lambda event, cid=coin_id: self._begin_coin_drag(cid, event))
            canvas.bind("<ButtonRelease-1>", lambda event, cid=coin_id: self._release_coin(cid, event))
            self._repair_ransom_visibility()
            self._later(self.rng.randint(3800, 5800), lambda cid=coin_id: self._expire_coin(cid))
        self._later(self.rng.randint(380, 760), self._spawn_coin)

    def _coin_position(self, size: int) -> tuple[int, int]:
        if self._window_exists(self.note_window):
            note_left = self.note_window.winfo_x()
            note_top = self.note_window.winfo_y()
        else:
            note_left = self.screen_width - self.NOTE_WIDTH - 32
            note_top = 34
        note_right = note_left + self.NOTE_WIDTH
        note_bottom = note_top + self.NOTE_HEIGHT
        for _ in range(30):
            x = self.rng.randint(8, max(8, self.screen_width - size - 8))
            y = self.rng.randint(45, max(45, self.screen_height - size - 50))
            overlaps_note = x + size > note_left and x < note_right and y + size > note_top and y < note_bottom
            if not overlaps_note:
                return x, y
        return 20, max(60, self.screen_height - size - 80)

    def _collect_coin(self, coin_id: int) -> None:
        if self.stage != "ransom":
            return
        record = self.coin_windows.pop(coin_id, None)
        if record is None:
            return
        # During a drag this top-level still owns mouse capture.  Destroying it
        # synchronously made Windows choose a new active topmost window and the
        # opaque red backdrop could win one compositor frame. Hide its canvas
        # now, release capture, then destroy it after the input message ends.
        self._retire_collected_coin(record)
        self.balance = max(0, self.balance - self.COIN_VALUE)
        self.audio.play("coin.wav", channel="coin")
        if self.note_canvas is not None and self.balance_item is not None:
            self.note_canvas.itemconfigure(self.balance_item, text=str(self.balance))
        if self.balance <= 0:
            self._ransom_success()
            return
        # Commit the full game stack in one native batch after the captured
        # coin is hidden.  Unlike sequential lift() calls this never lets the
        # opaque backdrop appear between individual popup updates.
        self._restack_ransom_windows(self._ransom_layer_windows())

    def _begin_coin_drag(self, coin_id: int, event: tk.Event) -> None:
        record = self.coin_windows.get(coin_id)
        if self.stage != "ransom" or record is None or record["dragging"]:
            return
        window = record["window"]
        record["dragging"] = True
        record["user_armed"] = True
        record["moving"] = False
        record["motion_generation"] += 1
        record["velocity_x"] = 0.0
        record["velocity_y"] = 0.0
        record["drag_target_x"] = float(record["x"])
        record["drag_target_y"] = float(record["y"])
        record["drag_animation_pending"] = True
        pointer_x = float(getattr(event, "x_root", window.winfo_pointerx()))
        pointer_y = float(getattr(event, "y_root", window.winfo_pointery()))
        record["drag_offset_x"] = pointer_x - float(record["x"])
        record["drag_offset_y"] = pointer_y - float(record["y"])
        record["drag_samples"] = [(time.monotonic(), pointer_x, pointer_y)]
        try:
            record["canvas"].configure(cursor=self.minigame_cursor)
            record["canvas"].grab_set()
            self._raise_without_activation(window)
        except tk.TclError:
            pass
        generation = record["motion_generation"]
        self._later(0, lambda cid=coin_id, token=generation: self._animate_coin_drag(cid, token))

    def _coin_pointer_position(self) -> tuple[float, float]:
        # Query absolute screen coordinates at render time. Moving a native
        # window produces relative motion events, whose queued coordinates can
        # otherwise feed the previous window position back into the next move.
        x, y = self.root.winfo_pointerxy()
        return float(x), float(y)

    def _animate_coin_drag(self, coin_id: int, generation: int) -> None:
        record = self.coin_windows.get(coin_id)
        if (
            self.stage != "ransom"
            or record is None
            or not record["dragging"]
            or generation != record["motion_generation"]
        ):
            return
        pointer_x, pointer_y = self._coin_pointer_position()
        x, y = self._clamp_coin_position(pointer_x - record["drag_offset_x"],
                                          pointer_y - record["drag_offset_y"], int(record["size"]))
        record["drag_target_x"], record["drag_target_y"] = x, y
        now = time.monotonic()
        samples = record["drag_samples"] + [(now, pointer_x, pointer_y)]
        record["drag_samples"] = [sample for sample in samples[-24:] if now - sample[0] <= 0.18]
        moved = round(x) != round(float(record["x"])) or round(y) != round(float(record["y"]))
        record["x"], record["y"] = x, y
        if moved:
            self._move_coin_window(record, x, y)
        if moved and record["user_armed"] and self._coin_hits_note(record):
            self._collect_coin(coin_id)
            return
        self._later(self.COIN_DRAG_FRAME_MS, lambda cid=coin_id, token=generation: self._animate_coin_drag(cid, token))

    def _release_coin(self, coin_id: int, event: tk.Event) -> None:
        record = self.coin_windows.get(coin_id)
        if self.stage != "ransom" or record is None or not record["dragging"]:
            return
        pointer_x = float(getattr(event, "x_root", record["window"].winfo_pointerx()))
        pointer_y = float(getattr(event, "y_root", record["window"].winfo_pointery()))
        now = time.monotonic()
        samples = list(record["drag_samples"])
        samples.append((now, pointer_x, pointer_y))
        recent = [sample for sample in samples if now - sample[0] <= 0.16]
        # Apply the most recent pointer location immediately. This avoids a
        # final one-frame snap when release lands between drag ticks.
        release_x = pointer_x - float(record["drag_offset_x"])
        release_y = pointer_y - float(record["drag_offset_y"])
        release_x, release_y = self._clamp_coin_position(release_x, release_y, int(record["size"]))
        record["drag_target_x"], record["drag_target_y"] = release_x, release_y
        record["x"], record["y"] = release_x, release_y
        self._move_coin_window(record, release_x, release_y)
        record["dragging"] = False
        record["drag_animation_pending"] = False
        try:
            record["canvas"].configure(cursor=self.minigame_cursor)
            record["canvas"].grab_release()
        except tk.TclError:
            pass
        if len(recent) >= 2:
            first_time, first_x, first_y = recent[0]
            last_time, last_x, last_y = recent[-1]
            elapsed = max(0.016, last_time - first_time)
            record["velocity_x"] = max(-46.0, min(46.0, (last_x - first_x) / elapsed * 0.016))
            record["velocity_y"] = max(-46.0, min(46.0, (last_y - first_y) / elapsed * 0.016))
        else:
            record["velocity_x"] = 0.0
            record["velocity_y"] = 0.0
        record["moving"] = abs(record["velocity_x"]) + abs(record["velocity_y"]) >= 0.7
        record["motion_generation"] += 1
        generation = record["motion_generation"]
        if record["user_armed"] and self._coin_hits_note(record):
            self._collect_coin(coin_id)
            return
        if record["moving"]:
            self._later(16, lambda cid=coin_id, token=generation: self._animate_coin_motion(cid, token))

    def _animate_coin_motion(self, coin_id: int, generation: int) -> None:
        record = self.coin_windows.get(coin_id)
        if (
            self.stage != "ransom"
            or record is None
            or record["dragging"]
            or generation != record["motion_generation"]
        ):
            return
        size = int(record["size"])
        x = float(record["x"]) + float(record["velocity_x"])
        y = float(record["y"]) + float(record["velocity_y"])
        max_x = max(0.0, float(self.screen_width - size))
        max_y = max(0.0, float(self.screen_height - size - 1))
        if x < 0.0 or x > max_x:
            x = min(max(x, 0.0), max_x)
            record["velocity_x"] *= -0.72
        if y < 0.0 or y > max_y:
            y = min(max(y, 0.0), max_y)
            record["velocity_y"] *= -0.72
        record["velocity_x"] *= 0.965
        record["velocity_y"] *= 0.965
        # Flying coins treat the nuisance popup windows as solid obstacles.
        # This deliberately uses their visible bounds, unlike the forgiving
        # enlarged RANSOM payment target below.
        x, y = self._bounce_coin_from_glitch(record, x, y)
        record["x"], record["y"] = x, y
        if not self._move_coin_window(record, x, y):
            return
        # Only a coin that has actually been grabbed by the user is eligible.
        # This prevents spawn/automatic overlap from counting as payment while
        # still allowing a released, thrown coin to score on impact.
        if record["user_armed"] and self._coin_hits_note(record):
            self._collect_coin(coin_id)
            return
        record["moving"] = abs(record["velocity_x"]) + abs(record["velocity_y"]) >= 0.7
        if record["moving"]:
            self._later(16, lambda cid=coin_id, token=generation: self._animate_coin_motion(cid, token))

    def _bounce_coin_from_glitch(
        self,
        coin: dict[str, Any],
        x: float,
        y: float,
    ) -> tuple[float, float]:
        """Reflect a thrown coin off the currently visible nuisance popups."""
        size = int(coin["size"])
        coin_right = x + size
        coin_bottom = y + size
        for popup in self.glitch_windows:
            window = popup.get("window")
            if (
                not self._window_exists(window)
                or float(popup.get("alpha", 1.0)) <= 0.08
            ):
                continue
            # The animation writes these coordinates every 16ms, so they are
            # the same moving bounds that the player sees on screen.
            left = float(popup["x"])
            top = float(popup["y"])
            right = left + float(popup["width"])
            bottom = top + float(popup["height"])
            overlap_x = min(coin_right, right) - max(x, left)
            overlap_y = min(coin_bottom, bottom) - max(y, top)
            if overlap_x <= 0.0 or overlap_y <= 0.0:
                continue

            # Resolve along the shallower penetration axis. Prefer the travel
            # direction for a clean, predictable reflection at a corner.
            velocity_x = float(coin["velocity_x"])
            velocity_y = float(coin["velocity_y"])
            horizontal = overlap_x < overlap_y
            if overlap_x == overlap_y:
                horizontal = abs(velocity_x) >= abs(velocity_y)
            if horizontal:
                from_left = velocity_x > 0.0 or (velocity_x == 0.0 and x + size / 2 <= left + (right - left) / 2)
                if from_left:
                    x = left - size - 1.0
                    coin["velocity_x"] = -max(1.0, abs(velocity_x) * self.COIN_POPUP_BOUNCE)
                else:
                    x = right + 1.0
                    coin["velocity_x"] = max(1.0, abs(velocity_x) * self.COIN_POPUP_BOUNCE)
                coin["velocity_y"] *= 0.94
            else:
                from_top = velocity_y > 0.0 or (velocity_y == 0.0 and y + size / 2 <= top + (bottom - top) / 2)
                if from_top:
                    y = top - size - 1.0
                    coin["velocity_y"] = -max(1.0, abs(velocity_y) * self.COIN_POPUP_BOUNCE)
                else:
                    y = bottom + 1.0
                    coin["velocity_y"] = max(1.0, abs(velocity_y) * self.COIN_POPUP_BOUNCE)
                coin["velocity_x"] *= 0.94
            x, y = self._clamp_coin_position(x, y, size)
            return x, y
        return x, y

    def _clamp_coin_position(self, x: float, y: float, size: int) -> tuple[float, float]:
        return (
            min(max(0.0, x), max(0.0, float(self.screen_width - size))),
            min(max(0.0, y), max(0.0, float(self.screen_height - size - 1))),
        )

    @staticmethod
    def _move_coin_window(record: dict[str, Any], x: float, y: float) -> bool:
        """Move a coin without repeatedly changing focus or Z-order."""
        window = record["window"]
        try:
            if os.name == "nt":
                user32 = ctypes.windll.user32
                hwnd = record.get("native_hwnd")
                if hwnd is None:
                    user32.GetParent.argtypes = [ctypes.c_void_p]
                    user32.GetParent.restype = ctypes.c_void_p
                    child = int(window.winfo_id())
                    hwnd = int(user32.GetParent(child) or child)
                user32.SetWindowPos.argtypes = [ctypes.c_void_p, ctypes.c_void_p,
                                               ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                               ctypes.c_int, ctypes.c_uint]
                # SWP_NOSIZE | SWP_NOZORDER | SWP_NOACTIVATE | SWP_NOOWNERZORDER
                if user32.SetWindowPos(hwnd, 0, round(x), round(y), 0, 0, 0x0215):
                    return True
            window.geometry(f"+{round(x)}+{round(y)}")
            return True
        except (tk.TclError, OSError):
            return False

    def _coin_hits_note(self, record: dict[str, Any]) -> bool:
        if not self._window_exists(self.note_window):
            return False
        try:
            note_left = self.note_window.winfo_x()
            note_top = self.note_window.winfo_y()
            note_right = note_left + self.note_window.winfo_width()
            note_bottom = note_top + self.note_window.winfo_height()
        except tk.TclError:
            return False
        padding = self.COIN_HITBOX_PADDING
        coin_left = float(record["x"]) - padding
        coin_top = float(record["y"]) - padding
        coin_right = float(record["x"]) + int(record["size"]) + padding
        coin_bottom = float(record["y"]) + int(record["size"]) + padding
        return (
            coin_right >= note_left
            and coin_left <= note_right
            and coin_bottom >= note_top
            and coin_top <= note_bottom
        )

    def _expire_coin(self, coin_id: int) -> None:
        record = self.coin_windows.get(coin_id)
        if record is None:
            return
        if record["dragging"] or record["moving"]:
            self._later(700, lambda cid=coin_id: self._expire_coin(cid))
            return
        self._remove_coin(coin_id)

    def _retire_collected_coin(self, record: dict[str, Any]) -> None:
        record["dragging"] = False
        record["moving"] = False
        record["motion_generation"] += 1
        try:
            if self.root.grab_current() is record["canvas"]:
                record["canvas"].grab_release()
            record["canvas"].itemconfigure("all", state="hidden")
            record["window"].attributes("-alpha", 0.0)
        except tk.TclError:
            pass
        self.retiring_coin_windows.append(record)
        self._later(
            self.COIN_RETIRE_DELAY_MS,
            lambda item=record: self._destroy_retired_coin(item),
        )

    def _destroy_retired_coin(self, record: dict[str, Any]) -> None:
        if record in self.retiring_coin_windows:
            self.retiring_coin_windows.remove(record)
        self._destroy_window(record.get("window"))

    def _remove_coin(self, coin_id: int, repair_stack: bool = False) -> None:
        record = self.coin_windows.pop(coin_id, None)
        if record:
            record["dragging"] = False
            record["motion_generation"] += 1
            try:
                if self.root.grab_current() is record["canvas"]:
                    record["canvas"].grab_release()
            except tk.TclError:
                pass
            self._destroy_window(record.get("window"))
            if repair_stack:
                self._repair_ransom_visibility()

    def _update_ransom_clock(self) -> None:
        if self.stage != "ransom":
            return
        remaining = self.ransom_deadline - time.monotonic()
        if self.note_canvas is not None and self.time_item is not None:
            self.note_canvas.itemconfigure(self.time_item, text=format_clock(remaining))
        if remaining <= 0:
            self._ransom_failure()
            return
        self._later(50, self._update_ransom_clock)

    def _ransom_success(self) -> None:
        if self.stage != "ransom":
            return
        self.stage = "success"
        self.audio.stop_all()
        self.audio.play("ransom_success.ogg")
        self.status_var.set("支払い完了。すべての演出ウィンドウを閉じました")

        # Keep one physical popup for the whole result sequence. First black
        # out the RANSOM contents and move that unchanged-size popup to the
        # center. Only after it arrives do we put THANK YOU inside it, then
        # enlarge the same popup and finally close it.
        transition_window = self.note_window if self._window_exists(self.note_window) else None
        transition_canvas = self.note_canvas if transition_window is not None else None
        if transition_window is not None:
            transition_window.update_idletasks()
            start_x = transition_window.winfo_x()
            start_y = transition_window.winfo_y()
            start_width = max(1, transition_window.winfo_width())
            start_height = max(1, transition_window.winfo_height())
        else:
            start_width, start_height = self.NOTE_WIDTH, self.NOTE_HEIGHT
            start_x = (self.screen_width - start_width) // 2
            start_y = (self.screen_height - start_height) // 2

        self._destroy_ransom_windows(keep_note=transition_window is not None)
        if transition_canvas is not None:
            try:
                transition_canvas.delete("all")
                transition_canvas.configure(bg="#000000")
                transition_canvas.create_rectangle(
                    0,
                    0,
                    start_width,
                    start_height,
                    fill="#000000",
                    outline="",
                )
                transition_window.configure(bg="#000000")
                transition_window.attributes("-topmost", True)
                transition_window.lift()
                transition_window.update()
            except tk.TclError:
                transition_window = None

        target_width, target_height, target_x, target_y = self._thank_geometry()
        if transition_window is None:
            transition_window = tk.Toplevel(self.root)
            transition_window.title("RANSOM")
            transition_window.attributes("-topmost", True)
            transition_window.resizable(False, False)
            transition_canvas = tk.Canvas(
                transition_window,
                width=start_width,
                height=start_height,
                bg="#000000",
                highlightthickness=0,
                borderwidth=0,
            )
            transition_canvas.pack(fill="both", expand=True)
            start_x = (self.screen_width - start_width) // 2
            start_y = (self.screen_height - start_height) // 2
            transition_window.geometry(f"{start_width}x{start_height}+{start_x}+{start_y}")
            self.note_window = transition_window
            self.note_canvas = transition_canvas
            self._begin_thank_growth(
                transition_window,
                start_width,
                start_height,
                start_x,
                start_y,
                target_width,
                target_height,
                target_x,
                target_y,
            )
        else:
            center_x = (self.screen_width - start_width) // 2
            center_y = (self.screen_height - start_height) // 2
            self.thank_phase = "centering"
            self._animate_success_centering(
                transition_window,
                time.monotonic(),
                start_x,
                start_y,
                start_width,
                start_height,
                center_x,
                center_y,
                target_width,
                target_height,
                target_x,
                target_y,
            )

        # All shell effects are our own windows and disappear immediately.
        self._destroy_shell_overlays_async()
        self._later(5200, self._finish_terminal_event)

    def _thank_geometry(self) -> tuple[int, int, int, int]:
        source = self.source_images["thank_you.png"]
        aspect = source.width / max(1, source.height)
        max_width = max(320, self.screen_width - 48)
        max_height = max(220, self.screen_height - 86)
        width = min(self.THANK_MAX_WIDTH, max_width, int(max_height * aspect))
        height = max(1, int(round(width / aspect)))
        x = (self.screen_width - width) // 2
        y = (self.screen_height - height) // 2
        return width, height, x, y

    def _animate_success_centering(
        self,
        window: tk.Toplevel,
        started: float,
        start_x: int,
        start_y: int,
        start_width: int,
        start_height: int,
        center_x: int,
        center_y: int,
        target_width: int,
        target_height: int,
        target_x: int,
        target_y: int,
    ) -> None:
        if self.stage != "success" or not self._window_exists(window):
            return
        elapsed_ms = max(0.0, (time.monotonic() - started) * 1000.0)
        progress = min(1.0, elapsed_ms / self.THANK_CENTER_MS)
        eased = 1.0 - (1.0 - progress) ** 3
        x = round(start_x + (center_x - start_x) * eased)
        y = round(start_y + (center_y - start_y) * eased)
        try:
            window.geometry(f"{start_width}x{start_height}+{x}+{y}")
        except tk.TclError:
            return
        if progress >= 1.0:
            self._begin_thank_growth(
                window,
                start_width,
                start_height,
                center_x,
                center_y,
                target_width,
                target_height,
                target_x,
                target_y,
            )
            return
        self._later(
            self.THANK_FRAME_MS,
            lambda: self._animate_success_centering(
                window,
                started,
                start_x,
                start_y,
                start_width,
                start_height,
                center_x,
                center_y,
                target_width,
                target_height,
                target_x,
                target_y,
            ),
        )

    def _begin_thank_growth(
        self,
        window: tk.Toplevel,
        start_width: int,
        start_height: int,
        start_x: int,
        start_y: int,
        target_width: int,
        target_height: int,
        target_x: int,
        target_y: int,
    ) -> None:
        if self.stage != "success" or not self._window_exists(window):
            return
        canvas = self.note_canvas
        if canvas is None:
            return
        # Alias the existing RANSOM popup instead of constructing or layering
        # a second result window over it.
        self.thank_window = window
        self.thank_phase = "inserted"
        self.balance_item = None
        self.time_item = None
        canvas.configure(width=start_width, height=start_height, bg="#a7e86a")
        canvas.delete("all")
        self.thank_photo = self._new_pixel_photo("thank_you.png", (start_width, start_height))
        self.thank_image_item = canvas.create_image(
            start_width // 2,
            start_height // 2,
            image=self.thank_photo,
            tags=("thank_image",),
        )
        window.protocol("WM_DELETE_WINDOW", self._finish_terminal_event)
        self._show_input_passthrough(window)
        try:
            window.update()
        except tk.TclError:
            return
        # Hold one beat so the content replacement is visibly completed before
        # the same popup begins growing.
        self._later(
            self.THANK_INSERT_HOLD_MS,
            lambda: self._animate_thank_growth(
                window,
                time.monotonic(),
                start_width,
                start_height,
                start_x,
                start_y,
                target_width,
                target_height,
                target_x,
                target_y,
            ),
        )

    def _animate_thank_growth(
        self,
        window: tk.Toplevel,
        started: float,
        start_width: int,
        start_height: int,
        start_x: int,
        start_y: int,
        target_width: int,
        target_height: int,
        target_x: int,
        target_y: int,
    ) -> None:
        if self.stage != "success" or not self._window_exists(window) or self.note_canvas is None:
            return
        self.thank_phase = "growing"
        elapsed_ms = max(0.0, (time.monotonic() - started) * 1000.0)
        progress = min(1.0, elapsed_ms / self.THANK_GROW_MS)
        eased = 1.0 - (1.0 - progress) ** 3
        width = round(start_width + (target_width - start_width) * eased)
        height = round(start_height + (target_height - start_height) * eased)
        x = round(start_x + (target_x - start_x) * eased)
        y = round(start_y + (target_y - start_y) * eased)
        try:
            window.geometry(f"{width}x{height}+{x}+{y}")
            self.note_canvas.configure(width=width, height=height)
            self.thank_photo = self._new_pixel_photo("thank_you.png", (width, height))
            if self.thank_image_item is not None:
                self.note_canvas.coords(self.thank_image_item, width // 2, height // 2)
                self.note_canvas.itemconfigure(self.thank_image_item, image=self.thank_photo)
        except tk.TclError:
            return
        if progress >= 1.0:
            self.thank_phase = "display"
            # Only the image is brief; the supplied success sound remains intact.
            self._later(self.THANK_DISPLAY_MS, self._dismiss_thank_window)
            return
        self._later(
            self.THANK_FRAME_MS,
            lambda: self._animate_thank_growth(
                window,
                started,
                start_width,
                start_height,
                start_x,
                start_y,
                target_width,
                target_height,
                target_x,
                target_y,
            ),
        )

    def _dismiss_thank_window(self) -> None:
        if self.stage != "success":
            return
        closing_window = self.thank_window
        self._destroy_window(closing_window)
        self.thank_window = None
        self.thank_photo = None
        self.thank_image_item = None
        self.thank_phase = ""
        if self.note_window is closing_window:
            self.note_window = None
            self.note_canvas = None
            self.note_base_x = 0
            self.note_base_y = 0

    def _ransom_failure(self) -> None:
        if self.stage != "ransom":
            return
        self.stage = "failure"
        # The derived soundtrack starts its supplied final jump at exactly 90s.
        if not self.audio.music_is_playing():
            self.audio.play("failure.wav")
        self._destroy_ransom_windows()
        self._create_overlay()
        self._animate_failure(0)

    def _animate_failure(self, frame: int) -> None:
        if self.stage != "failure" or self.overlay_canvas is None:
            return
        size = int(min(self.screen_width, self.screen_height) * self.FAILURE_FACE_SCALE)
        cache_key = f"final-face:{size}"
        photo = self.photos.get(cache_key)
        if photo is None:
            # Scale once before the deadline starts. Re-scaling on every frame
            # made the former 78-frame animation take several seconds.
            image = self.source_images["final_face.png"].resize((size, size), resample_lanczos())
            photo = ImageTk.PhotoImage(image)
            self.photos[cache_key] = photo
        now = time.monotonic()
        if frame == 0:
            self.failure_deadline = now + self.FAILURE_DURATION_MS / 1000.0
        elif now >= self.failure_deadline:
            self._finish_terminal_event()
            return
        self.overlay_canvas.delete("all")
        background = "#350000"
        self.overlay_canvas.configure(bg=background)
        self.overlay_canvas.create_image(
            self.screen_width // 2 + self.rng.randint(-9, 9),
            self.screen_height // 2 + self.rng.randint(-8, 8),
            image=photo,
        )
        remaining_ms = max(1, math.ceil((self.failure_deadline - time.monotonic()) * 1000.0))
        self._later(min(self.FAILURE_FRAME_MS, remaining_ms), lambda: self._animate_failure(frame + 1))

    def _finish_terminal_event(self) -> None:
        if self.stage not in {"success", "failure"}:
            return
        self._destroy_window(self.thank_window)
        self.thank_window = None
        self.thank_photo = None
        self.thank_image_item = None
        self.thank_phase = ""
        self._destroy_overlay()
        self._destroy_ransom_windows()
        self._destroy_shell_overlays()
        self.audio.stop_all()
        if self.bridge_result_path is not None:
            # Reaching the payment phase means STOP was missed.  Both the
            # payment-complete and timeout endings therefore infect the NEO
            # encounter after the desktop animation has finished.
            self._write_bridge_result("infected")
            self.root.after(25, self.quit_app)
            return
        self._schedule_next()

    def _write_bridge_result(self, status: str) -> None:
        """Atomically return a one-shot encounter result to the game launcher."""
        if self.bridge_result_path is None or self.bridge_result_written:
            return
        try:
            destination = self.bridge_result_path.expanduser().resolve()
            destination.parent.mkdir(parents=True, exist_ok=True)
            temporary = destination.with_name(destination.name + ".tmp")
            temporary.write_text(status, encoding="utf-8")
            os.replace(temporary, destination)
            self.bridge_result_written = True
        except OSError:
            # The visual encounter should still restore and close even when a
            # launcher-owned result path becomes unavailable.
            pass

    # ---------- safe taskbar / desktop / cursor look-alike overlays ----------

    def _show_input_passthrough(self, window: tk.Toplevel) -> None:
        """Show a topmost result image without taking focus or blocking input."""
        window.update_idletasks()
        if os.name != "nt":
            window.deiconify()
            return
        try:
            user32 = ctypes.windll.user32
            child = int(window.winfo_id())
            user32.GetParent.argtypes = [ctypes.c_void_p]
            user32.GetParent.restype = ctypes.c_void_p
            hwnd = int(user32.GetParent(child) or child)
            get_style = getattr(user32, "GetWindowLongPtrW", user32.GetWindowLongW)
            set_style = getattr(user32, "SetWindowLongPtrW", user32.SetWindowLongW)
            get_style.argtypes = [ctypes.c_void_p, ctypes.c_int]
            get_style.restype = ctypes.c_ssize_t
            set_style.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_ssize_t]
            set_style.restype = ctypes.c_ssize_t
            ex_style = int(get_style(hwnd, -20))  # GWL_EXSTYLE
            # WS_EX_TRANSPARENT | WS_EX_TOOLWINDOW | WS_EX_LAYERED |
            # WS_EX_NOACTIVATE. Layered+transparent passes pointer hit tests
            # through to windows owned by other applications as well.
            set_style(
                hwnd,
                -20,
                ex_style | 0x00000020 | 0x00000080 | 0x00080000 | 0x08000000,
            )
            user32.SetLayeredWindowAttributes.argtypes = [
                ctypes.c_void_p,
                ctypes.c_uint,
                ctypes.c_ubyte,
                ctypes.c_uint,
            ]
            user32.SetLayeredWindowAttributes(hwnd, 0, 255, 0x00000002)
            window.deiconify()
            window.update_idletasks()
            user32.SetWindowPos.argtypes = [
                ctypes.c_void_p,
                ctypes.c_void_p,
                ctypes.c_int,
                ctypes.c_int,
                ctypes.c_int,
                ctypes.c_int,
                ctypes.c_uint,
            ]
            user32.SetWindowPos(
                hwnd,
                ctypes.c_void_p(-1),  # HWND_TOPMOST
                0,
                0,
                0,
                0,
                0x0001 | 0x0002 | 0x0010 | 0x0040,
            )  # NOSIZE | NOMOVE | NOACTIVATE | SHOWWINDOW
        except Exception:
            # Still avoid forcing focus if a Windows style call is unavailable.
            window.deiconify()

    def _make_non_minimizable(self, window: tk.Toplevel) -> None:
        """Disable minimize UI and immediately undo external minimize commands."""
        window.update_idletasks()
        if os.name == "nt":
            try:
                user32 = ctypes.windll.user32
                child = int(window.winfo_id())
                user32.GetParent.argtypes = [ctypes.c_void_p]
                user32.GetParent.restype = ctypes.c_void_p
                hwnd = int(user32.GetParent(child) or child)
                get_style = getattr(user32, "GetWindowLongPtrW", user32.GetWindowLongW)
                set_style = getattr(user32, "SetWindowLongPtrW", user32.SetWindowLongW)
                get_style.argtypes = [ctypes.c_void_p, ctypes.c_int]
                get_style.restype = ctypes.c_ssize_t
                set_style.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_ssize_t]
                set_style.restype = ctypes.c_ssize_t
                style = int(get_style(hwnd, -16))  # GWL_STYLE
                set_style(hwnd, -16, style & ~0x00020000)  # WS_MINIMIZEBOX
                user32.GetSystemMenu.argtypes = [ctypes.c_void_p, ctypes.c_bool]
                user32.GetSystemMenu.restype = ctypes.c_void_p
                user32.EnableMenuItem.argtypes = [ctypes.c_void_p, ctypes.c_uint, ctypes.c_uint]
                user32.DrawMenuBar.argtypes = [ctypes.c_void_p]
                menu = user32.GetSystemMenu(hwnd, False)
                if menu:
                    user32.EnableMenuItem(menu, 0xF020, 0x00000001)  # SC_MINIMIZE / MF_GRAYED
                    user32.DrawMenuBar(hwnd)
                user32.SetWindowPos.argtypes = [
                    ctypes.c_void_p,
                    ctypes.c_void_p,
                    ctypes.c_int,
                    ctypes.c_int,
                    ctypes.c_int,
                    ctypes.c_int,
                    ctypes.c_uint,
                ]
                user32.SetWindowPos(
                    hwnd,
                    None,
                    0,
                    0,
                    0,
                    0,
                    0x0001 | 0x0002 | 0x0004 | 0x0010 | 0x0020,
                )
            except Exception:
                pass

        def undo_minimize(event: tk.Event) -> None:
            if event.widget is window and not self._closing:
                self.root.after_idle(lambda: self._restore_ransom_window(window))

        window.bind("<Unmap>", undo_minimize, add="+")

    def _restore_ransom_window(self, window: tk.Toplevel) -> None:
        if self.stage != "ransom" or not self._window_exists(window):
            return
        try:
            if os.name == "nt":
                user32 = ctypes.windll.user32
                handle = self._native_window_handle(window)
                user32.IsIconic.argtypes = [ctypes.c_void_p]
                user32.IsWindowVisible.argtypes = [ctypes.c_void_p]
                user32.ShowWindow.argtypes = [ctypes.c_void_p, ctypes.c_int]
                if user32.IsIconic(handle) or not user32.IsWindowVisible(handle):
                    user32.ShowWindow(handle, 4)  # SW_SHOWNOACTIVATE
                get_style = getattr(user32, "GetWindowLongPtrW", user32.GetWindowLongW)
                get_style.argtypes = [ctypes.c_void_p, ctypes.c_int]
                get_style.restype = ctypes.c_ssize_t
                if not int(get_style(handle, -20)) & 0x8:  # WS_EX_TOPMOST
                    self._raise_without_activation(window)
            else:
                if window.state() in {"iconic", "withdrawn"}:
                    window.deiconify()
                window.attributes("-topmost", True)
        except (tk.TclError, OSError):
            pass

    @staticmethod
    def _native_window_handle(window: tk.Toplevel) -> int:
        user32 = ctypes.windll.user32
        user32.GetParent.argtypes = [ctypes.c_void_p]
        user32.GetParent.restype = ctypes.c_void_p
        child = int(window.winfo_id())
        return int(user32.GetParent(child) or child)

    def _raise_without_activation(self, window: tk.Toplevel) -> None:
        """Reorder this app's window without changing keyboard focus/owner order."""
        if os.name != "nt":
            window.lift()
            return
        user32 = ctypes.windll.user32
        user32.SetWindowPos.argtypes = [ctypes.c_void_p, ctypes.c_void_p,
                                       ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                       ctypes.c_int, ctypes.c_uint]
        user32.SetWindowPos(self._native_window_handle(window), ctypes.c_void_p(-1),
                           0, 0, 0, 0, 0x0213)  # NOSIZE|NOMOVE|NOACTIVATE|NOOWNERZORDER

    def _ransom_layer_windows(self) -> list[tk.Toplevel]:
        """Return this app's visible layers from back to front."""
        groups = [
            [self.desktop_overlay, self.taskbar_overlay]
            + [record["window"] for record in self.secondary_monitor_overlays],
            [self.ransom_frame_window],
            [record["window"] for record in self.glitch_windows],
            [self.note_window],
            [record["window"] for record in self.coin_windows.values()],
            [record["window"] for record in self.face_flash_windows],
        ]
        return [
            window
            for group in groups
            for window in group
            if self._window_exists(window)
        ]

    def _maintain_ransom_visibility(self) -> None:
        if self.stage != "ransom" or self._closing:
            return
        self._repair_ransom_visibility()
        self._later(self.VISIBILITY_WATCHDOG_MS, self._maintain_ransom_visibility)

    def _repair_ransom_visibility(self) -> None:
        """Keep popups above our backdrop, while preserving intentional fades.

        All layers used to have independent topmost flags. If Windows raised
        the opaque backdrop, the note remained hidden until its next teleport.
        Repair our own relative Z-order only when it is actually wrong; never
        activate windows, operate on another process, or revive a finished game.
        """
        if self.stage != "ransom" or self._closing:
            return
        try:
            controls = [r["window"] for r in self.glitch_windows]
            controls += [self.note_window]
            controls += [r["window"] for r in self.coin_windows.values()]
            for window in controls:
                if self._window_exists(window):
                    self._restore_ransom_window(window)
            if self._window_exists(self.note_window) and float(self.note_window.attributes("-alpha")) != 1.0:
                self.note_window.attributes("-alpha", 1.0)
            # A glitch's alpha belongs to its fade animation, not visibility repair.
            if os.name == "nt":
                user32 = ctypes.windll.user32
                user32.GetTopWindow.argtypes = [ctypes.c_void_p]
                user32.GetTopWindow.restype = ctypes.c_void_p
                user32.GetWindow.argtypes = [ctypes.c_void_p, ctypes.c_uint]
                user32.GetWindow.restype = ctypes.c_void_p
                ranks: dict[int, int] = {}
                handle = user32.GetTopWindow(None)
                while handle and int(handle) not in ranks and len(ranks) < 4096:
                    ranks[int(handle)] = len(ranks)
                    handle = user32.GetWindow(handle, 2)  # GW_HWNDNEXT
                groups = [
                    [self.desktop_overlay, self.taskbar_overlay]
                    + [record["window"] for record in self.secondary_monitor_overlays],
                    [self.ransom_frame_window],
                    [record["window"] for record in self.glitch_windows],
                    [self.note_window],
                    [record["window"] for record in self.coin_windows.values()],
                    [record["window"] for record in self.face_flash_windows],
                ]
                ordered = []
                for group in groups:
                    active = [(ranks.get(self._native_window_handle(w), 4096), w)
                              for w in group if self._window_exists(w)]
                    # Preserve the user's stacking order inside each category.
                    ordered.extend(sorted(active, key=lambda item: item[0], reverse=True))
                if any(lower[0] < upper[0] for lower, upper in zip(ordered, ordered[1:])):
                    self._restack_ransom_windows([window for _rank, window in ordered])
        except (tk.TclError, OSError):
            pass  # a layer can disappear between a notification and this check

    def _restack_ransom_windows(self, windows: list[tk.Toplevel]) -> bool:
        """Commit one native Z-order update, never expose a raised backdrop.

        Sequentially raising the opaque backdrop and then each popup exposed
        a red-only intermediate frame to the compositor during coin removal.
        DeferWindowPos applies the top-level windows as one batch instead.
        """
        if not windows or os.name != "nt":
            return False
        user32 = ctypes.windll.user32
        user32.BeginDeferWindowPos.argtypes = [ctypes.c_int]
        user32.BeginDeferWindowPos.restype = ctypes.c_void_p
        user32.DeferWindowPos.argtypes = [ctypes.c_void_p, ctypes.c_void_p, ctypes.c_void_p,
                                         ctypes.c_int, ctypes.c_int, ctypes.c_int, ctypes.c_int,
                                         ctypes.c_uint]
        user32.DeferWindowPos.restype = ctypes.c_void_p
        user32.EndDeferWindowPos.argtypes = [ctypes.c_void_p]
        batch = user32.BeginDeferWindowPos(len(windows))
        if not batch:
            return False
        for window in windows:
            batch = user32.DeferWindowPos(batch, self._native_window_handle(window),
                                           ctypes.c_void_p(-1), 0, 0, 0, 0, 0x0213)
            if not batch:
                return False  # Windows frees a failed batch; retry on next poll.
        return bool(user32.EndDeferWindowPos(batch))

    def _make_clickthrough(self, window: tk.Toplevel) -> bool:
        """Make a visual-only Tk layer unable to intercept mouse activation."""
        return self._configure_visual_layer(window, pointer_passthrough=True)

    def _configure_visual_layer(self, window: tk.Toplevel, pointer_passthrough: bool) -> bool:
        """Style only our own window; backgrounds can host a native cursor."""
        if os.name != "nt":
            return False
        try:
            window.update_idletasks()
            user32 = ctypes.windll.user32
            child = int(window.winfo_id())
            user32.GetParent.argtypes = [ctypes.c_void_p]
            user32.GetParent.restype = ctypes.c_void_p
            parent = int(user32.GetParent(child))
            hwnd = parent or child
            get_style = getattr(user32, "GetWindowLongPtrW", user32.GetWindowLongW)
            set_style = getattr(user32, "SetWindowLongPtrW", user32.SetWindowLongW)
            get_style.argtypes = [ctypes.c_void_p, ctypes.c_int]
            get_style.restype = ctypes.c_ssize_t
            set_style.argtypes = [ctypes.c_void_p, ctypes.c_int, ctypes.c_ssize_t]
            set_style.restype = ctypes.c_ssize_t
            ex_style = int(get_style(hwnd, -20))
            # TOOLWINDOW | LAYERED | NOACTIVATE, optionally WS_EX_TRANSPARENT.
            ex_style |= 0x00000080 | 0x00080000 | 0x08000000
            ex_style = ex_style | 0x20 if pointer_passthrough else ex_style & ~0x20
            set_style(hwnd, -20, ex_style)
            user32.SetWindowPos.argtypes = [
                ctypes.c_void_p,
                ctypes.c_void_p,
                ctypes.c_int,
                ctypes.c_int,
                ctypes.c_int,
                ctypes.c_int,
                ctypes.c_uint,
            ]
            user32.SetWindowPos(hwnd, ctypes.c_void_p(-1), 0, 0, 0, 0, 0x0001 | 0x0002 | 0x0010 | 0x0020)
            return True
        except Exception:
            return False

    def _taskbar_rect(self) -> tuple[int, int, int, int]:
        if os.name == "nt":
            try:
                class RECT(ctypes.Structure):
                    _fields_ = [
                        ("left", ctypes.c_long),
                        ("top", ctypes.c_long),
                        ("right", ctypes.c_long),
                        ("bottom", ctypes.c_long),
                    ]

                rect = RECT()
                hwnd = ctypes.windll.user32.FindWindowW("Shell_TrayWnd", None)
                if hwnd and ctypes.windll.user32.GetWindowRect(hwnd, ctypes.byref(rect)):
                    return rect.left, rect.top, rect.right - rect.left, rect.bottom - rect.top
            except Exception:
                pass
        return 0, self.screen_height - 48, self.screen_width, 48

    def _desktop_icon_count(self) -> int:
        """Read the desktop list count; never changes Shell items or icon data."""
        if os.name == "nt":
            try:
                user32 = ctypes.windll.user32
                progman = user32.FindWindowW("Progman", None)
                defview = user32.FindWindowExW(progman, 0, "SHELLDLL_DefView", None)
                if not defview:
                    worker = 0
                    for _ in range(128):
                        worker = user32.FindWindowExW(0, worker, "WorkerW", None)
                        if not worker:
                            break
                        defview = user32.FindWindowExW(worker, 0, "SHELLDLL_DefView", None)
                        if defview:
                            break
                if defview:
                    listview = user32.FindWindowExW(defview, 0, "SysListView32", "FolderView")
                    if listview:
                        count = int(user32.SendMessageW(listview, 0x1004, 0, 0))
                        if count >= 0:
                            return min(512, count)
            except Exception:
                pass
        return 12

    def _shell_variants(self, size: int) -> list[ImageTk.PhotoImage]:
        cached = self.shell_photo_cache.get(size)
        if cached is not None:
            return cached
        stop = self.source_images["stop.png"].resize((size, size), resample_lanczos())
        images: list[Image.Image] = [stop]
        for index in range(1, 7):
            source = self.source_images[f"glitch_{index}.png"].resize((size, size), resample_lanczos())
            gray = source.convert("L")
            red = ImageOps.colorize(gray, black="#180000", white="#ff2525").convert("RGBA")
            red.putalpha(220)
            images.append(red)
        # Hybrids replace only several horizontal strips, so an icon can become
        # partly glitched without losing the transparent STOP silhouette.
        for index in (1, 3, 6):
            hybrid = stop.copy()
            source = self.source_images[f"glitch_{index}.png"].resize((size, size), resample_lanczos())
            red = ImageOps.colorize(source.convert("L"), black="#220000", white="#ff3030").convert("RGBA")
            mask = Image.new("L", (size, size), 0)
            draw = ImageDraw.Draw(mask)
            for band in range(3):
                y = (index * 7 + band * max(5, size // 4)) % max(1, size - 4)
                draw.rectangle((0, y, size, min(size, y + max(3, size // 9))), fill=225)
            hybrid.alpha_composite(Image.composite(red, Image.new("RGBA", (size, size)), mask))
            images.append(hybrid)
        photos = [ImageTk.PhotoImage(image) for image in images]
        self.shell_photo_cache[size] = photos
        return photos

    def _create_shell_overlays(self) -> None:
        """Create visual-only shell effects for the failed STOP sequence.

        Windows wallpaper, shortcut metadata, taskbars, cursors and other app
        windows are deliberately left untouched.  Top-level click-through
        layers disappear automatically even if Windows terminates the process
        during shutdown, so the effect cannot leave the desktop damaged.
        """
        if not self.enable_shell_effects or os.name != "nt" or self.system_effects_active:
            return
        self.system_effects_active = True
        if self.stage == "ransom":
            self._create_visual_shell_overlays()


    def _desktop_stop_photo(self, size: int = 54) -> ImageTk.PhotoImage:
        key = f"desktop_stop:{size}"
        photo = self.photos.get(key)
        if photo is None:
            source = self.source_images["stop.png"].resize((size, size), resample_lanczos())
            photo = ImageTk.PhotoImage(source)
            self.photos[key] = photo
        return photo

    def _create_desktop_stop_overlay(self) -> None:
        """Cover every desktop item slot, including non-.lnk Shell items."""
        if self.desktop_overlay is not None or os.name != "nt":
            return
        desktop = tk.Toplevel(self.root)
        self.desktop_overlay = desktop
        desktop.overrideredirect(True)
        desktop.configure(bg=TRANSPARENT_KEY)
        desktop.attributes("-topmost", True)
        try:
            desktop.attributes("-transparentcolor", TRANSPARENT_KEY)
        except tk.TclError:
            pass
        desktop.geometry(f"{self.screen_width}x{self.screen_height}+0+0")
        canvas = tk.Canvas(
            desktop,
            width=self.screen_width,
            height=self.screen_height,
            bg=TRANSPARENT_KEY,
            highlightthickness=0,
        )
        self.desktop_canvas = canvas
        canvas.pack(fill="both", expand=True)
        stop_photo = self._desktop_stop_photo()
        icon_count = self._desktop_icon_count()
        rows = max(1, (self.screen_height - 58) // 82)
        for index in range(icon_count):
            column, row = divmod(index, rows)
            canvas.create_image(45 + column * 92, 45 + row * 82, image=stop_photo)
        if not self._make_clickthrough(desktop):
            self._destroy_window(desktop)
            self.desktop_overlay = None
            self.desktop_canvas = None






















    def _restore_actual_system_effects(self) -> None:
        """Clear visual state; the safe runtime never mutates Windows state."""
        self.system_effects_active = False

    def _create_visual_shell_overlays(self) -> None:
        if not self.enable_shell_effects or os.name != "nt" or self.desktop_overlay is not None:
            return
        task_x, task_y, task_w, task_h = self._taskbar_rect()

        desktop = tk.Toplevel(self.root)
        self.desktop_overlay = desktop
        desktop.overrideredirect(True)
        desktop.configure(bg="#760000", cursor=self.minigame_cursor)
        desktop.attributes("-topmost", True)
        desktop.attributes("-alpha", 1.0)
        desktop.geometry(f"{self.screen_width}x{self.screen_height}+0+0")
        dcanvas = tk.Canvas(
            desktop,
            width=self.screen_width,
            height=self.screen_height,
            bg="#760000",
            highlightthickness=0,
            cursor=self.minigame_cursor,
        )
        self.desktop_canvas = dcanvas
        dcanvas.pack(fill="both", expand=True)
        icon_count = self._desktop_icon_count()
        variants = self._shell_variants(48)
        usable_bottom = task_y if task_y > self.screen_height // 2 else self.screen_height - 55
        rows = max(1, (usable_bottom - 45) // 82)
        for index in range(icon_count):
            column, row = divmod(index, rows)
            item = dcanvas.create_image(45 + column * 92, 48 + row * 82, image=self.rng.choice(variants))
            self.shell_icon_records.append({"canvas": dcanvas, "item": item, "variants": variants})

        taskbar = tk.Toplevel(self.root)
        self.taskbar_overlay = taskbar
        taskbar.overrideredirect(True)
        taskbar.configure(bg="#9d0000", cursor=self.minigame_cursor)
        taskbar.attributes("-topmost", True)
        taskbar.attributes("-alpha", 0.84)
        taskbar.geometry(f"{task_w}x{task_h}+{task_x}+{task_y}")
        tcanvas = tk.Canvas(taskbar, width=task_w, height=task_h, bg="#9d0000", highlightthickness=0, cursor=self.minigame_cursor)
        self.taskbar_canvas = tcanvas
        tcanvas.pack(fill="both", expand=True)
        for line in range(0, max(task_w, task_h), 9):
            if task_w >= task_h:
                y = line % max(1, task_h)
                tcanvas.create_line(0, y, task_w, y, fill="#c81414")
            else:
                x = line % max(1, task_w)
                tcanvas.create_line(x, 0, x, task_h, fill="#c81414")
        task_icon_size = max(28, min(46, min(task_w, task_h) - 7))
        task_variants = self._shell_variants(task_icon_size)
        step = max(42, min(task_w, task_h))
        if task_w >= task_h:
            for position in range(step // 2, task_w, step):
                item = tcanvas.create_image(position, task_h // 2, image=self.rng.choice(task_variants))
                self.shell_icon_records.append({"canvas": tcanvas, "item": item, "variants": task_variants})
        else:
            for position in range(step // 2, task_h, step):
                item = tcanvas.create_image(task_w // 2, position, image=self.rng.choice(task_variants))
                self.shell_icon_records.append({"canvas": tcanvas, "item": item, "variants": task_variants})

        # These are ordinary game surfaces: mouse events remain inside the
        # game, allowing Tk to supply one red native pointer. No pointer clone,
        # input hooks, system-cursor edits, or changes to other apps are needed.
        if not all(self._configure_visual_layer(window, pointer_passthrough=False) for window in (desktop, taskbar)):
            self._destroy_shell_overlays()
            return
        self.shell_texture_deadline = 0.0
        self._animate_shell_overlays()

    def _animate_shell_overlays(self) -> None:
        if not self.system_effects_active or self.stage not in {"attack", "downloading", "ransom", "failure"}:
            return
        now = time.monotonic()
        if now >= self.shell_texture_deadline:
            for record in self.shell_icon_records:
                if self.rng.random() < 0.22:
                    try:
                        record["canvas"].itemconfigure(record["item"], image=self.rng.choice(record["variants"]))
                    except tk.TclError:
                        pass
            self.shell_texture_deadline = now + self.rng.uniform(0.33, 0.56)
        self._later(16, self._animate_shell_overlays)

    def _monitor_rectangles(self) -> list[tuple[int, int, int, int, bool]]:
        """Enumerate monitor rectangles as left, top, width, height, primary."""
        if os.name != "nt":
            return [(0, 0, self.screen_width, self.screen_height, True)]
        monitors: list[tuple[int, int, int, int, bool]] = []
        try:
            class RECT(ctypes.Structure):
                _fields_ = [
                    ("left", ctypes.c_long),
                    ("top", ctypes.c_long),
                    ("right", ctypes.c_long),
                    ("bottom", ctypes.c_long),
                ]

            class MONITORINFO(ctypes.Structure):
                _fields_ = [
                    ("cbSize", ctypes.c_ulong),
                    ("rcMonitor", RECT),
                    ("rcWork", RECT),
                    ("dwFlags", ctypes.c_ulong),
                ]

            callback_type = ctypes.WINFUNCTYPE(
                ctypes.c_bool,
                ctypes.c_void_p,
                ctypes.c_void_p,
                ctypes.POINTER(RECT),
                ctypes.c_ssize_t,
            )
            user32 = ctypes.windll.user32

            def collect(
                monitor_handle: int,
                _device_context: int,
                monitor_rect: ctypes.POINTER(RECT),
                _data: int,
            ) -> bool:
                rect = monitor_rect.contents
                info = MONITORINFO()
                info.cbSize = ctypes.sizeof(MONITORINFO)
                primary = bool(user32.GetMonitorInfoW(monitor_handle, ctypes.byref(info)) and info.dwFlags & 1)
                width = max(1, rect.right - rect.left)
                height = max(1, rect.bottom - rect.top)
                monitors.append((rect.left, rect.top, width, height, primary))
                return True

            callback = callback_type(collect)
            user32.EnumDisplayMonitors(None, None, callback, 0)
        except Exception:
            monitors.clear()
        if not monitors:
            monitors.append((0, 0, self.screen_width, self.screen_height, True))
        return monitors

    def _secondary_monitor_red_color(self) -> str:
        red, green, blue, _alpha = self.source_images["glitch_5.png"].getpixel((0, 0))
        return f"#{red:02x}{green:02x}{blue:02x}"

    def _secondary_monitor_photo(self, width: int, height: int) -> ImageTk.PhotoImage:
        key = (width, height)
        photo = self.secondary_monitor_photos.get(key)
        if photo is None:
            # Fill the whole secondary display with the supplied texture. Use
            # nearest-neighbour sampling to retain its deliberately pixelated
            # appearance instead of introducing smooth AI-like interpolation.
            image = self.source_images["glitch_5.png"].resize(
                (width, height),
                Image.Resampling.NEAREST,
            )
            photo = ImageTk.PhotoImage(image)
            self.secondary_monitor_photos[key] = photo
        return photo

    def _prepare_secondary_monitor_photos(self) -> None:
        if self._closing:
            return
        for _left, _top, width, height, primary in self._monitor_rectangles():
            if not primary:
                self._secondary_monitor_photo(width, height)

    @staticmethod
    def _monitor_geometry(width: int, height: int, left: int, top: int) -> str:
        return f"{width}x{height}{left:+d}{top:+d}"

    def _create_secondary_monitor_overlays(self) -> None:
        if self.stage not in {"attack", "downloading", "ransom", "failure"}:
            return
        self._destroy_secondary_monitor_overlays()
        background = self._secondary_monitor_red_color()
        for left, top, width, height, primary in self._monitor_rectangles():
            if primary:
                continue
            window = tk.Toplevel(self.root)
            window.withdraw()
            window.overrideredirect(True)
            window.configure(bg=background)
            window.attributes("-topmost", True)
            window.geometry(self._monitor_geometry(width, height, left, top))
            canvas = tk.Canvas(
                window,
                width=width,
                height=height,
                bg=background,
                highlightthickness=0,
                borderwidth=0,
            )
            canvas.pack(fill="both", expand=True)
            photo = self._secondary_monitor_photo(width, height)
            item = canvas.create_image(width // 2, height // 2, image=photo)
            record = {"window": window, "canvas": canvas, "item": item, "photo": photo}
            self.secondary_monitor_overlays.append(record)
            self._show_input_passthrough(window)
            # Tk negative offsets are measured from the right/bottom edge.
            # Move our own window using absolute virtual-desktop coordinates.
            self._move_coin_window(record, left, top)
            try:
                window.lift()
            except tk.TclError:
                pass
        if self.secondary_monitor_overlays:
            self._later(self.rng.randint(900, 2600), self._flash_secondary_monitors)

    def _flash_secondary_monitors(self, pulses: int | None = None) -> None:
        if self.stage not in {"attack", "downloading", "ransom", "failure"}:
            return
        if not self.secondary_monitor_overlays:
            return
        if pulses is None:
            pulses = self.rng.choice((1, 1, 1, 2, 2, 3))
        for record in self.secondary_monitor_overlays:
            try:
                record["canvas"].itemconfigure(record["item"], state="hidden")
            except tk.TclError:
                pass
        self._later(
            self.rng.randint(65, 145),
            lambda remaining=pulses: self._restore_secondary_monitor_images(remaining),
        )

    def _restore_secondary_monitor_images(self, remaining_pulses: int) -> None:
        if self.stage not in {"attack", "downloading", "ransom", "failure"}:
            return
        if not self.secondary_monitor_overlays:
            return
        for record in self.secondary_monitor_overlays:
            try:
                record["canvas"].itemconfigure(record["item"], state="normal")
                record["window"].attributes("-topmost", True)
                record["window"].lift()
            except tk.TclError:
                pass
        if remaining_pulses > 1:
            self._later(
                self.rng.randint(55, 125),
                lambda remaining=remaining_pulses - 1: self._flash_secondary_monitors(remaining),
            )
        else:
            self._later(self.rng.randint(1400, 4400), self._flash_secondary_monitors)

    def _destroy_secondary_monitor_overlays(self) -> None:
        for record in self.secondary_monitor_overlays:
            self._destroy_window(record.get("window"))
        self.secondary_monitor_overlays.clear()

    @staticmethod
    def _delete_canvas_item(canvas: tk.Canvas | None, item: int) -> None:
        if canvas is not None:
            try:
                canvas.delete(item)
            except tk.TclError:
                pass

    def _destroy_shell_overlay_windows(self) -> None:
        """Remove the Tk look-alike layers without waiting on Windows."""
        self._destroy_secondary_monitor_overlays()
        for window in (self.cursor_overlay, self.taskbar_overlay, self.desktop_overlay):
            self._destroy_window(window)
        self.cursor_overlay = None
        self.cursor_canvas = None
        self.cursor_item = None
        self.taskbar_overlay = None
        self.taskbar_canvas = None
        self.desktop_overlay = None
        self.desktop_canvas = None
        self.shell_icon_records.clear()

    def _destroy_shell_overlays_async(self) -> None:
        """Remove visual-only layers immediately during the success animation."""
        self._destroy_shell_overlay_windows()
        self._restore_actual_system_effects()

    def _destroy_shell_overlays(self) -> None:
        # Visual layers disappear synchronously; no OS restoration is needed.
        self._destroy_shell_overlay_windows()
        self._restore_actual_system_effects()

    # ---------- visuals and window lifecycle ----------

    def _create_overlay(self) -> None:
        self._destroy_overlay()
        window = tk.Toplevel(self.root)
        self.overlay = window
        window.overrideredirect(True)
        window.configure(bg="black")
        window.attributes("-topmost", True)
        window.geometry(f"{self.screen_width}x{self.screen_height}+0+0")
        canvas = tk.Canvas(
            window,
            width=self.screen_width,
            height=self.screen_height,
            bg="black",
            highlightthickness=0,
        )
        self.overlay_canvas = canvas
        canvas.pack(fill="both", expand=True)
        window.lift()
        window.update_idletasks()

    def _animate_noise(self) -> None:
        if self.stage not in {"reaction_grace", "reaction"} or self.overlay_canvas is None:
            return
        canvas = self.overlay_canvas
        canvas.delete("noise")
        self._draw_red_noise(canvas, 115, include_white=False, tag="noise")
        canvas.tag_lower("noise")
        canvas.tag_raise("entity")
        canvas.tag_raise("stop")
        self._later(42, self._animate_noise)

    def _draw_red_noise(
        self,
        canvas: tk.Canvas,
        count: int,
        include_white: bool,
        tag: str | None = None,
    ) -> None:
        colors = ["#310000", "#690000", "#a90000", "#ff1111", "#170000"]
        if include_white:
            colors.extend(("#ffffff", "#d0d0d0"))
        tags = (tag,) if tag else ()
        for _ in range(count):
            y = self.rng.randrange(0, self.screen_height)
            x1 = self.rng.randrange(0, max(1, self.screen_width - 20))
            length = self.rng.randint(14, max(30, self.screen_width // 3))
            canvas.create_rectangle(
                x1,
                y,
                min(self.screen_width, x1 + length),
                y + self.rng.randint(1, 6),
                fill=self.rng.choice(colors),
                outline="",
                tags=tags,
            )

    def _load_sources(self) -> None:
        for name in ASSET_NAMES:
            with Image.open(ASSET_DIR / name) as image:
                self.source_images[name] = image.convert("RGBA")

    def _photo(self, name: str, size: tuple[int, int]) -> ImageTk.PhotoImage:
        key = f"{name}:{size[0]}x{size[1]}"
        photo = self.photos.get(key)
        if photo is None:
            image = self.source_images[name].resize(size, resample_lanczos())
            photo = ImageTk.PhotoImage(image)
            self.photos[key] = photo
        return photo

    def _new_photo(self, name: str, size: tuple[int, int]) -> ImageTk.PhotoImage:
        image = self.source_images[name].resize(size, resample_lanczos())
        return ImageTk.PhotoImage(image)

    def _new_pixel_photo(self, name: str, size: tuple[int, int]) -> ImageTk.PhotoImage:
        image = self.source_images[name].resize(size, Image.Resampling.NEAREST)
        return ImageTk.PhotoImage(image)

    def _red_face(self) -> Image.Image:
        if self.face_red_source is None:
            source = self.source_images["ransom_face.png"]
            gray = source.convert("L")
            colored = ImageOps.colorize(gray, black="#000000", white="#ff1919").convert("RGBA")
            colored.putalpha(source.getchannel("A"))
            self.face_red_source = colored
        return self.face_red_source

    def _stop_background_photo(self) -> ImageTk.PhotoImage:
        key = f"stop-background:{self.screen_width}x{self.screen_height}"
        cached = self.photos.get(key)
        if cached is not None:
            return cached
        gradient = Image.radial_gradient("L").resize(
            (self.screen_width, self.screen_height),
            resample_lanczos(),
        )
        background = ImageOps.colorize(gradient, black="#090000", white="#360704").convert("RGBA")
        photo = ImageTk.PhotoImage(background)
        self.photos[key] = photo
        return photo

    def _later(self, milliseconds: int, callback: Callable[[], None]) -> str:
        holder: dict[str, str] = {}

        def wrapped() -> None:
            callback_id = holder.get("id")
            if callback_id is not None:
                self.after_ids.discard(callback_id)
            if not self._closing:
                callback()

        callback_id = self.root.after(milliseconds, wrapped)
        holder["id"] = callback_id
        self.after_ids.add(callback_id)
        return callback_id

    def _cancel_callbacks(self) -> None:
        # Invalidate any scheduled encounter as well as its Tk callbacks. The
        # independently polled fallback must never resurrect a cancelled wait.
        self.wait_sequence += 1
        self.wait_deadline = 0.0
        for callback_id in list(self.after_ids):
            try:
                self.root.after_cancel(callback_id)
            except tk.TclError:
                pass
        self.after_ids.clear()

    @staticmethod
    def _window_exists(window: tk.Toplevel | None) -> bool:
        if window is None:
            return False
        try:
            return bool(window.winfo_exists())
        except tk.TclError:
            return False

    def _destroy_window(self, window: tk.Toplevel | None) -> None:
        if self._window_exists(window):
            try:
                window.destroy()
            except tk.TclError:
                pass

    def _destroy_overlay(self) -> None:
        self._destroy_window(self.overlay)
        self.overlay = None
        self.overlay_canvas = None

    def _destroy_ransom_windows(self, keep_note: bool = False) -> None:
        self._destroy_ransom_border_frame()
        for record in list(self.glitch_windows):
            self._destroy_window(record.get("window"))
        self.glitch_windows.clear()
        for coin_id in list(self.coin_windows):
            self._remove_coin(coin_id, repair_stack=False)
        for record in list(self.retiring_coin_windows):
            self._destroy_retired_coin(record)
        for record in list(self.face_flash_windows):
            self._destroy_window(record.get("window"))
        self.face_flash_windows.clear()
        if not keep_note:
            self._destroy_window(self.note_window)
            self.note_window = None
            self.note_canvas = None
            self.note_base_x = 0
            self.note_base_y = 0
            self.note_jitter_tick = 0
            self.balance_item = None
            self.time_item = None

    def _reset_event_windows(self) -> None:
        self.intro_sequence_id += 1
        self._destroy_window(self.intro_window)
        self.intro_window = None
        self.intro_visible_since = 0.0
        self.intro_deadline = 0.0
        self._destroy_window(self.thank_window)
        self.thank_window = None
        self.thank_photo = None
        self.thank_image_item = None
        self.thank_phase = ""
        self._destroy_overlay()
        self._destroy_ransom_windows()
        self._destroy_shell_overlays()

    # ---------- emergency / app shutdown ----------

    def _handle_tk_callback_exception(self, exc_type: type[BaseException], exc: BaseException, traceback_obj: Any) -> None:
        import traceback

        if sys.stderr is not None:
            traceback.print_exception(exc_type, exc, traceback_obj, file=sys.stderr)
        try:
            self.error_log_path.parent.mkdir(parents=True, exist_ok=True)
            with self.error_log_path.open("a", encoding="utf-8") as log_file:
                log_file.write(
                    f"\n[{time.strftime('%Y-%m-%d %H:%M:%S')}] stage={self.stage}\n"
                )
                traceback.print_exception(exc_type, exc, traceback_obj, file=log_file)
        except OSError:
            pass

        # A stale animation callback must not terminate the hidden process.
        # Restore the desktop and return to the normal repeat cooldown.
        if self._closing or self._recovering_callback_error:
            return
        self._recovering_callback_error = True
        try:
            was_armed = self.armed
            self._cancel_callbacks()
            self.audio.stop_all()
            self._reset_event_windows()
            self.preheld_input_at_stop = False
            self.app_held_inputs.clear()
            self.reaction_failed = False
            if was_armed:
                self.armed = True
                self.stage = "idle"
                self.status_var.set("一時エラーから復帰しました。次回を待機します")
                self._schedule_next()
            else:
                self.stage = "idle"
        except Exception:
            try:
                self._restore_actual_system_effects()
            except Exception:
                pass
        finally:
            self._recovering_callback_error = False

    def stop_session(self) -> None:
        self._cancel_callbacks()
        self.audio.stop_all()
        self._reset_event_windows()
        self.app_held_inputs.clear()
        self.armed = False
        self.stage = "idle"
        self.status_var.set("停止しました。すべての演出ウィンドウを閉じました")
        if not self.headless:
            self.root.deiconify()
            self.root.lift()
            self.root.focus_force()

    def restore_and_continue(self) -> None:
        """Undo the current encounter without terminating the application."""
        if self._closing:
            return
        if self.exit_after_downloading:
            # The DELTARUNE story bridge is an unavoidable scripted infection.
            # Keep '-' as a recovery control for standalone builds only.
            return
        self._cancel_callbacks()
        self.audio.stop_all()
        self._reset_event_windows()
        self.preheld_input_at_stop = False
        self.app_held_inputs.clear()
        self.reaction_failed = False
        self.armed = True
        self.repeat_var.set(True)
        self.stage = "idle"
        self._schedule_next()
        self.status_var.set("現在の演出を復元しました。次のエンカウントを待機中")

    def quit_app(self) -> None:
        if self._closing:
            return
        if self.bridge_result_path is not None and not self.bridge_result_written:
            self._write_bridge_result("cancelled")
        self._closing = True
        self._cancel_callbacks()
        self._stop_global_command_listener()
        for callback_id in self.preparation_after_ids:
            self.root.after_cancel(callback_id)
        self.preparation_after_ids.clear()
        if self.wait_watchdog_after_id is not None:
            try:
                self.root.after_cancel(self.wait_watchdog_after_id)
            except tk.TclError:
                pass
            self.wait_watchdog_after_id = None
        self.audio.close()
        self._reset_event_windows()
        if self.private_font_loaded and os.name == "nt":
            try:
                ctypes.windll.gdi32.RemoveFontResourceExW(str(RANSOM_FONT_FILE), 0x10, None)
            except Exception:
                pass
            self.private_font_loaded = False
        try:
            self.root.destroy()
        except tk.TclError:
            pass


def run_self_test() -> int:
    def report(message: str) -> None:
        # PyInstaller's --windowed build intentionally has no stdout stream.
        if sys.stdout is not None:
            print(message)

    problems = validate_resources()
    if format_clock(90.0) != "01:30" or format_clock(0.0) != "00:00":
        problems.append("clock formatting test failed")
    if RansomSimulator.INTRO_EXTRA_MAX_MS != 300:
        problems.append("random warning grace extension test failed")
    if RansomSimulator.THANK_DISPLAY_MS != 1800:
        problems.append("THANK YOU display duration test failed")
    if (
        RansomSimulator.THANK_CENTER_MS != 420
        or RansomSimulator.THANK_INSERT_HOLD_MS != 90
        or RansomSimulator.THANK_GROW_MS != 420
        or RansomSimulator.THANK_FRAME_MS != 16
        or RansomSimulator.THANK_MAX_WIDTH != 1020
    ):
        problems.append("THANK YOU transition configuration test failed")
    if (
        RansomSimulator.REACTION_ARM_DELAY_MS != 250
        or RansomSimulator.REACTION_MS != 150
    ):
        problems.append("STOP 0.25s grace / 0.15s detection test failed")
    if (
        {command for command, _modifiers, _key in GLOBAL_COMMAND_HOTKEYS.values()}
        != {"test", "restore", "exit"}
    ):
        problems.append("global command hotkey mapping test failed")
    if RansomSimulator.DOWNLOADING_SEGMENTS != 12:
        problems.append("segmented DOWNLOADING bar configuration test failed")
    if (
        (RansomSimulator.DOWNLOADING_FRAMES - 1) * RansomSimulator.DOWNLOADING_FRAME_MS
        + RansomSimulator.DOWNLOADING_END_DELAY_MS
        != 1500
    ):
        problems.append("DOWNLOADING 1.500 second duration test failed")
    if RansomSimulator.COIN_HITBOX_PADDING != 36:
        problems.append("enlarged coin collision padding test failed")
    if (
        (
            RansomSimulator.DEFAULT_MIN_WAIT_SECONDS,
            RansomSimulator.DEFAULT_MAX_WAIT_SECONDS,
        )
        != (60, 180)
    ):
        problems.append("default encounter cooldown test failed")
    if RansomSimulator.STARTING_BALANCE != 500:
        problems.append("default starting balance test failed")
    if problems:
        report("SELF-TEST FAILED")
        for problem in problems:
            report(f"- {problem}")
        return 1
    report("SELF-TEST OK")
    report(f"Assets: {len(ASSET_NAMES)}")
    report(f"Sounds: {len(SOUND_NAMES)}")
    report(
        f"Timer: 01:30 / Balance: {RansomSimulator.STARTING_BALANCE} / Coin value: 10 / "
        f"Cooldown: {RansomSimulator.DEFAULT_MIN_WAIT_SECONDS}-"
        f"{RansomSimulator.DEFAULT_MAX_WAIT_SECONDS}s"
    )
    return 0


def run_runtime_self_test() -> int:
    """Exercise the packaged Tk/Pillow/pygame runtime without showing effects."""
    problems = validate_resources()
    if problems:
        return 1
    root: tk.Tk | None = None
    simulator: RansomSimulator | None = None
    try:
        root = tk.Tk()
        root.withdraw()
        simulator = RansomSimulator(
            root,
            demo_defaults=True,
            headless=True,
            enable_shell_effects=False,
            use_saved_settings=False,
        )
        simulator.audio.set_volume(0.0)
        cursor_probe = tk.Canvas(root, cursor=simulator.minigame_cursor)
        if os.name == "nt" and "red_cursor.cur" not in str(cursor_probe.cget("cursor")):
            return 1
        cursor_probe.destroy()
        if not simulator.audio.available:
            return 1
        if len(simulator.source_images) != len(ASSET_NAMES):
            return 1
        photo = simulator._photo("ransom_face.png", (64, 64))
        if photo.width() != 64 or photo.height() != 64:
            return 1
        probe_font = tkfont.Font(root=root, family=RANSOM_FONT_BOLD, size=-36)
        if not simulator.private_font_loaded or "Roboto Mono" not in probe_font.actual("family"):
            return 1
        draw_probe = Image.new("RGBA", (8, 8), (0, 0, 0, 0))
        ImageDraw.Draw(draw_probe).rectangle((1, 1, 6, 6), fill="#ff0000")
        if draw_probe.getpixel((3, 3))[0] != 255:
            return 1
        simulator.audio.play("coin.wav", channel="coin")
        if not simulator.audio._channels["coin"].get_busy():
            return 1
        simulator.audio.play("ransom_success.ogg", channel="event")
        if not simulator.audio._channels["event"].get_busy():
            return 1
        simulator.audio.play_music(MUSIC_NAME, start=MUSIC_START_SECONDS)
        if not simulator.audio.music_is_playing():
            return 1
        root.update_idletasks()
        return 0
    except Exception:
        return 1
    finally:
        if simulator is not None:
            simulator.quit_app()
        elif root is not None:
            try:
                root.destroy()
            except tk.TclError:
                pass


def main() -> int:
    parser = argparse.ArgumentParser(description=APP_NAME)
    parser.add_argument("--self-test", action="store_true", help="validate bundled files without opening windows")
    parser.add_argument("--runtime-self-test", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--demo-defaults", action="store_true", help="use short default wait values")
    parser.add_argument("--show-controller", action="store_true", help="show optional developer controls")
    parser.add_argument("--no-global-hotkeys", action="store_true", help="disable +, -, and * while waiting")
    parser.add_argument("--warning-preview", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--ransom-preview", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--bridge-result", type=Path, help=argparse.SUPPRESS)
    parser.add_argument("--force-stop-failure", action="store_true", help=argparse.SUPPRESS)
    parser.add_argument("--exit-after-downloading", action="store_true", help=argparse.SUPPRESS)
    args = parser.parse_args()
    if args.self_test:
        return run_self_test()
    if args.runtime_self_test:
        return run_runtime_self_test()

    problems = validate_resources()
    if problems:
        message = "\n".join(problems)
        if sys.stderr is not None:
            print(message, file=sys.stderr)
        return 1

    if os.name == "nt":
        try:
            ctypes.windll.shell32.SetCurrentProcessExplicitAppUserModelID("DOORS.Ransom.VisualSimulator")
        except Exception:
            pass
    root = tk.Tk()
    root.withdraw()
    simulator = RansomSimulator(
        root,
        demo_defaults=args.demo_defaults,
        headless=not args.show_controller,
        enable_shell_effects=args.bridge_result is None,
        bridge_result_path=args.bridge_result,
        force_stop_failure=args.force_stop_failure,
        exit_after_downloading=args.exit_after_downloading,
        enable_global_hotkeys=args.bridge_result is None and not args.no_global_hotkeys,
    )
    if args.show_controller:
        root.deiconify()
    if args.bridge_result is not None:
        simulator.repeat_var.set(False)
        simulator.arm(test=True)
    elif args.warning_preview:
        root.after(500, lambda: simulator.arm(test=True))
    elif args.ransom_preview:
        root.after(500, simulator.start_ransom_preview)
    elif not args.show_controller:
        # Do not leave the first automatic encounter behind a one-shot delayed
        # callback. If that startup callback is lost on a slow/overloaded PC,
        # the app used to remain unarmed forever and the waiting-deadline
        # fallback could not help. Arm synchronously before the main loop;
        # all actual encounter work still happens later on Tk's timer.
        simulator.arm()
    root.mainloop()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
