"""Around Us daily carousel slides (1080x1350 JPEG each).

Slides:
  world(items, fx)        India in the world + rupee vs top economies
  markets(rows)           top 10 stock exchanges (weekdays)
  digest(kind, title, items)   India top 10 / South India / Andhra / Near you
"""
import os
from datetime import datetime, timedelta, timezone
from PIL import Image, ImageDraw, ImageFont

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
FONTS = os.path.join(ROOT, "fonts")
IST = timezone(timedelta(hours=5, minutes=30))

PAPER = (244, 241, 234)
INK = (20, 22, 26)
INK2 = (34, 37, 43)
MUTE = (112, 110, 104)
LINE = (210, 205, 195)
UP = (34, 150, 90)
DOWN = (210, 60, 50)
NEAR = (217, 67, 59)

THEMES = {  # tag colour, background, text, sub text, rule
    "WORLD": dict(tag=(47, 85, 212), bg=PAPER, ink=INK, sub=MUTE, rule=LINE),
    "RUPEE": dict(tag=(20, 135, 115), bg=PAPER, ink=INK, sub=MUTE, rule=LINE),
    "MARKETS": dict(tag=(242, 194, 48), bg=INK, ink=PAPER, sub=(160, 160, 155), rule=(60, 63, 70)),
    "INDIA": dict(tag=(232, 119, 46), bg=PAPER, ink=INK, sub=MUTE, rule=LINE),
    "SOUTH INDIA": dict(tag=(20, 135, 115), bg=PAPER, ink=INK, sub=MUTE, rule=LINE),
    "ANDHRA PRADESH": dict(tag=(128, 72, 160), bg=PAPER, ink=INK, sub=MUTE, rule=LINE),
    "NEAR YOU": dict(tag=INK, bg=NEAR, ink=PAPER, sub=(255, 225, 220), rule=(240, 150, 140)),
}
W, H, M = 1080, 1350, 80
HANDLE = "@aroundus.daily"


def f(name, size):
    return ImageFont.truetype(os.path.join(FONTS, f"{name}.ttf"), size)


def has_glyph(font, ch):
    """True if the font really contains ch (not the empty 'tofu' box)."""
    try:
        return font.getmask(ch).getbbox() != font.getmask("\uffff").getbbox()
    except Exception:
        return False


def rupee_sign(font):
    return "₹" if has_glyph(font, "₹") else "Rs "


def date_label(iso):
    try:
        return datetime.strptime(iso[:10], "%Y-%m-%d").strftime("%-d %b")
    except Exception:
        return ""


def wrap(d, text, ft, width):
    words, lines, cur = text.split(), [], ""
    for w in words:
        t = (cur + " " + w).strip()
        if d.textlength(t, font=ft) <= width or not cur:
            cur = t
        else:
            lines.append(cur)
            cur = w
    if cur:
        lines.append(cur)
    return lines


def base(kind, title, accent=None, subtitle=None):
    th = THEMES[kind]
    im = Image.new("RGB", (W, H), th["bg"])
    noise = Image.effect_noise((W, H), 9).convert("L")
    im = Image.blend(im, Image.merge("RGB", [noise] * 3), 0.05)
    d = ImageDraw.Draw(im)
    # logo + wordmark
    x, y = M + 20, 86
    for r in (21, 14, 7):
        d.ellipse([x - r, y - r, x + r, y + r], outline=th["ink"], width=2)
    d.ellipse([x - 5, y - 5, x + 5, y + 5], fill=NEAR if kind != "NEAR YOU" else INK)
    d.text((M + 54, 64), "around us", font=f("bri800", 36), fill=th["ink"])
    # tag pill
    tf = f("int700", 23)
    tw = d.textlength(kind, font=tf)
    tag_fg = INK if kind == "MARKETS" else PAPER
    d.rounded_rectangle([W - M - tw - 44, 62, W - M, 110], radius=24, fill=th["tag"])
    d.text((W - M - tw - 22, 72), kind, font=tf, fill=tag_fg)
    # title, with optional italic accent word
    big, ser = f("bri800", 84), f("iserif", 94)
    cx, ty = M - 3, 228
    for i, word in enumerate(title.split()):
        is_acc = accent and word.lower().strip(".,") == accent.lower()
        ft = ser if is_acc else big
        col = (INK if kind == "NEAR YOU" else th["tag"]) if is_acc else th["ink"]
        tok = word + " "
        d.text((cx, ty), tok, font=ft, fill=col, anchor="ls")
        cx += d.textlength(tok, font=ft)
    y = ty + 26
    if subtitle:
        d.text((M, y), subtitle, font=f("int500", 28), fill=th["sub"])
        y += 46
    d.line([(M, y + 8), (W - M, y + 8)], fill=th["rule"], width=2)
    return im, d, th, y + 34


