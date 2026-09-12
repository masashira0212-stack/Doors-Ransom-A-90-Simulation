
import re

with open("doors_ransom.py", "r", encoding="utf-8") as f:
    code = f.read()

drag_search = """    def _make_draggable(self, window, widget) -> None:
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

drag_replace = """    def _make_draggable(self, window, widget) -> None:
        def on_press(event):
            window._drag_start_x = event.x_root
            window._drag_start_y = event.y_root
            window._drag_start_win_x = window.winfo_x()
            window._drag_start_win_y = window.winfo_y()
            window._is_dragging = True
            self.ransom_stack_repair_deferred = True
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
        def on_release(event):
            window._is_dragging = False
        widget.bind("<ButtonPress-1>", on_press, add="+")
        widget.bind("<B1-Motion>", on_drag, add="+")
        widget.bind("<ButtonRelease-1>", on_release, add="+")"""
code = code.replace(drag_search, drag_replace)

jitter_search = """        self.note_jitter_tick += 1
        left, top, right, bottom = self._primary_work_area()"""
jitter_replace = """        self.note_jitter_tick += 1
        if getattr(self.note_window, "_is_dragging", False):
            self._later(16, self._animate_note_jitter)
            return
        left, top, right, bottom = self._primary_work_area()"""
code = code.replace(jitter_search, jitter_replace)

repair_search = """        if self._has_active_coin_drag():
            self.ransom_stack_repair_deferred = True
            return"""
repair_replace = """        controls = [r.get("window") for r in self.glitch_windows] + [self.note_window]
        if self._has_active_coin_drag() or any(getattr(w, "_is_dragging", False) for w in controls if w is not None):
            self.ransom_stack_repair_deferred = True
            return"""
code = code.replace(repair_search, repair_replace)

# We need to remove the "controls = ..." assignment later in _repair_ransom_visibility since we moved it up.
# Wait, it is:
#        try:
#            controls = [r["window"] for r in self.glitch_windows]
#            controls += [self.note_window]
# Let us replace that too so it doesn"t redefine it.
redef_search = """        try:
            controls = [r["window"] for r in self.glitch_windows]
            controls += [self.note_window]"""
redef_replace = """        try:"""
code = code.replace(redef_search, redef_replace)

with open("doors_ransom.py", "w", encoding="utf-8") as f:
    f.write(code)

