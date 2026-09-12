
import re

with open("doors_ransom.py", "r", encoding="utf-8") as f:
    code = f.read()

draggable_method = """    def _make_draggable(self, window, widget) -> None:
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
        widget.bind("<B1-Motion>", on_drag, add="+")
"""

# Insert _make_draggable before _create_note_window
code = code.replace("    def _create_note_window(self) -> None:", draggable_method + "\n    def _create_note_window(self) -> None:")

# Add _make_draggable to _create_note_window
note_search = """        self.note_canvas = canvas
        canvas.pack(fill="both", expand=True)"""
note_replace = """        self.note_canvas = canvas
        canvas.pack(fill="both", expand=True)
        self._make_draggable(window, canvas)"""
code = code.replace(note_search, note_replace)

# Add _make_draggable to _create_glitch_window
glitch_search = """        label.pack(fill="both", expand=True)
        record: dict[str, Any] = {"""
glitch_replace = """        label.pack(fill="both", expand=True)
        self._make_draggable(window, label)
        record: dict[str, Any] = {"""
code = code.replace(glitch_search, glitch_replace)

with open("doors_ransom.py", "w", encoding="utf-8") as f:
    f.write(code)

