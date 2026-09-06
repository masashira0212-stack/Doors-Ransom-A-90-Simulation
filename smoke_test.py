"""Short GUI lifecycle smoke test for the desktop simulator."""

from __future__ import annotations

import ctypes
import os
import tkinter as tk
import time
from types import SimpleNamespace

from doors_ransom import RansomSimulator, TRANSPARENT_KEY, format_clock, validate_resources


def check(condition: bool, message: str) -> None:
    if not condition:
        raise AssertionError(message)


def main() -> int:
    problems = validate_resources()
    check(not problems, f"resource validation failed: {problems}")
    check(format_clock(90) == "01:30", "90-second clock formatting failed")
    check(
        RansomSimulator.REACTION_ARM_DELAY_MS == 250
        and RansomSimulator.REACTION_MS == 150,
        "STOP is not configured for 0.25s grace plus 0.15s detection",
    )
    check(
        RansomSimulator.POINTER_DEADZONE_PX == 14
        and RansomSimulator.POINTER_CONFIRM_SAMPLES == 2,
        "STOP pointer jitter filter is not configured",
    )
    check(
        not hasattr(RansomSimulator, "_poll_global_hotkeys"),
        "simulator still contains global keyboard polling",
    )
    check(
        RansomSimulator.INTRO_EXTRA_MAX_MS == 300,
        "warning-to-STOP random extension is not 0.3 seconds",
    )
    attack_ms = RansomSimulator.ATTACK_DURATION_MS
    downloading_ms = (
        (RansomSimulator.DOWNLOADING_FRAMES - 1) * RansomSimulator.DOWNLOADING_FRAME_MS
        + RansomSimulator.DOWNLOADING_END_DELAY_MS
    )
    check(attack_ms == 800, "STOP-failure jumpscare is not exactly 800ms")
    check(RansomSimulator.FAILURE_DURATION_MS == 800, "final jumpscare is not exactly 800ms")
    check(RansomSimulator.FAILURE_FRAME_MS == 16, "final jumpscare is not targeting 60fps")
    check(downloading_ms == 1500, "DOWNLOADING visual is not exactly 1.500 seconds")
    check(
        RansomSimulator.COIN_HITBOX_PADDING == 36,
        "coin-to-ransom collision padding was not enlarged",
    )

    root = tk.Tk()
    root.withdraw()
    simulator = RansomSimulator(root, demo_defaults=True, headless=True, enable_shell_effects=False, use_saved_settings=False)
    simulator.volume_var.set(0)
    simulator.audio.set_volume(0)
    simulator.repeat_var.set(False)
    check(
        not hasattr(simulator, "hotkey_after_id"),
        "simulator still schedules a global hotkey loop",
    )

    # Normal cooldown path (not the plus-key shortcut) must reach the same intro
    # and start its supplied face sound.
    simulator.min_wait_var.set("1")
    simulator.max_wait_var.set("1")
    old_warning_sound = simulator.audio._sounds.get("jumpscare2.mp3") if simulator.audio.available else None
    simulator.arm(test=False)
    cooldown_deadline = time.monotonic() + 1.4
    while simulator.stage == "waiting" and time.monotonic() < cooldown_deadline:
        root.update()
        time.sleep(0.01)
    check(simulator.stage == "intro", "normal cooldown did not launch the intro")
    root.update()
    check(
        simulator._window_exists(simulator.intro_window)
        and bool(simulator.intro_window.winfo_ismapped()),
        "normal cooldown advanced before the warning face was mapped",
    )
    check(
        simulator.intro_visible_since > 0.0
        and simulator.intro_deadline > simulator.intro_visible_since,
        "normal cooldown did not start its delay from confirmed face visibility",
    )
    work_left, work_top, work_right, work_bottom = simulator._primary_work_area()
    intro_x = simulator.intro_window.winfo_x()
    intro_y = simulator.intro_window.winfo_y()
    intro_width = simulator.intro_window.winfo_width()
    intro_height = simulator.intro_window.winfo_height()
    check(
        intro_x >= work_left + 12
        and intro_y >= work_top + 12
        and intro_x + intro_width <= work_right - 12
        and intro_y + intro_height <= work_bottom - 12,
        "automatic warning face spawned outside the measured work area",
    )
    current_sequence = simulator.intro_sequence_id
    simulator._center_warning(current_sequence)
    check(simulator.stage == "intro", "automatic warning skipped its confirmed visible duration")
    if simulator.audio.available:
        check(
            simulator.audio._sounds.get("jumpscare2.mp3") is not old_warning_sound,
            "normal cooldown did not reopen and reload the idle audio device",
        )
        check(simulator.audio._channels["warning"].get_busy(), "normal cooldown intro sound did not start")
    simulator._cancel_callbacks()
    simulator._reset_event_windows()
    simulator.audio.stop_all()

    # The normal Tk callback is supplemented by a lightweight deadline poller.
    # Simulate a lost callback: a past deadline must still launch the warning.
    simulator.armed = True
    simulator.stage = "waiting"
    simulator.wait_sequence += 1
    simulator.wait_deadline = time.monotonic() - 0.001
    simulator._poll_waiting_deadline()
    root.update()
    check(
        simulator.stage == "intro"
        and simulator._window_exists(simulator.intro_window)
        and bool(simulator.intro_window.winfo_ismapped()),
        "waiting deadline fallback did not recover a lost timed callback",
    )
    simulator._cancel_callbacks()
    simulator._reset_event_windows()
    simulator.audio.stop_all()

    # Repeated automatic-path warning creation must always map a measured,
    # in-bounds face before any centering/STOP transition is accepted.
    for warning_cycle in range(12):
        simulator.armed = True
        simulator.stage = "waiting"
        simulator._show_intro()
        root.update()
        check(
            simulator.stage == "intro"
            and simulator._window_exists(simulator.intro_window)
            and bool(simulator.intro_window.winfo_ismapped()),
            f"automatic warning cycle {warning_cycle + 1} was not visibly mapped",
        )
        left, top, right, bottom = simulator._primary_work_area()
        check(
            simulator.intro_window.winfo_x() >= left + 12
            and simulator.intro_window.winfo_y() >= top + 12
            and simulator.intro_window.winfo_x() + simulator.intro_window.winfo_width() <= right - 12
            and simulator.intro_window.winfo_y() + simulator.intro_window.winfo_height() <= bottom - 12,
            f"automatic warning cycle {warning_cycle + 1} exceeded the work area",
        )
        simulator._center_warning(simulator.intro_sequence_id)
        check(
            simulator.stage == "intro",
            f"automatic warning cycle {warning_cycle + 1} advanced before its face duration",
        )
        simulator._cancel_callbacks()
        simulator._reset_event_windows()
        simulator.audio.stop_all()

    # Warning lifecycle: random-position window -> full-screen STOP -> clean avoid.
    simulator.armed = True
    simulator.stage = "waiting"
    simulator._show_intro()
    root.update()
    check(simulator.stage == "intro", "intro stage did not start")
    check(simulator._window_exists(simulator.intro_window), "intro window was not created")
    check(simulator.intro_window.cget("bg") == TRANSPARENT_KEY, "intro window background is not keyed transparent")
    check(
        str(simulator.intro_window.attributes("-transparentcolor")) == TRANSPARENT_KEY,
        "intro window transparent color was not applied",
    )

    simulator.intro_deadline = time.monotonic() - 0.001
    simulator._center_warning()
    root.update()
    check(
        simulator.stage in {"centering", "reaction_grace"},
        "centering stage did not start",
    )
    check(simulator._window_exists(simulator.overlay), "full-screen overlay was not created")

    if simulator.stage == "centering":
        simulator._show_stop()
    root.update()
    check(simulator.stage == "reaction_grace", "STOP grace stage did not start")
    if simulator.audio.available:
        check(not simulator.audio._channels["loop"].get_busy(), "an extra sound overlapped jumpscare2 during STOP")
    simulator._arm_reaction()
    root.update()
    check(simulator.stage == "reaction", "STOP reaction stage did not arm")
    simulator._input_violation()
    check(simulator.stage == "reaction", "movement interrupted STOP before its fixed end")
    check(simulator.reaction_failed, "movement was not remembered during STOP")
    simulator._safe_avoid()
    simulator.overlay_canvas.update_idletasks()
    check(simulator.stage == "attack", "STOP failure did not open the jumpscare screen")
    check(bool(simulator.overlay_canvas.find_all()), "first jumpscare frame was not painted immediately")
    if simulator.audio.available:
        check(simulator.audio._channels["warning"].get_busy(), "jumpscare1 cut off jumpscare2")
        check(simulator.audio._channels["attack"].get_busy(), "jumpscare1 did not start with its first visual frame")
    simulator._show_downloading()
    check(simulator.stage == "downloading", "short jumpscare did not hand off to DOWNLOADING")
    first_download_text = simulator.overlay_canvas.itemcget(
        simulator.overlay_canvas.find_withtag("download_text")[0],
        "text",
    )
    check(first_download_text == "DOWNLOADING.", "DOWNLOADING ellipsis did not start at one dot")
    check(
        len(simulator.overlay_canvas.find_withtag("download_bar")) == 1,
        "segmented DOWNLOADING bar frame was not drawn",
    )
    simulator._animate_downloading(8)
    animated_download_text = simulator.overlay_canvas.itemcget(
        simulator.overlay_canvas.find_withtag("download_text")[0],
        "text",
    )
    check(animated_download_text == "DOWNLOADING...", "DOWNLOADING ellipsis did not animate")
    check(
        len(simulator.overlay_canvas.find_withtag("download_bar_segment")) == 4,
        "DOWNLOADING red blocks did not fill discretely one at a time",
    )
    check(
        not any(simulator.overlay_canvas.type(item) == "line" for item in simulator.overlay_canvas.find_all()),
        "DOWNLOADING still contains noise lines",
    )

    simulator._cancel_callbacks()
    simulator._reset_event_windows()
    simulator.audio.stop_all()
    simulator.armed = True
    simulator.stage = "waiting"
    simulator._show_intro()
    simulator.intro_deadline = time.monotonic() - 0.001
    simulator._center_warning()
    simulator._show_stop()
    simulator._arm_reaction()
    simulator.reaction_failed = False
    simulator._safe_avoid()
    simulator._finish_avoid()
    root.update()
    check(simulator.stage == "idle", "clean avoid did not return to idle")

    # Ransom lifecycle: actual popups + actual coin windows -> successful payment.
    simulator.start_ransom_preview()
    root.update()
    check(simulator.stage == "ransom", "ransom stage did not start")
    check(
        len(simulator.glitch_windows) == simulator.glitch_window_target
        and simulator.glitch_window_target in {4, 5},
        "expected four or five actual glitch popups were not created",
    )
    check(simulator._window_exists(simulator.note_window), "ransom note window was not created")
    protected_windows = [simulator.note_window, simulator.glitch_windows[0]["window"]]
    for protected_window in protected_windows:
        protected_window.iconify()
    root.update()
    root.update_idletasks()
    check(
        all(protected_window.state() != "iconic" for protected_window in protected_windows),
        "ransom or glitch popup remained minimized",
    )
    check(simulator._window_exists(simulator.ransom_frame_window), "animated red-dot border was not created")
    check(len(simulator.ransom_frame_photos) == 4, "pixel-art corners did not create four distinct texture cels")
    check(len(simulator.ransom_frame_items) == 4, "pixel-art noise did not create all four corners")
    check(
        all(
            photo.width() == simulator.ransom_frame_thickness
            and photo.height() == simulator.ransom_frame_thickness
            for frame_photos in simulator.ransom_frame_photos
            for photo in frame_photos
        ),
        "red-dot noise still used full-length screen-edge strips",
    )
    check(
        simulator.FRAME_DOT_SPACING == simulator.FRAME_DOT_SIZE,
        "red frame still has a fixed gap between adjacent dot cells",
    )
    check(
        abs(float(simulator.ransom_frame_window.attributes("-alpha")) - simulator.FRAME_OPACITY) < 0.02,
        "red frame is not semi-transparent",
    )
    simulator._create_desktop_stop_overlay()
    root.update()
    check(simulator._window_exists(simulator.desktop_overlay), "desktop icon fallback layer was not created")
    check(
        len(simulator.desktop_canvas.find_all()) == simulator._desktop_icon_count(),
        "desktop icon fallback did not cover every reported desktop item slot",
    )
    simulator._flash_random_face()
    simulator._flash_desktop_face()
    check(
        {record["kind"] for record in simulator.face_flash_windows} == {"screen", "desktop"},
        "screen and desktop-area face flashes were not created separately",
    )
    check(
        all(48 <= record["size"] <= 108 for record in simulator.face_flash_windows),
        "face flash was not kept small",
    )
    root.update()
    check(
        simulator.note_window.winfo_width() == simulator.NOTE_WIDTH
        and simulator.note_window.winfo_height() == simulator.NOTE_HEIGHT,
        "ransom note was not enlarged",
    )
    note_text = " ".join(
        simulator.note_canvas.itemcget(item, "text")
        for item in simulator.note_canvas.find_all()
        if simulator.note_canvas.type(item) == "text"
    )
    check("FILES" in note_text and "ITEMS" not in note_text, "redrawn ransom note did not use FILES")
    check(
        simulator.note_canvas.itemcget(simulator.balance_item, "text") == "500"
        and simulator.note_canvas.itemcget(simulator.time_item, "text") == "01:30",
        "ransom note dynamic balance/time fields were not initialized",
    )
    check(
        "Roboto Mono" in simulator.note_canvas.itemcget(simulator.balance_item, "font")
        and "Roboto Mono" in simulator.note_canvas.itemcget(simulator.time_item, "font"),
        "ransom note did not use the bundled original-style mono font",
    )
    check(
        all(240 <= record["width"] <= 420 and record["height"] < record["width"] for record in simulator.glitch_windows),
        "glitch popup random horizontal sizing is outside the requested range",
    )
    fixed_images = [record["image"] for record in simulator.glitch_windows]
    simulator._animate_glitch_windows()
    root.update()
    check(fixed_images == [record["image"] for record in simulator.glitch_windows], "a popup changed its chosen image")
    fading_record = simulator.glitch_windows[0]
    fading_record["next_toggle"] = time.monotonic() - 1.0
    for _ in range(16):
        simulator._animate_glitch_windows()
    check(fading_record not in simulator.glitch_windows, "faded popup was not replaced immediately")
    check(
        len(simulator.glitch_windows) == simulator.glitch_window_target,
        "a new popup did not appear immediately after fade-out",
    )
    old_note_position = (simulator.note_window.winfo_x(), simulator.note_window.winfo_y())
    simulator._move_note_window()
    root.update()
    check(
        (simulator.note_window.winfo_x(), simulator.note_window.winfo_y()) != old_note_position,
        "ransom note did not teleport",
    )
    check(simulator.coin_windows, "clickable coin window was not created")

    # Coin input: a passive overlap must not pay, but a user drag and a
    # user-thrown collision must.  A press on its own is intentionally inert.
    coin_id = next(iter(simulator.coin_windows))
    coin_record = simulator.coin_windows[coin_id]
    starting_balance = simulator.balance
    original_coin_position = (float(coin_record["x"]), float(coin_record["y"]))
    note_left = simulator.note_window.winfo_x()
    note_top = simulator.note_window.winfo_y()
    note_right = note_left + simulator.note_window.winfo_width()
    note_bottom = note_top + simulator.note_window.winfo_height()
    coin_size = int(coin_record["size"])
    visual_gap = max(1, simulator.COIN_HITBOX_PADDING // 2)
    if note_left >= coin_size + visual_gap:
        coin_record["x"] = float(note_left - coin_size - visual_gap)
        coin_record["y"] = float(note_top + 10)
    elif note_right + coin_size + visual_gap <= simulator.screen_width:
        coin_record["x"] = float(note_right + visual_gap)
        coin_record["y"] = float(note_top + 10)
    elif note_top >= coin_size + visual_gap:
        coin_record["x"] = float(note_left + 10)
        coin_record["y"] = float(note_top - coin_size - visual_gap)
    else:
        coin_record["x"] = float(note_left + 10)
        coin_record["y"] = float(note_bottom + visual_gap)
    check(
        simulator._coin_hits_note(coin_record),
        "enlarged hitbox did not reach across a visible coin-to-popup gap",
    )
    coin_record["velocity_x"] = 0.0
    coin_record["velocity_y"] = 0.0
    coin_record["moving"] = True
    coin_record["motion_generation"] += 1
    simulator._animate_coin_motion(coin_id, coin_record["motion_generation"])
    check(
        simulator.balance == starting_balance and coin_id in simulator.coin_windows,
        "a naturally overlapping, untouched coin incorrectly counted as payment",
    )
    coin_record["x"], coin_record["y"] = original_coin_position
    coin_record["window"].geometry(
        f"+{round(original_coin_position[0])}+{round(original_coin_position[1])}"
    )

    press = SimpleNamespace(
        x_root=round(original_coin_position[0] + 6),
        y_root=round(original_coin_position[1] + 6),
    )
    simulator._begin_coin_drag(coin_id, press)
    check(simulator.balance == starting_balance, "pressing a coin alone counted as payment")
    drag_into_note = SimpleNamespace(
        x_root=round(note_left + 10 + coin_record["drag_offset_x"]),
        y_root=round(note_top + 10 + coin_record["drag_offset_y"]),
    )
    original_coin_pointer = simulator._coin_pointer_position
    simulator._coin_pointer_position = lambda: (float(drag_into_note.x_root), float(drag_into_note.y_root))
    root.update()
    simulator._coin_pointer_position = original_coin_pointer
    check(
        simulator.balance == starting_balance - simulator.COIN_VALUE
        and coin_id not in simulator.coin_windows,
        "dragging a grabbed coin into the ransom popup did not count",
    )

    if not simulator.coin_windows:
        simulator._spawn_coin()
    thrown_coin_id = next(iter(simulator.coin_windows))
    thrown_record = simulator.coin_windows[thrown_coin_id]
    thrown_start_x = float(thrown_record["x"])
    thrown_start_y = float(thrown_record["y"])
    if thrown_start_x + int(thrown_record["size"]) <= note_left:
        throw_sign = -1.0
    elif thrown_start_x >= note_right:
        throw_sign = 1.0
    else:
        # The coin is vertically outside the note, so either horizontal
        # direction remains safely outside during this release check.
        throw_sign = 1.0 if thrown_start_x < simulator.screen_width / 2 else -1.0
    simulator._begin_coin_drag(
        thrown_coin_id,
        SimpleNamespace(x_root=round(thrown_start_x + 6), y_root=round(thrown_start_y + 6)),
    )
    now = time.monotonic()
    thrown_record["drag_samples"] = [(now - 0.05, thrown_start_x + 6, thrown_start_y + 6)]
    simulator._release_coin(
        thrown_coin_id,
        SimpleNamespace(
            x_root=round(thrown_start_x + 6 + throw_sign * 70),
            y_root=round(thrown_start_y + 6),
        ),
    )
    check(
        thrown_record["moving"] and thrown_record["velocity_x"] * throw_sign > 0,
        "releasing a dragged coin did not throw it in the release direction",
    )
    popup_record = simulator.glitch_windows[0]
    popup_left = float(popup_record["x"])
    popup_top = float(popup_record["y"])
    popup_right = popup_left + float(popup_record["width"])
    popup_height = float(popup_record["height"])
    coin_size = int(thrown_record["size"])
    thrown_record["y"] = popup_top + max(2.0, (popup_height - coin_size) / 2.0)
    thrown_record["velocity_y"] = 0.0
    if popup_left >= coin_size + 2:
        thrown_record["x"] = popup_left - coin_size + 3.0
        thrown_record["velocity_x"] = 14.0
        bounce_x, _ = simulator._bounce_coin_from_glitch(
            thrown_record, float(thrown_record["x"]), float(thrown_record["y"])
        )
        check(
            bounce_x <= popup_left - coin_size
            and thrown_record["velocity_x"] < 0,
            "a thrown coin did not bounce away from the left side of a glitch popup",
        )
    else:
        thrown_record["x"] = popup_right - 3.0
        thrown_record["velocity_x"] = -14.0
        bounce_x, _ = simulator._bounce_coin_from_glitch(
            thrown_record, float(thrown_record["x"]), float(thrown_record["y"])
        )
        check(
            bounce_x >= popup_right
            and thrown_record["velocity_x"] > 0,
            "a thrown coin did not bounce away from the right side of a glitch popup",
        )
    coin_size = int(thrown_record["size"])
    if note_left >= coin_size + 12:
        thrown_record["x"] = float(note_left - coin_size - 8)
        thrown_record["velocity_x"] = 12.0
    else:
        thrown_record["x"] = float(note_left + simulator.note_window.winfo_width() + 8)
        thrown_record["velocity_x"] = -12.0
    thrown_record["y"] = float(note_top + 10)
    thrown_record["velocity_y"] = 0.0
    thrown_record["moving"] = True
    thrown_record["motion_generation"] += 1
    throw_generation = thrown_record["motion_generation"]
    simulator._animate_coin_motion(thrown_coin_id, throw_generation)
    check(
        simulator.balance == starting_balance - simulator.COIN_VALUE * 2
        and thrown_coin_id not in simulator.coin_windows,
        "a user-thrown coin collision with the ransom popup did not count",
    )

    original_note_window = simulator.note_window
    initial_note_size = (original_note_window.winfo_width(), original_note_window.winfo_height())
    original_destroy_shell_overlays_async = simulator._destroy_shell_overlays_async
    black_transition_before_restore: list[bool] = []

    def observe_success_restore_order() -> None:
        black_transition_before_restore.append(
            simulator._window_exists(simulator.note_window)
            and simulator.note_canvas is not None
            and str(simulator.note_canvas.cget("bg")) == "#000000"
        )
        original_destroy_shell_overlays_async()

    simulator._destroy_shell_overlays_async = observe_success_restore_order
    for _ in range(simulator.STARTING_BALANCE // simulator.COIN_VALUE):
        if simulator.stage != "ransom":
            break
        if not simulator.coin_windows:
            simulator._spawn_coin()
        coin_id = next(iter(simulator.coin_windows))
        simulator._collect_coin(coin_id)
        root.update()

    check(simulator.balance == 0, "coin total did not reach zero")
    check(simulator.stage == "success", "successful payment did not open the success stage")
    check(
        simulator.note_window is original_note_window
        and simulator.thank_window is None
        and simulator.thank_phase == "centering",
        "success did not begin by centering the original ransom popup",
    )
    simulator._destroy_shell_overlays_async = original_destroy_shell_overlays_async
    check(
        black_transition_before_restore == [True],
        "ransom note did not turn black before slower Windows restoration",
    )
    transition_deadline = time.monotonic() + 0.9
    while simulator.thank_phase == "centering" and time.monotonic() < transition_deadline:
        root.update()
        time.sleep(0.005)
    check(simulator._window_exists(simulator.thank_window), "THANK YOU was not inserted into the popup")
    check(
        simulator.thank_window is original_note_window
        and simulator.note_window is original_note_window,
        "THANK YOU used a second popup instead of the original ransom popup",
    )
    root.update_idletasks()
    check(
        simulator.thank_phase == "inserted"
        and simulator.thank_window.winfo_width() == initial_note_size[0]
        and simulator.thank_window.winfo_height() == initial_note_size[1]
        and bool(simulator.note_canvas.find_withtag("thank_image")),
        "THANK YOU was not inserted while the centered popup was still its original size",
    )
    check(
        abs(simulator.thank_window.winfo_x() - (simulator.screen_width - simulator.thank_window.winfo_width()) // 2) <= 2
        and abs(simulator.thank_window.winfo_y() - (simulator.screen_height - simulator.thank_window.winfo_height()) // 2) <= 2,
        "original ransom popup was not centered before THANK YOU was inserted",
    )
    if os.name == "nt":
        user32 = ctypes.windll.user32
        child = int(simulator.thank_window.winfo_id())
        hwnd = int(user32.GetParent(child) or child)
        get_style = getattr(user32, "GetWindowLongPtrW", user32.GetWindowLongW)
        ex_style = int(get_style(hwnd, -20))
        check(
            ex_style & 0x08000000
            and ex_style & 0x00000020
            and ex_style & 0x00080000,
            "THANK YOU window is not non-activating and click-through",
        )
    growth_deadline = time.monotonic() + 1.0
    while simulator.thank_phase != "display" and time.monotonic() < growth_deadline:
        root.update()
        time.sleep(0.005)
    root.update_idletasks()
    check(simulator.thank_phase == "display", "THANK YOU popup growth did not complete")
    check(
        simulator.thank_window.winfo_width() > initial_note_size[0]
        and simulator.thank_window.winfo_height() > initial_note_size[1],
        "same THANK YOU popup did not enlarge after the image was inserted",
    )
    check(
        abs(simulator.thank_window.winfo_x() - (simulator.screen_width - simulator.thank_window.winfo_width()) // 2) <= 2
        and abs(simulator.thank_window.winfo_y() - (simulator.screen_height - simulator.thank_window.winfo_height()) // 2) <= 2,
        "enlarged THANK YOU popup did not remain centered",
    )
    check(not simulator._window_exists(simulator.ransom_frame_window), "red-dot border remained after success")
    check(not simulator.glitch_windows, "glitch windows remained after success")
    check(not simulator.coin_windows, "coin windows remained after success")
    check(not simulator.face_flash_windows, "brief face flashes remained after success")
    if simulator.audio.available:
        check(simulator.audio._channels["event"].get_busy(), "supplied OGG success sound did not start")

    simulator._dismiss_thank_window()
    check(not simulator._window_exists(simulator.thank_window), "THANK YOU did not dismiss promptly")
    check(not simulator._window_exists(simulator.note_window), "original ransom popup remained after THANK YOU closed")
    check(simulator.stage == "success", "dismissing THANK YOU ended the success audio stage early")
    if simulator.audio.available:
        check(simulator.audio._channels["event"].get_busy(), "THANK YOU dismissal cut the success sound")

    simulator._finish_terminal_event()
    root.update()
    check(simulator.stage == "idle", "success cleanup did not return to idle")

    # Timer expiry path: all ransom windows close and the final overlay appears.
    simulator.start_ransom_preview()
    root.update()
    simulator.ransom_deadline = time.monotonic() - 0.1
    simulator._update_ransom_clock()
    root.update()
    check(simulator.stage == "failure", "expired timer did not start the failure stage")
    check(simulator._window_exists(simulator.overlay), "failure jumpscare overlay was not created")
    check(not simulator._window_exists(simulator.ransom_frame_window), "red-dot border remained during final jumpscare")
    check(not simulator.glitch_windows, "glitch windows remained after timer expiry")
    simulator._cancel_callbacks()
    simulator._finish_terminal_event()
    root.update()
    check(simulator.stage == "idle", "failure cleanup did not return to idle")
    check(
        simulator._secondary_monitor_red_color() == "#cc0000",
        "secondary-monitor background was not extracted from the supplied image",
    )
    check(
        simulator._monitor_geometry(1920, 1080, -1920, 0) == "1920x1080-1920+0",
        "negative-coordinate secondary monitor geometry is invalid",
    )
    check(
        all(primary or (width > 0 and height > 0) for _x, _y, width, height, primary in simulator._monitor_rectangles()),
        "secondary monitor enumeration returned invalid bounds",
    )
    real_monitor_rectangles = simulator._monitor_rectangles
    simulator._monitor_rectangles = lambda: [
        (0, 0, simulator.screen_width, simulator.screen_height, True),
        (-320, 0, 320, 200, False),
    ]
    simulator.stage = "attack"
    simulator._create_secondary_monitor_overlays()
    root.update()
    check(len(simulator.secondary_monitor_overlays) == 1, "virtual secondary overlay was not created")
    secondary_record = simulator.secondary_monitor_overlays[0]
    check(
        secondary_record["window"].winfo_x() == -320
        and secondary_record["window"].winfo_y() == 0,
        "left-side monitor was placed relative to the primary right edge",
    )
    check(
        str(secondary_record["canvas"].cget("bg")) == "#cc0000",
        "virtual secondary overlay did not use the extracted red background",
    )
    simulator._cancel_callbacks()
    simulator._flash_secondary_monitors(1)
    check(
        str(secondary_record["canvas"].itemcget(secondary_record["item"], "state")) == "hidden",
        "secondary image did not switch to its plain-red flash frame",
    )
    simulator._cancel_callbacks()
    simulator._restore_secondary_monitor_images(1)
    check(
        str(secondary_record["canvas"].itemcget(secondary_record["item"], "state")) == "normal",
        "secondary image did not return after its plain-red flash frame",
    )
    simulator._cancel_callbacks()
    simulator._destroy_secondary_monitor_overlays()
    check(not simulator.secondary_monitor_overlays, "secondary overlay was not removed during cleanup")
    simulator._monitor_rectangles = real_monitor_rectangles
    simulator.stage = "idle"

    # Repeated clean encounters must leave the hidden process armed. This
    # catches callback loss/state leakage that only appears after several runs.
    simulator.repeat_var.set(True)
    simulator.min_wait_var.set("600")
    simulator.max_wait_var.set("600")
    for cycle in range(8):
        simulator._cancel_callbacks()
        simulator._reset_event_windows()
        simulator.armed = True
        simulator.stage = "waiting"
        simulator._show_intro()
        simulator._cancel_callbacks()
        simulator.intro_deadline = time.monotonic() - 0.001
        simulator._center_warning()
        simulator._cancel_callbacks()
        simulator._show_stop()
        simulator._cancel_callbacks()
        simulator._arm_reaction()
        simulator._cancel_callbacks()
        simulator.reaction_failed = False
        simulator._safe_avoid()
        simulator._cancel_callbacks()
        simulator._finish_avoid()
        check(
            simulator.armed and simulator.stage == "waiting",
            f"encounter endurance cycle {cycle + 1} did not remain armed",
        )
    simulator._cancel_callbacks()

    simulator.start_ransom_preview()
    simulator._cancel_callbacks()
    simulator.restore_and_continue()
    check(not simulator._closing, "minus-style restore terminated the application")
    check(
        simulator.armed and simulator.stage == "waiting",
        "minus-style restore did not return to infinite waiting",
    )
    check(not simulator.glitch_windows and not simulator.coin_windows, "restore left encounter windows open")
    simulator._cancel_callbacks()

    simulator.quit_app()
    print("GUI SMOKE TEST OK")
    print("Warning windows: intro / full-screen STOP")
    print(f"Ransom windows: {simulator.glitch_window_target} glitch popups / dynamic note / coin popups")
    print("Payment: 500 -> 0 / THANK YOU cleanup")
    print("Failure: expired timer / jumpscare overlay / cleanup")
    print("Endurance: 8 repeated encounters / still armed")
    print("Restore key: encounter cleaned / application still armed")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
