
import re

with open("doors_ransom.py", "r", encoding="utf-8") as f:
    code = f.read()

# Add cv2 import
code = re.sub(
    r"import time\n",
    "import time\nimport cv2\n",
    code
)

# Add video cap to init
code = re.sub(
    r"self\.thank_phase = .\"\"\n",
    "self.thank_phase = \"\"\n        self.thank_video_cap = None\n",
    code
)

# Modify _animate_thank_growth to play video at end
growth_search = r"(if progress >= 1\.0:\n\s+self\.thank_phase = \"display\"\n\s+)# Only the image is brief; the supplied success sound remains intact\.\n\s+self\._later\(self\.THANK_DISPLAY_MS, self\._dismiss_thank_window\)\n\s+return"
growth_replace = r"""\1try:
                self.thank_video_cap = cv2.VideoCapture(str(ASSET_DIR / "Thank_you_vid.mp4"))
                self._play_thank_video_frame(width, height)
            except Exception as e:
                print("Failed to play video:", e)
                self.quit_app()
            return"""

code = re.sub(growth_search, growth_replace, code)

# Add _play_thank_video_frame method
play_frame_method = """
    def _play_thank_video_frame(self, width: int, height: int) -> None:
        if self.stage != "success" or not self.thank_video_cap:
            return
        ret, frame = self.thank_video_cap.read()
        if ret:
            try:
                frame = cv2.cvtColor(frame, cv2.COLOR_BGR2RGB)
                if frame.shape[1] != width or frame.shape[0] != height:
                    frame = cv2.resize(frame, (width, height))
                img = Image.fromarray(frame)
                self.thank_photo = ImageTk.PhotoImage(image=img)
                if self.thank_image_item is not None and self.note_canvas is not None:
                    self.note_canvas.itemconfigure(self.thank_image_item, image=self.thank_photo)
                fps = self.thank_video_cap.get(cv2.CAP_PROP_FPS)
                delay = int(1000 / fps) if fps > 0 else 33
                self._later(delay, lambda: self._play_thank_video_frame(width, height))
            except Exception as e:
                print("Error playing frame:", e)
                self.thank_video_cap.release()
                self.thank_video_cap = None
                self.quit_app()
        else:
            self.thank_video_cap.release()
            self.thank_video_cap = None
            self.quit_app()
"""

# Insert _play_thank_video_frame before _dismiss_thank_window
code = code.replace("    def _dismiss_thank_window(self) -> None:", play_frame_method.lstrip("\n") + "\n    def _dismiss_thank_window(self) -> None:")

with open("doors_ransom.py", "w", encoding="utf-8") as f:
    f.write(code)