def footer(d, th, page=None, note=None):
    d.line([(M, H - 120), (W - M, H - 120)], fill=th["rule"], width=2)
    if note:
        d.text((M, H - 160), note, font=f("int500", 22), fill=th["sub"])
    d.text((M, H - 92), HANDLE, font=f("int600", 28), fill=th["ink"])
    date = datetime.now(IST).strftime("%d %b %Y")
    right = date + (f"   {page}" if page else "")
    df = f("iserif", 34)
    d.text((W - M - d.textlength(right, font=df), H - 96), right, font=df, fill=th["sub"])


def list_block(d, th, items, y0, y1, numbered=True):
    """Draw items between y0 and y1, shrinking type until everything fits.
    Each item: text, optional tag (state/town) and src (outlet) shown small above it."""
    acc = th["tag"] if th["bg"] != NEAR else INK
    for size in (34, 32, 30, 28, 27, 26, 25, 24, 23, 22):
        ft, tf = f("int500", size), f("int600", max(16, int(size * 0.58)))
        lh, gap = int(size * 1.24), int(size * 0.5)
        num_w = int(size * 1.55) if numbered else int(size * 0.95)
        width = W - 2 * M - num_w
        plan, h = [], 0
        for it in items:
            lines = wrap(d, it["text"], ft, width)[:4]
            meta = " · ".join(x for x in (it.get("tag", ""), it.get("src", ""), date_label(it.get("date", ""))) if x).upper()
            mh = int(size * 0.78) if meta else 0
            plan.append((lines, meta, mh))
            h += mh + len(lines) * lh + gap
        if y0 + h <= y1:
            break
    y = y0
    for n, (lines, meta, mh) in enumerate(plan, 1):
        x = M + num_w
        if numbered:
            d.text((M, y + mh + lh - int(size * 0.3)), f"{n:02d}", font=f("bri800", size), fill=acc, anchor="ls")
        else:
            cy = y + mh + lh / 2 - 2
            d.ellipse([M + 2, cy - size * 0.17, M + 2 + size * 0.34, cy + size * 0.17], fill=acc)
        if meta:
            d.text((x, y), meta, font=tf, fill=th["sub"])
            y += mh
        for ln in lines:
            d.text((x, y), ln, font=ft, fill=th["ink"])
            y += lh
        y += gap
    return y


# ---------------------------------------------------------------- slides
def world(items, fx, path, page=None, fx_note=""):
    im, d, th, y = base("WORLD", "India in the world", accent="world")
    fx_h = 300 if fx else 0
    list_block(d, th, items[:6], y, H - 170 - fx_h, numbered=False)
    if fx:
        top = H - 150 - fx_h
        d.text((M, top), "RUPEE TODAY  ·  ₹ for 1 unit", font=f("int700", 24), fill=th["tag"])
        if fx_note:
            nf = f("int500", 19)
            d.text((W - M - d.textlength(fx_note, font=nf), top + 4), fx_note, font=nf, fill=th["sub"])
        n = len(fx)
        gap = 16
        tw = (W - 2 * M - gap * (n - 1)) / n
        for i, c in enumerate(fx):
            x0 = M + i * (tw + gap)
            d.rounded_rectangle([x0, top + 48, x0 + tw, top + 250], radius=18, fill=(232, 228, 219))
            d.text((x0 + tw / 2, top + 92), c["code"], font=f("int700", 28), fill=INK, anchor="mm")
            d.text((x0 + tw / 2, top + 140), c["country"], font=f("int500", 19), fill=MUTE, anchor="mm")
            num = f"{c['inr']:.2f}" if c["inr"] < 1000 else f"{c['inr']:.0f}"
            rf, nf = f("int700", 30), f("bri800", 38)
            total = d.textlength("₹", font=rf) + d.textlength(num, font=nf)
            sx = x0 + (tw - total) / 2
            d.text((sx, top + 205), "₹", font=rf, fill=INK, anchor="ls")
            d.text((sx + d.textlength("₹", font=rf), top + 205), num, font=nf, fill=INK, anchor="ls")
            ch = c.get("change")
            if ch is not None:
                col = DOWN if ch > 0 else UP  # rupee weaker when the price of a foreign unit rises
                arrow(d, x0 + tw / 2 - 40, top + 228, ch >= 0, col, 9)
                d.text((x0 + tw / 2 - 26, top + 228), f"{abs(ch):.2f}%", font=f("int600", 20), fill=col, anchor="lm")
    footer(d, th, page)
    im.save(path, quality=92)


def arrow(d, x, y, up, col, s):
    pts = [(x, y + s * 0.6), (x + s, y + s * 0.6), (x + s / 2, y - s * 0.6)] if up else \
          [(x, y - s * 0.6), (x + s, y - s * 0.6), (x + s / 2, y + s * 0.6)]
    d.polygon(pts, fill=col)


