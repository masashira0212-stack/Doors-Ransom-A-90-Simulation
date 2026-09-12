import tkinter as tk

root = tk.Tk()
root.geometry("800x600")

def start_pop():
    win = tk.Toplevel(root)
    win.overrideredirect(True)
    win.config(bg="red")
    
    final_w, final_h = 400, 300
    final_x, final_y = 200, 150
    
    steps = [
        (0.2, 0.2), # Start very small
        (0.5, 0.5), # Grow
        (1.1, 1.1), # Overshoot (shock)
        (0.9, 0.9), # Bounce back
        (1.0, 1.0)  # Settle
    ]
    
    def animate(step_idx=0):
        if step_idx >= len(steps):
            return
        scale_w, scale_h = steps[step_idx]
        w = int(final_w * scale_w)
        h = int(final_h * scale_h)
        x = int(final_x + (final_w - w) / 2)
        y = int(final_y + (final_h - h) / 2)
        
        win.geometry(f"{w}x{h}+{x}+{y}")
        root.after(30, animate, step_idx + 1)
        
    animate()

root.after(1000, start_pop)
root.mainloop()
