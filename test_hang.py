import threading
import tkinter as tk
import time

def listener():
    time.sleep(10)

root = tk.Tk()
t = threading.Thread(target=listener, daemon=True)
t.start()

def exit_app():
    root.destroy()

root.after(1000, exit_app)
root.mainloop()
