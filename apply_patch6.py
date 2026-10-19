
import re

with open("doors_ransom.py", "r", encoding="utf-8") as f:
    code = f.read()

bad_drag = """    def _make_draggable(self, window, widget) -> None:
        def on_press(event):
            window._drag_start_x = event.x
            window._drag_start_y = event.y
        def on_drag(event):
            x = window.winfo_x() - getattr(window, "_drag_start_x", 0) + event.x
            y = window.winfo_y() - getattr(window, "_drag_start_y", 0) + event.y
            try:
                window.geometry(f"+{x}+{y}")
            except Exception:
                pass
            if getattr(self, "note_window", None) is window:
                self.note_base_x = x
                self.note_base_y = y
        widget.bind("<ButtonPress-1>", on_press, add="+")
        widget.bind("<B1-Motion>", on_drag, add="+")"""

good_drag = """    def _make_draggable(self, window, widget) -> None:
        def on_press(event):
            window._drag_start_x = event.x_root
            window._drag_start_y = event.y_root
            window._drag_start_win_x = window.winfo_x()
            window._drag_start_win_y = window.winfo_y()
        def on_drag(event):
            dx = event.x_root - getattr(window, "_drag_start_x", event.x_root)
            dy = event.y_root - getattr(window, "_drag_start_y", event.y_root)
            x = getattr(window, "_drag_start_win_x", window.winfo_x()) + dx
            y = getattr(window, "_drag_start_win_y", window.winfo_y()) + dy
            try:
                window.geometry(f"+{x}+{y}")
            except Exception:
                pass
            if getattr(self, "note_window", None) is window:
                self.note_base_x = x
                self.note_base_y = y
        widget.bind("<ButtonPress-1>", on_press, add="+")
        widget.bind("<B1-Motion>", on_drag, add="+")"""

if bad_drag in code:
    code = code.replace(bad_drag, good_drag)
else:
    print("Could not find bad_drag in doors_ransom.py")

with open("doors_ransom.py", "w", encoding="utf-8") as f:
    f.write(code)

