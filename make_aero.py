from PIL import Image, ImageDraw, ImageFont
import os

width, height = 800, 32

img = Image.new('RGBA', (width, height), (0, 0, 0, 0))
draw = ImageDraw.Draw(img)

# Windows 7 Aero Glass gradient
for y in range(height):
    if y < height // 2:
        # Top half: light translucent blue
        r = int(180 + (220 - 180) * (y / (height / 2)))
        g = int(210 + (240 - 210) * (y / (height / 2)))
        b = int(240 + (255 - 240) * (y / (height / 2)))
        a = 230
    else:
        # Bottom half: darker, more saturated blue
        r = int(100 + (140 - 100) * ((y - height / 2) / (height / 2)))
        g = int(150 + (180 - 150) * ((y - height / 2) / (height / 2)))
        b = int(200 + (220 - 200) * ((y - height / 2) / (height / 2)))
        a = 230
    draw.line([(0, y), (width, y)], fill=(r, g, b, a))

# Add a slight white highlight at the very top
draw.line([(0, 0), (width, 0)], fill=(255, 255, 255, 180))
draw.line([(0, 1), (width, 1)], fill=(255, 255, 255, 100))

# Add a dark border at the bottom
draw.line([(0, height-1), (width, height-1)], fill=(50, 50, 50, 200))

# Draw Close Button (Red)
close_w, close_h = 45, 20
close_x = width - close_w - 6
close_y = 6
# Close button gradient
for y in range(close_y, close_y + close_h):
    if y < close_y + close_h // 2:
        cr, cg, cb = 240, 100, 100
    else:
        cr, cg, cb = 200, 40, 40
    draw.line([(close_x, y), (close_x + close_w, y)], fill=(cr, cg, cb, 255))
# Close button white border
draw.rectangle([close_x, close_y, close_x + close_w, close_y + close_h], outline=(255, 255, 255, 150))
# X symbol
cx = close_x + close_w // 2
cy = close_y + close_h // 2
draw.line([(cx - 4, cy - 4), (cx + 4, cy + 4)], fill=(255, 255, 255, 255), width=2)
draw.line([(cx + 4, cy - 4), (cx - 4, cy + 4)], fill=(255, 255, 255, 255), width=2)

img.save('assets/aero_titlebar.png')
print("Generated assets/aero_titlebar.png")
