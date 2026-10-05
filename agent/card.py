"""Renders an Around Us story card (1080x1350 JPEG) from a story dict.

story = {
  "category": "WORLD" | "INDIA" | "NEAR YOU",
  "kicker": "short label above headline, e.g. 'Space' (optional)",
  "headline": "plain words, <= 70 chars",
  "accent": "one word from the headline to set in italic colour (optional)",
  "points": ["2-3 short lines, <= 90 chars each"],
  "why": "one line: why it matters to people here (optional)",
  "sources": ["The Hindu", "Reuters"],
}
"""
import os
import random
from datetime import datetime, timedelta, timezone
from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONTS = os.path.join(ROOT, "fonts")

PAPER = (244, 241, 234)
INK = (20, 22, 26)
MUTE = (112, 110, 104)
LINE = (210, 205, 195)
WORLD = (47, 85, 212)
INDIA = (232, 119, 46)
NEAR = (217, 67, 59)
SAY = (242, 194, 48)
CAT_COL = {"WORLD": WORLD, "INDIA": INDIA, "NEAR YOU": NEAR, "YOUR SAY": SAY}
W, H, M = 1080, 1350, 88
HANDLE = "@aroundus.daily"
IST = timezone(timedelta(hours=5, minutes=30))


def f(name, size):
    return ImageFont.truetype(os.path.join(FONTS, f"{name}.ttf"), size)


def canvas(bg, seed):
    img = Image.new("RGB", (W, H), bg)
    noise = Image.effect_noise((W, H), 9).convert("L")
    rnd = random.Random(seed)
    alpha = 0.06 + rnd.random() * 0.02
    grain = Image.merge("RGB", [noise] * 3)
    return Image.blend(img, grain, alpha)


def wrap(d, text, ft, width):
    words, lines, cur = text.split(), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if d.textlength(t, font=ft) <= width:
            cur = t
        else:
            if cur:
                lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def logo(d, x, y, ink):
    for r in (21, 14, 7):
        d.ellipse([x - r, y - r, x + r, y + r], outline=ink, width=2)
    d.ellipse([x - 5, y - 5, x + 5, y + 5], fill=NEAR)


def headline_block(d, x, y, text, accent, maxw, ink, accent_col):
    """Big headline; one accent word in italic serif colour. Auto-sizes."""
    for size in (104, 96, 88, 80, 72, 64):
        big = f("bri800", size)
        ser = f("iserif", int(size * 1.1))
        lines = wrap(d, text, big, maxw)
        if len(lines) <= 4:
            break
    lh = int(size * 1.02)
    acc = (accent or "").strip(" .,!?:;").lower()
    for ln in lines:
        cx = x
        for i, word in enumerate(ln.split()):
            core = word.strip(" .,!?:;\"'").lower()
            is_acc = acc and core == acc
            ft = ser if is_acc else big
            col = accent_col if is_acc else ink
            token = word + (" " if i < len(ln.split()) - 1 else "")
            d.text((cx, y + lh), token, font=ft, fill=col, anchor="ls")
            cx += d.textlength(token, font=ft)
        y += lh
    return y


def render(story, path, seed=1):
    cat = story.get("category", "WORLD").upper()
    col = CAT_COL.get(cat, WORLD)
    dark = cat == "NEAR YOU"
    bg = NEAR if dark else PAPER
    ink = PAPER if dark else INK
    sub = (255, 225, 220) if dark else MUTE
    accent_col = INK if dark else col

    im = canvas(bg, seed)
    d = ImageDraw.Draw(im)

    # header
    logo(d, M + 20, 92, ink)
    d.text((M + 54, 70), "around us", font=f("bri800", 38), fill=ink)
    tag_ft = f("int700", 24)
    tw = d.textlength(cat, font=tag_ft)
    tag_bg = INK if dark else col
    tag_fg = PAPER if (dark or col in (WORLD, NEAR)) else INK
    d.rounded_rectangle([W - M - tw - 44, 66, W - M, 116], radius=25, fill=tag_bg)
    d.text((W - M - tw - 22, 77), cat, font=tag_ft, fill=tag_fg)

    y = 190
    if story.get("kicker"):
        d.text((M, y), story["kicker"].upper(), font=f("int700", 26), fill=accent_col)
        y += 50

    y = headline_block(d, M - 4, y, story["headline"], story.get("accent"), W - 2 * M, ink, accent_col)
    y += 50
    d.line([(M, y), (M + 120, y)], fill=ink, width=5)
    y += 46

    pt_ft = f("int500", 36)
    for p in story.get("points", [])[:3]:
        lines = wrap(d, p, pt_ft, W - 2 * M - 44)
        d.ellipse([M, y + 14, M + 14, y + 28], fill=accent_col)
        for ln in lines[:3]:
            d.text((M + 40, y), ln, font=pt_ft, fill=ink)
            y += 50
        y += 18

    why = story.get("why")
    if why and y < H - 330:
        y += 10
        why_ft = f("iserif", 40)
        for ln in wrap(d, "Why it matters: " + why, why_ft, W - 2 * M)[:3]:
            d.text((M, y), ln, font=why_ft, fill=sub)
            y += 48

    # footer
    d.line([(M, H - 150), (W - M, H - 150)], fill=(255, 190, 182) if dark else LINE, width=2)
    src = ", ".join(story.get("sources", [])[:3])
    if src:
        d.text((M, H - 132), "Source: " + src, font=f("int500", 24), fill=sub)
    d.text((M, H - 88), HANDLE, font=f("int600", 28), fill=ink)
    date = datetime.now(IST).strftime("%d %b %Y")
    df = f("iserif", 34)
    d.text((W - M - d.textlength(date, font=df), H - 92), date, font=df, fill=sub)

    im.save(path, quality=92)
    return path


if __name__ == "__main__":
    render({
        "category": "WORLD", "kicker": "Space",
        "headline": "Europe's new rocket puts its first weather satellite in orbit",
        "accent": "weather",
        "points": ["The launch from French Guiana went to plan on Sunday.",
                   "The satellite will track storms over the Indian Ocean too.",
                   "Better forecasts mean earlier cyclone warnings for the AP coast."],
        "why": "farmers and fishermen get more warning before bad weather.",
        "sources": ["Reuters", "BBC"],
    }, "/tmp/test_world.jpg")
    render({
        "category": "NEAR YOU", "kicker": "Giddalur",
        "headline": "Drain overflowing near the bus stand for four days",
        "accent": "four",
        "points": ["Residents say the water has not cleared since Thursday.",
                   "Shops nearby say customers are avoiding the stretch."],
        "why": "standing water brings mosquitoes and dengue risk.",
        "sources": ["Reader report (unverified)"],
    }, "/tmp/test_near.jpg", seed=2)
    print("ok")