def rupee(rows, path, page=None, note=""):
    im, d, th, y = base("RUPEE", "Rupee today", accent="Rupee",
                        subtitle="How many rupees for 1 unit of each currency")
    # header row
    cols = (M, W - M - 330, W - M)  # currency | rupees | change
    d.text((cols[0], y), "CURRENCY", font=f("int700", 20), fill=th["sub"])
    hf = f("int700", 20)
    d.text((cols[1], y), rupee_sign(hf).strip() + " FOR 1", font=hf, fill=th["sub"], anchor="ra")
    d.text((cols[2], y), "VS YESTERDAY", font=f("int700", 20), fill=th["sub"], anchor="ra")
    y += 40
    rh = min(104, (H - 230 - y) / max(len(rows), 1))
    symbols = {"USD": "$", "EUR": "€", "GBP": "£", "JPY": "¥", "CNY": "CN¥", "CAD": "C$", "SGD": "S$", "AED": "AED"}
    colours = {"USD": (47, 85, 212), "EUR": (20, 135, 115), "GBP": (128, 72, 160), "JPY": (217, 67, 59),
               "CNY": (196, 54, 40), "CAD": (210, 60, 50), "SGD": (232, 119, 46), "AED": (34, 120, 80)}
    for i, r in enumerate(rows):
        yy = y + i * rh
        if i % 2 == 0:
            d.rounded_rectangle([M - 16, yy, W - M + 16, yy + rh - 6], radius=14, fill=(233, 229, 220))
        cy = yy + (rh - 6) / 2
        # symbol badge
        bx, br = cols[0] + 30, 30
        d.ellipse([bx - br, cy - br, bx + br, cy + br], fill=colours.get(r["code"], INK))
        sym = symbols.get(r["code"], r["code"][:1])
        sf = f("int700", 30 if len(sym) == 1 else 20 if len(sym) == 2 else 15)
        d.text((bx, cy + 1), sym, font=sf, fill=PAPER, anchor="mm")
        tx = cols[0] + 78
        d.text((tx, cy - 14), r["code"], font=f("int700", 34), fill=INK, anchor="lm")
        d.text((tx, cy + 22), r["country"], font=f("int500", 22), fill=MUTE, anchor="lm")
        num = f"{r['inr']:.2f}"
        nf, rf = f("bri800", 44), f("int700", 34)
        rs = rupee_sign(rf)
        d.text((cols[1], cy), num, font=nf, fill=INK, anchor="rm")
        d.text((cols[1] - d.textlength(num, font=nf) - 4, cy + 2), rs, font=rf, fill=INK, anchor="rm")
        ch = r.get("change")
        if ch is None:
            d.text((cols[2], cy), "–", font=f("int600", 30), fill=MUTE, anchor="rm")
        else:
            # rupee price of a foreign unit going UP means the rupee got weaker
            col = DOWN if ch > 0.005 else UP if ch < -0.005 else MUTE
            txt = f"{abs(ch):.2f}%"
            tw = d.textlength(txt, font=f("int700", 28))
            d.text((cols[2], cy), txt, font=f("int700", 28), fill=col, anchor="rm")
            if col != MUTE:
                arrow(d, cols[2] - tw - 26, cy, ch > 0, col, 16)
    d.text((M, H - 196), "Red = rupee weaker than yesterday · Green = rupee stronger",
           font=f("int500", 22), fill=th["sub"])
    footer(d, th, page, note=note)
    im.save(path, quality=92)


def markets(rows, path, page=None, note=None):
    im, d, th, y = base("MARKETS", "Markets at close", accent="close",
                        subtitle="Top 10 stock exchanges · main index · day change")
    rh = (H - 200 - y) / max(len(rows), 1)
    rh = min(rh, 92)
    for i, r in enumerate(rows):
        yy = y + i * rh
        if i % 2 == 0:
            d.rounded_rectangle([M - 16, yy, W - M + 16, yy + rh - 8], radius=14, fill=INK2)
        cy = yy + (rh - 8) / 2
        d.text((M + 4, cy - 13), r["exchange"], font=f("int600", 30), fill=PAPER, anchor="lm")
        d.text((M + 4, cy + 20), r["index"], font=f("int500", 21), fill=th["sub"], anchor="lm")
        if r.get("value") is None:
            d.text((W - M, cy), "no data", font=f("int500", 26), fill=th["sub"], anchor="rm")
            continue
        val = f"{r['value']:,.0f}" if r["value"] >= 1000 else f"{r['value']:,.2f}"
        d.text((W - M - 190, cy), val, font=f("bri700", 34), fill=PAPER, anchor="rm")
        ch = r.get("change")
        if ch is not None:
            col = UP if ch >= 0 else DOWN
            d.rounded_rectangle([W - M - 160, cy - 22, W - M, cy + 22], radius=10, fill=col)
            arrow(d, W - M - 146, cy, ch >= 0, PAPER, 14)
            d.text((W - M - 14, cy), f"{abs(ch):.2f}%", font=f("int700", 26), fill=PAPER, anchor="rm")
    footer(d, th, page, note=note or "Last close, source: Yahoo Finance. For information only, not investment advice.")
    im.save(path, quality=92)


def digest(kind, title, accent, items, path, page=None, subtitle=None, note=None):
    im, d, th, y = base(kind, title, accent=accent, subtitle=subtitle)
    list_block(d, th, items, y, H - 180, numbered=(kind == "INDIA"))
    footer(d, th, page, note=note)
    im.save(path, quality=92)
