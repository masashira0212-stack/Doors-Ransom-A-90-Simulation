import tkinter as tk

root = tk.Tk()
width, bar_height = 800, 30
titlebar = tk.Canvas(root, width=width, height=bar_height, highlightthickness=0)
titlebar.pack()

for y in range(bar_height):
    if y < bar_height // 2:
        r = int(180 + (220 - 180) * (y / (bar_height / 2)))
        g = int(210 + (240 - 210) * (y / (bar_height / 2)))
        b = int(240 + (255 - 240) * (y / (bar_height / 2)))
    else:
        r = int(100 + (140 - 100) * ((y - bar_height / 2) / (bar_height / 2)))
        g = int(150 + (180 - 150) * ((y - bar_height / 2) / (bar_height / 2)))
        b = int(200 + (220 - 200) * ((y - bar_height / 2) / (bar_height / 2)))
    color = f"#{r:02x}{g:02x}{b:02x}"
    titlebar.create_line(0, y, width, y, fill=color)

titlebar.create_line(0, 0, width, 0, fill="#ffffff")
font = ("Segoe UI", 10, "bold")
titlebar.create_text(11, bar_height//2 + 1, text="RANSOM", fill="#333333", font=font, anchor="w")
titlebar.create_text(10, bar_height//2, text="RANSOM", fill="#ffffff", font=font, anchor="w")

close_w, close_h = 45, 18
close_x = width - close_w - 6
close_y = 6
for y in range(close_y, close_y + close_h):
    color = "#e06060" if y < close_y + close_h // 2 else "#c03030"
    titlebar.create_line(close_x, y, close_x + close_w, y, fill=color)
titlebar.create_rectangle(close_x, close_y, close_x + close_w, close_y + close_h, outline="#ffffff")
cx, cy = close_x + close_w // 2, close_y + close_h // 2
titlebar.create_line(cx - 3, cy - 3, cx + 4, cy + 4, fill="white", width=2)
titlebar.create_line(cx + 3, cy - 3, cx - 4, cy + 4, fill="white", width=2)

root.after(2000, root.destroy)
root.mainloop()
