
import re

with open("doors_ransom.py", "r", encoding="utf-8") as f:
    code = f.read()

old_force = """    def _force_complete(self, event=None) -> None:
        if self.stage == "ransom":
            self.app_held_inputs.clear()
            self._ransom_success()"""

new_force = """    def _force_complete(self, event=None) -> None:
        if self.stage in ("ransom", "waiting"):
            self.app_held_inputs.clear()
            self._cancel_callbacks()
            self._ransom_success()"""

code = code.replace(old_force, new_force)

code = code.replace(
    "    def _ransom_success(self) -> None:\n        if self.stage != \"ransom\":\n            return",
    "    def _ransom_success(self) -> None:\n        if self.stage not in (\"ransom\", \"waiting\"):\n            return"
)

with open("doors_ransom.py", "w", encoding="utf-8") as f:
    f.write(code)

