"""Check live note text at different display scales and small work areas."""

import argparse
import tkinter as tk
import tkinter.font as tkfont

from doors_ransom import RansomSimulator


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--preview", action="store_true")
    args = parser.parse_args()
    root = tk.Tk()
    root.withdraw()
    app = RansomSimulator(root, enable_shell_effects=False, use_saved_settings=False)
    app.audio.set_volume(0)
    real_work_area = app._primary_work_area
    try:
        for scaling in (1.0, 4 / 3, 2.0, 8 / 3):
            root.tk.call("tk", "scaling", scaling)
            for area in ((0, 0, 1920, 1040), (0, 0, 800, 560)):
                app._primary_work_area = lambda value=area: value
                app._fit_note_to_screen()
                app.stage = "ransom"
                app._create_note_window()
                app._cancel_callbacks()
                root.update_idletasks()
                canvas = app.note_canvas
                for item in canvas.find_all():
                    if canvas.type(item) != "text":
                        continue
                    label = canvas.itemcget(item, "text")
                    left, top, right, bottom = canvas.bbox(item)
                    assert 0 <= left < right <= app.NOTE_WIDTH, (scaling, area, label, canvas.bbox(item))
                    assert 0 <= top < bottom <= app.NOTE_HEIGHT, (scaling, area, label, canvas.bbox(item))
                    family = tkfont.Font(root=root, font=canvas.itemcget(item, "font")).actual("family")
                    assert "Roboto Mono" in family, (label, family)
                    if label == "TIME:":
                        assert right + 2 < canvas.bbox(app.time_item)[0], "TIME label overlaps countdown"
                    if "UNRECOVERABLE" in label:
                        assert top >= round(99 * app.note_scale * 3), "notice overlaps header"
                        assert bottom <= round(144 * app.note_scale * 3), "notice overlaps counter"
                assert app.NOTE_WIDTH + 24 <= area[2] - area[0]
                assert app.NOTE_HEIGHT + 48 <= area[3] - area[1]
                app._destroy_ransom_windows()
        print("NOTE LAYOUT OK: 4 display scales x 2 work areas; bundled font resolved; text fits")
        if args.preview:
            app._primary_work_area = real_work_area
            app._fit_note_to_screen()
            app.stage = "ransom"
            app._create_note_window()
            app._cancel_callbacks()
            root.after(60000, app.quit_app)
            root.mainloop()
        return 0
    finally:
        app.quit_app()


if __name__ == "__main__":
    raise SystemExit(main())
