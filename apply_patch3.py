
import re

with open("doors_ransom.py", "r", encoding="utf-8") as f:
    code = f.read()

force_method = """
    def _force_complete(self, event=None) -> None:
        if self.stage == "ransom":
            self.app_held_inputs.clear()
            self._ransom_success()
"""
code = code.replace("    def _ransom_success(self) -> None:", force_method.lstrip("\n") + "\n    def _ransom_success(self) -> None:")

bind_replace = """        self.root.bind_all("<MouseWheel>", self._on_pointer_press, add="+")
        self.root.bind_all("<grave>", self._force_complete, add="+")"""
code = code.replace("        self.root.bind_all(\"<MouseWheel>\", self._on_pointer_press, add=\"+\")", bind_replace)

begin_growth_search = r"""        canvas\.delete\("all"\)
        self\.thank_photo = self\._new_pixel_photo\("thank_you\.png", \(start_width, start_height\)\)"""

begin_growth_replace = r"""        canvas.delete("all")
        try:
            self.thank_video_cap = cv2.VideoCapture(str(ASSET_DIR / "Thank_you_vid.mp4"))
            ret, frame = self.thank_video_cap.read()
            if ret:
                frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                if frame.shape[1] != start_width or frame.shape[0] != start_height:
                    frame = cv2.resize(frame, (start_width, start_height))
                img = Image.fromarray(frame)
                self.thank_photo = ImageTk.PhotoImage(image=img)
            else:
                self.thank_photo = self._new_pixel_photo("thank_you.png", (start_width, start_height))
        except Exception:
            self.thank_photo = self._new_pixel_photo("thank_you.png", (start_width, start_height))"""
code = re.sub(begin_growth_search, begin_growth_replace, code)

animate_growth_search = r"""            window\.geometry\(f"\{width\}x\{height\}\+\{x\}\+\{y\}"\)
            self\.note_canvas\.configure\(width=width, height=height\)
            self\.thank_photo = self\._new_pixel_photo\("thank_you\.png", \(width, height\)\)
            if self\.thank_image_item is not None:
                self\.note_canvas\.coords\(self\.thank_image_item, width // 2, height // 2\)
                self\.note_canvas\.itemconfigure\(self\.thank_image_item, image=self\.thank_photo\)"""

animate_growth_replace = r"""            window.geometry(f"{width}x{height}+{x}+{y}")
            self.note_canvas.configure(width=width, height=height)
            try:
                ret, frame = self.thank_video_cap.read()
                if ret:
                    frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                    if frame.shape[1] != width or frame.shape[0] != height:
                        frame = cv2.resize(frame, (width, height))
                    img = Image.fromarray(frame)
                    self.thank_photo = ImageTk.PhotoImage(image=img)
                else:
                    self.thank_photo = self._new_pixel_photo("thank_you.png", (width, height))
            except Exception:
                self.thank_photo = self._new_pixel_photo("thank_you.png", (width, height))
            if self.thank_image_item is not None:
                self.note_canvas.coords(self.thank_image_item, width // 2, height // 2)
                self.note_canvas.itemconfigure(self.thank_image_item, image=self.thank_photo)"""
code = re.sub(animate_growth_search, animate_growth_replace, code)

finish_growth_search = r"""        if progress >= 1\.0:
            self\.thank_phase = "display"
            try:
                self\.thank_video_cap = cv2\.VideoCapture\(str\(ASSET_DIR / "Thank_you_vid\.mp4"\)\)
                self\._play_thank_video_frame\(width, height\)
            except Exception as e:
                print\("Failed to play video:", e\)
                self\.quit_app\(\)
            return"""

finish_growth_replace = r"""        if progress >= 1.0:
            self.thank_phase = "display"
            if getattr(self, "thank_video_cap", None) is not None:
                self._play_thank_video_frame(width, height)
            else:
                self.quit_app()
            return"""
code = re.sub(finish_growth_search, finish_growth_replace, code)

with open("doors_ransom.py", "w", encoding="utf-8") as f:
    f.write(code)

