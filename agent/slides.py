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
    "GOLD RATE": dict(tag=(222, 178, 76), bg=(24, 21, 17), ink=PAPER, sub=(172, 162, 142), rule=(72, 63, 50)),
    "SILVER RATE": dict(tag=(196, 204, 214), bg=(22, 25, 30), ink=PAPER, sub=(150, 158, 170), rule=(62, 68, 78)),
    "NEAR YOU": dict(tag=INK, bg=NEAR, ink=PAPER, sub=(255, 225, 220), rule=(240, 150, 140)),
}
W, H, M = 1080, 1350, 56
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
    tag_fg = INK if kind in ("MARKETS", "GOLD RATE", "SILVER RATE") else PAPER
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
    """Slim one-line footer."""
    if note:
        d.text((M, H - 104), note, font=f("int500", 19), fill=th["sub"])
    d.line([(M, H - 72), (W - M, H - 72)], fill=th["rule"], width=1)
    d.text((M, H - 54), HANDLE, font=f("int600", 24), fill=th["ink"])
    date = datetime.now(IST).strftime("%d %b %Y")
    right = date + (f"   {page}" if page else "")
    df = f("iserif", 28)
    d.text((W - M - d.textlength(right, font=df), H - 58), right, font=df, fill=th["sub"])


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
    rh = min(108, (H - 160 - y) / max(len(rows), 1))
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
    d.text((M, H - 132), "Red = rupee weaker than yesterday · Green = rupee stronger",
           font=f("int500", 22), fill=th["sub"])
    footer(d, th, page, note=note)
    im.save(path, quality=92)


def markets(rows, path, page=None, note=None):
    im, d, th, y = base("MARKETS", "Markets at close", accent="close",
                        subtitle="Top 10 stock exchanges · main index · day change")
    rh = (H - 140 - y) / max(len(rows), 1)
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
    list_block(d, th, items, y, H - (128 if note else 92), numbered=(kind == "INDIA"))
    footer(d, th, page, note=note)
    im.save(path, quality=92)


def nifty(data, path):
    """Nifty 50 index + all 50 stocks (sorted by 1-day change): price, 1D / 1W / 1M / 1Y %."""
    th = {"tag": (242, 194, 48), "bg": INK, "ink": PAPER, "sub": (165, 165, 160), "rule": (60, 63, 70)}
    im = Image.new("RGB", (W, H), th["bg"])
    noise = Image.effect_noise((W, H), 9).convert("L")
    im = Image.blend(im, Image.merge("RGB", [noise] * 3), 0.04)
    d = ImageDraw.Draw(im)
    L = 40  # tighter side margin for this dense post
    # header
    x, y0 = L + 18, 58
    for r in (19, 12, 6):
        d.ellipse([x - r, y0 - r, x + r, y0 + r], outline=PAPER, width=2)
    d.ellipse([x - 4, y0 - 4, x + 4, y0 + 4], fill=NEAR)
    d.text((L + 48, 38), "around us", font=f("bri800", 32), fill=PAPER)
    tag, tf = "NIFTY 50", f("int700", 21)
    tw = d.textlength(tag, font=tf)
    d.rounded_rectangle([W - L - tw - 40, 36, W - L, 80], radius=22, fill=th["tag"])
    d.text((W - L - tw - 20, 45), tag, font=tf, fill=INK)

    ix = data["index"]
    when = datetime.strptime(ix["date"], "%Y-%m-%d").strftime("%a %d %b %Y").upper()
    label = f"NIFTY 50 · LIVE AT {ix['time']} IST · {when}" if ix.get("live") else f"NIFTY 50 · CLOSE ON {when}"
    d.text((L, 104), label, font=f("int700", 20), fill=th["sub"])
    vf = f("bri800", 82)
    val = f"{ix['close']:,.2f}"
    d.text((L - 3, 206), val, font=vf, fill=PAPER, anchor="ls")
    up = ix["d1"] >= 0
    col = UP if up else DOWN
    chip = f"{abs(ix['close'] - ix['prev']):,.2f}  ({abs(ix['d1']):.2f}%)"
    cx = L + d.textlength(val, font=vf) + 26
    cf = f("int700", 27)
    cw = d.textlength(chip, font=cf) + 56
    d.rounded_rectangle([cx, 156, cx + cw, 204], radius=12, fill=col)
    arrow(d, cx + 14, 180, up, PAPER, 17)
    d.text((cx + 40, 180), chip, font=cf, fill=PAPER, anchor="lm")
    y = 226
    gap = 14
    bw = (W - 2 * L - 2 * gap) / 3
    for i, (lab, key) in enumerate((("1 WEEK", "w1"), ("1 MONTH", "m1"), ("1 YEAR", "y1"))):
        gx = L + i * (bw + gap)
        v = ix.get(key)
        d.rounded_rectangle([gx, y, gx + bw, y + 58], radius=12, fill=INK2)
        d.text((gx + 16, y + 29), lab, font=f("int600", 18), fill=th["sub"], anchor="lm")
        if v is None:
            d.text((gx + bw - 16, y + 29), "–", font=f("int700", 26), fill=th["sub"], anchor="rm")
        else:
            c = UP if v >= 0 else DOWN
            t = f"{abs(v):.2f}%"
            tfw = d.textlength(t, font=f("int700", 26))
            d.text((gx + bw - 16, y + 29), t, font=f("int700", 26), fill=c, anchor="rm")
            arrow(d, gx + bw - 16 - tfw - 24, y + 29, v >= 0, c, 15)

    # table: 2 columns x 25 rows, sorted by 1-day change
    rows = data["rows"][:50]
    half = (len(rows) + 1) // 2
    top = 306
    cgap = 20
    colw = (W - 2 * L - cgap) / 2
    rh = (H - 112 - (top + 30)) / max(half, 1)
    hf, sf, pf, nf = f("int700", 15), f("int600", 17), f("int600", 17), f("int600", 16)
    # right edges (relative to column start): price, 1D, 1W, 1M, 1Y
    edges = (226, 290, 354, 418, colw - 8)
    for c in range(2):
        x0 = L + c * (colw + cgap)
        d.text((x0 + 6, top), "#  STOCK", font=hf, fill=th["sub"])
        for lab, e in zip(("PRICE ₹" if has_glyph(hf, "₹") else "PRICE Rs", "1D", "1W", "1M", "1Y"), edges):
            d.text((x0 + e, top), lab, font=hf, fill=th["sub"], anchor="ra")
        for i, r in enumerate(rows[c * half:(c + 1) * half]):
            yy = top + 30 + i * rh
            if i % 2 == 0:
                d.rounded_rectangle([x0, yy, x0 + colw, yy + rh - 3], radius=6, fill=INK2)
            cy = yy + (rh - 3) / 2
            rank = c * half + i + 1
            d.text((x0 + 6, cy), f"{rank:>2}", font=hf, fill=th["sub"], anchor="lm")
            d.text((x0 + 34, cy), r["sym"][:11], font=sf, fill=PAPER, anchor="lm")
            price = r["close"]
            ptxt = f"{price:,.0f}" if price >= 10000 else f"{price:,.1f}"
            d.text((x0 + edges[0], cy), ptxt, font=pf, fill=PAPER, anchor="rm")
            for key, e in zip(("d1", "w1", "m1", "y1"), edges[1:]):
                v = r.get(key)
                txt = "–" if v is None else (f"{v:+.0f}%" if abs(v) >= 99.95 else f"{v:+.1f}%")
                colr = th["sub"] if v is None else (UP if v >= 0 else DOWN)
                d.text((x0 + e, cy), txt, font=nf, fill=colr, anchor="rm")
    d.text((L, H - 104), "Sorted by 1-day change · Data: NSE via Yahoo Finance · For information only, not investment advice",
           font=f("int500", 18), fill=th["sub"])
    d.line([(L, H - 72), (W - L, H - 72)], fill=th["rule"], width=1)
    d.text((L, H - 54), HANDLE, font=f("int600", 24), fill=PAPER)
    date = datetime.now(IST).strftime("%d %b %Y")
    df = f("iserif", 28)
    d.text((W - L - d.textlength(date, font=df), H - 58), date, font=df, fill=th["sub"])
    im.save(path, quality=93)


def movers(data, path):
    """End of day: top 10 gainers and top 10 losers of the Nifty 50, with price, change ₹ and change %."""
    th = {"tag": (242, 194, 48), "bg": INK, "ink": PAPER, "sub": (165, 165, 160), "rule": (60, 63, 70)}
    im = Image.new("RGB", (W, H), th["bg"])
    noise = Image.effect_noise((W, H), 9).convert("L")
    im = Image.blend(im, Image.merge("RGB", [noise] * 3), 0.04)
    d = ImageDraw.Draw(im)
    L = 48
    x, y0 = L + 18, 58
    for r in (19, 12, 6):
        d.ellipse([x - r, y0 - r, x + r, y0 + r], outline=PAPER, width=2)
    d.ellipse([x - 4, y0 - 4, x + 4, y0 + 4], fill=NEAR)
    d.text((L + 48, 38), "around us", font=f("bri800", 32), fill=PAPER)
    tag, tf = "MARKET CLOSE", f("int700", 21)
    tw = d.textlength(tag, font=tf)
    d.rounded_rectangle([W - L - tw - 40, 36, W - L, 80], radius=22, fill=th["tag"])
    d.text((W - L - tw - 20, 45), tag, font=tf, fill=INK)

    ix = data["index"]
    when = datetime.strptime(ix["date"], "%Y-%m-%d").strftime("%a %d %b %Y").upper()
    d.text((L - 2, 168), "Nifty 50 ", font=f("bri800", 64), fill=PAPER, anchor="ls")
    d.text((L + d.textlength("Nifty 50 ", font=f("bri800", 64)), 168), "movers", font=f("iserif", 72),
           fill=th["tag"], anchor="ls")
    up = ix["d1"] >= 0
    col = UP if up else DOWN
    line = f"CLOSE {when}  ·  NIFTY {ix['close']:,.2f}"
    lf = f("int700", 21)
    d.text((L, 196), line, font=lf, fill=th["sub"])
    chip = f"{abs(ix['close'] - ix['prev']):,.2f} ({abs(ix['d1']):.2f}%)"
    cx = L + d.textlength(line, font=lf) + 18
    cf = f("int700", 21)
    cw = d.textlength(chip, font=cf) + 44
    d.rounded_rectangle([cx, 192, cx + cw, 226], radius=9, fill=col)
    arrow(d, cx + 12, 209, up, PAPER, 13)
    d.text((cx + 32, 209), chip, font=cf, fill=PAPER, anchor="lm")

    rows = data["rows"]
    gainers = [r for r in rows if r["d1"] > 0][:10]
    losers = [r for r in reversed(rows) if r["d1"] < 0][:10]
    rh = 40
    cols = (L + 8, L + 56, W - L - 330, W - L - 170, W - L - 8)  # rank, stock, price, chg ₹, chg %
    rs = "₹" if has_glyph(f("int600", 18), "₹") else "Rs"

    def block(title, items, top, colr, is_up):
        d.text((L, top), title, font=f("int700", 24), fill=colr)
        hy = top + 40
        hf = f("int700", 16)
        d.text((cols[1], hy), "STOCK", font=hf, fill=th["sub"])
        d.text((cols[2], hy), f"PRICE {rs}", font=hf, fill=th["sub"], anchor="ra")
        d.text((cols[3], hy), f"CHANGE {rs}", font=hf, fill=th["sub"], anchor="ra")
        d.text((cols[4], hy), "CHANGE %", font=hf, fill=th["sub"], anchor="ra")
        y = hy + 26
        if not items:
            d.text((cols[1], y + 14), "None today", font=f("int500", 22), fill=th["sub"])
        for i, r in enumerate(items):
            yy = y + i * rh
            if i % 2 == 0:
                d.rounded_rectangle([L, yy, W - L, yy + rh - 4], radius=8, fill=INK2)
            cy = yy + (rh - 4) / 2
            d.text((cols[0], cy), f"{i + 1}", font=f("int700", 19), fill=th["sub"], anchor="lm")
            d.text((cols[1], cy), r["sym"], font=f("int700", 23), fill=PAPER, anchor="lm")
            p = r["close"]
            d.text((cols[2], cy), f"{p:,.2f}", font=f("int600", 22), fill=PAPER, anchor="rm")
            diff = r["close"] - r["prev"]
            d.text((cols[3], cy), f"{diff:+,.2f}", font=f("int600", 22), fill=colr, anchor="rm")
            pct = f"{abs(r['d1']):.2f}%"
            pf = f("int700", 23)
            d.text((cols[4], cy), pct, font=pf, fill=colr, anchor="rm")
            arrow(d, cols[4] - d.textlength(pct, font=pf) - 26, cy, is_up, colr, 14)
        return y + max(len(items), 1) * rh

    end = block("TOP 10 GAINERS", gainers, 246, UP, True)
    block("TOP 10 LOSERS", losers, end + 16, DOWN, False)
    d.text((L, H - 104), "Nifty 50 stocks, today's close vs previous close · Data: NSE via Yahoo Finance · Not investment advice",
           font=f("int500", 17), fill=th["sub"])
    d.line([(L, H - 72), (W - L, H - 72)], fill=th["rule"], width=1)
    d.text((L, H - 54), HANDLE, font=f("int600", 24), fill=PAPER)
    date = datetime.now(IST).strftime("%d %b %Y")
    df = f("iserif", 28)
    d.text((W - L - d.textlength(date, font=df), H - 58), date, font=df, fill=th["sub"])
    im.save(path, quality=93)


def gold(data, path, inr):
    """Gold rate today + last 10 days for up to 4 cities (per 10 grams).
    Same rate everywhere -> one table + city chips. Different -> city table + 22K per city."""
    im, d, th, y = base("GOLD RATE", "Gold rate today", accent="Gold")
    gold_c = th["tag"]
    card, card2, today_bg = (38, 34, 27), (31, 28, 23), (64, 54, 32)
    rs = rupee_sign(f("int700", 40)).strip() or "Rs"   # Inter has ₹; Bricolage does not
    cities = data["cities"]
    latest = data["latest"]
    ser = cities[0]["series"]
    dates = sorted(ser)[-10:]

    def money(v):
        return f"{rs}{inr(v * 10)}"

    def change(dates_, s, iso):
        i = dates_.index(iso)
        if i == 0:
            return None
        return (s[iso] - s[dates_[i - 1]]) * 10

    def chg_text(d_, x, cy, v, font, anchor="rm"):
        if v is None:
            d_.text((x, cy), "–", font=font, fill=th["sub"], anchor=anchor)
            return
        if abs(v) < 0.5:
            d_.text((x, cy), "no change", font=font, fill=th["sub"], anchor=anchor)
            return
        col = UP if v > 0 else DOWN
        t = f"{inr(abs(v))}"
        d_.text((x, cy), t, font=font, fill=col, anchor=anchor)
        arrow(d_, x - d_.textlength(t, font=font) - 24, cy, v > 0, col, 14)

    def day_label(iso):
        dt = datetime.strptime(iso, "%Y-%m-%d")
        return ("Today, " if iso == latest else dt.strftime("%a ")) + dt.strftime("%d %b")

    if data["same"]:
        # city chips
        cf = f("int600", 24)
        x = M
        for c in cities:
            w = d.textlength(c["name"], font=cf) + 40
            d.rounded_rectangle([x, y, x + w, y + 48], radius=24, outline=gold_c, width=2)
            d.text((x + w / 2, y + 24), c["name"], font=cf, fill=th["ink"], anchor="mm")
            x += w + 14
        note = (f"Same rate in all {len(cities)} cities  ·  " if len(cities) > 1 else "") + "prices for 10 grams"
        d.text((M, y + 70), note, font=f("int500", 24), fill=th["sub"])
        # two big boxes: 24K and 22K
        top, bh, gap = y + 118, 196, 20
        bw = (W - 2 * M - gap) / 2
        today = ser[latest]
        for i, (lab, k) in enumerate((("24 CARAT", "k24"), ("22 CARAT", "k22"))):
            x0 = M + i * (bw + gap)
            d.rounded_rectangle([x0, top, x0 + bw, top + bh], radius=20, fill=card)
            d.text((x0 + 26, top + 24), lab, font=f("int700", 22), fill=gold_c)
            sub = "pure gold · coins & bars" if k == "k24" else "jewellery gold"
            d.text((x0 + bw - 26, top + 26), sub, font=f("int500", 19), fill=th["sub"], anchor="ra")
            sym_f, num_f = f("int700", 50), f("bri800", 64)
            d.text((x0 + 24, top + 122), rs, font=sym_f, fill=gold_c, anchor="ls")
            d.text((x0 + 26 + d.textlength(rs, font=sym_f), top + 122), inr(today[k] * 10), font=num_f,
                   fill=th["ink"], anchor="ls")
            v = change(dates, {iso: ser[iso][k] for iso in dates}, latest)
            cy = top + 162
            if v is None or abs(v) < 0.5:
                d.text((x0 + 26, cy), "No change from yesterday", font=f("int600", 21), fill=th["sub"], anchor="lm")
            else:
                col = UP if v > 0 else DOWN
                arrow(d, x0 + 28, cy, v > 0, col, 14)
                d.text((x0 + 50, cy), f"{rs}{inr(abs(v))} vs yesterday", font=f("int600", 21), fill=col, anchor="lm")
            d.text((x0 + bw - 26, cy), f"{rs}{inr(today[k])} / g", font=f("int500", 20), fill=th["sub"], anchor="rm")
        # 18K + 10-day range line
        ly = top + bh + 30
        lf = f("int500", 22)
        if today.get("k18"):
            d.text((M, ly), f"18 carat  {money(today['k18'])}", font=lf, fill=th["ink"])
        k22 = [(ser[iso]["k22"], iso) for iso in dates]
        hi, lo = max(k22), min(k22)
        rng = f"22K in 10 days:  high {money(hi[0])} ({date_label(hi[1])})  ·  low {money(lo[0])} ({date_label(lo[1])})"
        d.text((W - M, ly), rng, font=f("int500", 21), fill=th["sub"], anchor="ra")
        # 10-day table
        ty = ly + 56
        hf = f("int700", 18)
        cols = (M + 18, M + 440, M + 600, M + 830, W - M - 18)
        d.text((cols[0], ty), "DATE", font=hf, fill=th["sub"])
        for lab, x in zip(("24K · 10 g", "CHANGE", "22K · 10 g", "CHANGE"), cols[1:]):
            d.text((x, ty), lab, font=hf, fill=th["sub"], anchor="ra")
        ty += 34
        rh = min(52, (H - 122 - ty) / max(len(dates), 1))
        for i, iso in enumerate(reversed(dates)):
            yy = ty + i * rh
            fill = today_bg if iso == latest else (card if i % 2 == 0 else None)
            if fill:
                d.rounded_rectangle([M, yy, W - M, yy + rh - 5], radius=10, fill=fill)
            cy = yy + (rh - 5) / 2
            bold = iso == latest
            d.text((cols[0], cy), day_label(iso), font=f("int700" if bold else "int500", 23),
                   fill=gold_c if bold else th["ink"], anchor="lm")
            for k, xv, xc in (("k24", cols[1], cols[2]), ("k22", cols[3], cols[4])):
                d.text((xv, cy), money(ser[iso][k]), font=f("int700" if bold else "int600", 24),
                       fill=th["ink"], anchor="rm")
                chg_text(d, xc, cy, change(dates, {j: ser[j][k] for j in dates}, iso), f("int600", 20))
    else:
        # today, city by city
        hf = f("int700", 18)
        cols = (M + 18, M + 520, M + 760, W - M - 18)
        d.text((cols[0], y), "CITY · TODAY", font=hf, fill=th["sub"])
        for lab, x in zip(("24K · 10 g", "22K · 10 g", "22K CHANGE"), cols[1:]):
            d.text((x, y), lab, font=hf, fill=th["sub"], anchor="ra")
        yy = y + 32
        for i, c in enumerate(cities):
            s = c["series"]
            ds = sorted(s)
            d.rounded_rectangle([M, yy, W - M, yy + 62], radius=12, fill=card if i % 2 == 0 else card2)
            cy = yy + 31
            d.text((cols[0], cy), c["name"], font=f("int700", 27), fill=th["ink"], anchor="lm")
            d.text((cols[1], cy), money(s[latest]["k24"]), font=f("int700", 30), fill=th["ink"], anchor="rm")
            d.text((cols[2], cy), money(s[latest]["k22"]), font=f("int700", 30), fill=gold_c, anchor="rm")
            chg_text(d, cols[3], cy, change(ds, {j: s[j]["k22"] for j in ds}, latest), f("int600", 21))
            yy += 68
        # last 10 days, 22K per city
        ty = yy + 30
        d.text((M, ty), "22 CARAT · 10 GRAMS · LAST 10 DAYS", font=f("int700", 21), fill=gold_c)
        ty += 42
        short = {"Visakhapatnam": "VIZAG"}
        n = len(cities)
        first = M + 240
        step = (W - M - 18 - first) / n
        xs = [first + step * (j + 1) for j in range(n)]
        d.text((M + 18, ty), "DATE", font=hf, fill=th["sub"])
        for c, x in zip(cities, xs):
            d.text((x, ty), short.get(c["name"], c["name"].upper()), font=hf, fill=th["sub"], anchor="ra")
        ty += 32
        rh = min(50, (H - 122 - ty) / max(len(dates), 1))
        for i, iso in enumerate(reversed(dates)):
            yy = ty + i * rh
            fill = today_bg if iso == latest else (card if i % 2 == 0 else None)
            if fill:
                d.rounded_rectangle([M, yy, W - M, yy + rh - 5], radius=10, fill=fill)
            cy = yy + (rh - 5) / 2
            d.text((M + 18, cy), day_label(iso), font=f("int600", 22), fill=th["ink"], anchor="lm")
            for c, x in zip(cities, xs):
                v = c["series"].get(iso)
                d.text((x, cy), money(v["k22"]) if v else "–", font=f("int600", 22), fill=th["ink"], anchor="rm")
    src = "Source: GoodReturns" + (" · 22K cross-checked with BankBazaar" if data.get("verified") else "") + \
          " · Excludes 3% GST, TCS & making charges"
    footer(d, th, note=src)
    im.save(path, quality=93)


def gold_state(card, path, inr, hint=None):
    """One state's gold slide: today 24K/22K/18K, price by weight, 10-day 22K chart, 10-day table."""
    th = THEMES["GOLD RATE"]
    gold_c, ink, sub = th["tag"], th["ink"], th["sub"]
    panel, panel2, today_bg = (38, 34, 27), (31, 28, 23), (64, 54, 32)
    im = Image.new("RGB", (W, H), th["bg"])
    noise = Image.effect_noise((W, H), 9).convert("L")
    im = Image.blend(im, Image.merge("RGB", [noise] * 3), 0.04)
    d = ImageDraw.Draw(im)
    rs = rupee_sign(f("int700", 40)).strip() or "Rs"
    ser, latest = card["series"], card["latest"]
    dates = sorted(ser)[-10:]
    today = ser[latest]

    def money(v, mult=10):
        return f"{rs}{inr(v * mult)}"

    def delta(key, iso, mult=10):
        i = dates.index(iso)
        if i == 0 or not ser[iso].get(key) or not ser[dates[i - 1]].get(key):
            return None
        return (ser[iso][key] - ser[dates[i - 1]][key]) * mult

    def chg(x, cy, v, font, anchor="rm"):
        if v is None:
            d.text((x, cy), "–", font=font, fill=sub, anchor=anchor)
        elif abs(v) < 0.5:
            d.text((x, cy), "no change", font=font, fill=sub, anchor=anchor)
        else:
            col = UP if v > 0 else DOWN
            t = inr(abs(v))
            d.text((x, cy), t, font=font, fill=col, anchor=anchor)
            arrow(d, x - d.textlength(t, font=font) - 22, cy, v > 0, col, 13)

    # header
    x, y0 = M + 20, 86
    for r in (21, 14, 7):
        d.ellipse([x - r, y0 - r, x + r, y0 + r], outline=ink, width=2)
    d.ellipse([x - 5, y0 - 5, x + 5, y0 + 5], fill=NEAR)
    d.text((M + 54, 64), "around us", font=f("bri800", 36), fill=ink)
    tag, tf = "GOLD RATE", f("int700", 23)
    tw = d.textlength(tag, font=tf)
    d.rounded_rectangle([W - M - tw - 44, 62, W - M, 110], radius=24, fill=gold_c)
    d.text((W - M - tw - 22, 72), tag, font=tf, fill=INK)
    when = datetime.strptime(latest, "%Y-%m-%d").strftime("%a %d %b %Y").upper()
    d.text((M, 132), f"GOLD RATE TODAY · {when}", font=f("int700", 22), fill=gold_c)
    d.text((M - 3, 248), card["state"], font=f("bri800", 86), fill=ink, anchor="ls")

    # no city names on the slide: the state's rate (the rate its cities share) is shown
    y = 270
    d.text((M, y), "Prices for 10 grams unless shown", font=f("int500", 22), fill=sub)
    y += 18

    # today: 24K / 22K / 18K
    y += 40
    gap, bh = 16, 138
    bw = (W - 2 * M - 2 * gap) / 3
    for i, (lab, k, what) in enumerate((("24 CARAT", "k24", "coins & bars"), ("22 CARAT", "k22", "jewellery"),
                                        ("18 CARAT", "k18", "light jewellery"))):
        x0 = M + i * (bw + gap)
        d.rounded_rectangle([x0, y, x0 + bw, y + bh], radius=18, fill=panel)
        d.text((x0 + 20, y + 18), lab, font=f("int700", 20), fill=gold_c)
        d.text((x0 + bw - 20, y + 20), what, font=f("int500", 17), fill=sub, anchor="ra")
        v = today.get(k)
        if not v:
            d.text((x0 + 20, y + 88), "not available", font=f("int600", 24), fill=sub, anchor="ls")
            continue
        sym_f, num_f = f("int700", 36), f("bri800", 46)
        d.text((x0 + 20, y + 88), rs, font=sym_f, fill=gold_c, anchor="ls")
        d.text((x0 + 22 + d.textlength(rs, font=sym_f), y + 88), inr(v * 10), font=num_f, fill=ink, anchor="ls")
        dv = delta(k, latest)
        cy = y + 116
        if dv is None or abs(dv) < 0.5:
            d.text((x0 + 20, cy), "no change from yesterday", font=f("int600", 18), fill=sub, anchor="lm")
        else:
            col = UP if dv > 0 else DOWN
            arrow(d, x0 + 22, cy, dv > 0, col, 12)
            d.text((x0 + 40, cy), f"{rs}{inr(abs(dv))} vs yesterday", font=f("int600", 18), fill=col, anchor="lm")

    # price by weight (left) + 10-day 22K chart (right)
    y += bh + 18
    ph = 206
    pw = 548
    pw2 = W - 2 * M - gap - pw
    lx, rx = M, M + pw + gap
    d.rounded_rectangle([lx, y, lx + pw, y + ph], radius=18, fill=panel2)
    d.text((lx + 20, y + 16), "PRICE TODAY BY WEIGHT", font=f("int700", 19), fill=gold_c)
    cols = (lx + 20, lx + 300, lx + 418, lx + pw - 18)
    hy = y + 54
    for lab, xx in zip(("24K", "22K", "18K"), cols[1:]):
        d.text((xx, hy), lab, font=f("int700", 17), fill=sub, anchor="ra")
    for j, (lab, g) in enumerate((("1 gram", 1), ("8 g (1 sovereign)", 8), ("10 grams", 10))):
        cy = hy + 50 + j * 42
        if j % 2 == 0:
            d.rounded_rectangle([lx + 10, cy - 18, lx + pw - 10, cy + 18], radius=8, fill=panel)
        d.text((cols[0], cy), lab, font=f("int600", 21), fill=ink, anchor="lm")
        for k, xx in zip(("k24", "k22", "k18"), cols[1:]):
            v = today.get(k)
            d.text((xx, cy), money(v, g) if v else "–", font=f("int600", 21),
                   fill=gold_c if k == "k22" else ink, anchor="rm")

    d.rounded_rectangle([rx, y, rx + pw2, y + ph], radius=18, fill=panel2)
    d.text((rx + 20, y + 16), "22 CARAT · 10 g · TREND", font=f("int700", 19), fill=gold_c)
    vals = [ser[i]["k22"] * 10 for i in dates]
    lo, hi = min(vals), max(vals)
    cx0, cx1, cy0, cy1 = rx + 30, rx + pw2 - 30, y + 58, y + ph - 86
    span = (hi - lo) or 1
    pts = [(cx0 + (cx1 - cx0) * i / max(len(vals) - 1, 1),
            cy1 - (v - lo) / span * (cy1 - cy0) if hi != lo else (cy0 + cy1) / 2) for i, v in enumerate(vals)]
    for gy in (cy0, cy1):
        d.line([(cx0, gy), (cx1, gy)], fill=(60, 54, 44), width=1)
    d.line(pts, fill=gold_c, width=4, joint="curve")
    for i, (px, py) in enumerate(pts):
        r = 7 if i == len(pts) - 1 else 4
        d.ellipse([px - r, py - r, px + r, py + r], fill=gold_c if i == len(pts) - 1 else (140, 116, 60))
    sf = f("int600", 15)
    d.text((cx0 - 6, cy1 + 18), date_label(dates[0]), font=sf, fill=sub, anchor="lm")
    d.text((cx1 + 6, cy1 + 18), date_label(dates[-1]), font=sf, fill=sub, anchor="rm")
    first, last = vals[0], vals[-1]
    diff = last - first
    pct = diff / first * 100 if first else 0
    hl = f"High {money(hi, 1)}  ·  Low {money(lo, 1)}"
    d.text((rx + 20, y + ph - 46), hl, font=f("int600", 17), fill=ink, anchor="lm")
    col = UP if diff > 0 else DOWN if diff < 0 else sub
    tt = "no change" if abs(diff) < 0.5 else f"{'up' if diff > 0 else 'down'} {rs}{inr(abs(diff))} ({abs(pct):.1f}%)"
    d.text((rx + 20, y + ph - 20), "10-day change: " + tt, font=f("int700", 17), fill=col, anchor="lm")

    # 10-day table
    y += ph + 20
    d.text((M, y), "LAST 10 DAYS", font=f("int700", 22), fill=gold_c)
    d.text((W - M, y + 3), "24 & 22 carat · 10 grams", font=f("int500", 19), fill=sub, anchor="ra")
    y += 36
    hf = f("int700", 17)
    tcols = (M + 18, M + 430, M + 590, M + 820, W - M - 18)
    d.text((tcols[0], y), "DATE", font=hf, fill=sub)
    for lab, xx in zip(("24K · 10 g", "CHANGE", "22K · 10 g", "CHANGE"), tcols[1:]):
        d.text((xx, y), lab, font=hf, fill=sub, anchor="ra")
    y += 30
    rh = min(44, (H - 150 - y) / max(len(dates), 1))
    for i, iso in enumerate(reversed(dates)):
        yy = y + i * rh
        fill = today_bg if iso == latest else (panel if i % 2 == 0 else None)
        if fill:
            d.rounded_rectangle([M, yy, W - M, yy + rh - 4], radius=9, fill=fill)
        cy = yy + (rh - 4) / 2
        bold = iso == latest
        dt = datetime.strptime(iso, "%Y-%m-%d")
        lab = ("Today, " if bold else dt.strftime("%a ")) + dt.strftime("%d %b")
        d.text((tcols[0], cy), lab, font=f("int700" if bold else "int500", 21),
               fill=gold_c if bold else ink, anchor="lm")
        for k, xv, xc in (("k24", tcols[1], tcols[2]), ("k22", tcols[3], tcols[4])):
            d.text((xv, cy), money(ser[iso][k]), font=f("int700" if bold else "int600", 22), fill=ink, anchor="rm")
            chg(xc, cy, delta(k, iso), f("int600", 18))
    if hint:   # (text, "next" | "back"); arrow drawn, not a font glyph
        text, way = hint
        hf2 = f("int700", 21)
        tw2 = d.textlength(text, font=hf2)
        hy2 = H - 140
        if way == "next":
            d.text((W - M - 34, hy2), text, font=hf2, fill=gold_c, anchor="rm")
            d.line([(W - M - 24, hy2), (W - M - 2, hy2)], fill=gold_c, width=3)
            d.polygon([(W - M, hy2), (W - M - 10, hy2 - 7), (W - M - 10, hy2 + 7)], fill=gold_c)
        else:
            d.text((W - M, hy2), text, font=hf2, fill=gold_c, anchor="rm")
            x2 = W - M - tw2 - 12
            d.line([(x2 - 22, hy2), (x2, hy2)], fill=gold_c, width=3)
            d.polygon([(x2 - 24, hy2), (x2 - 14, hy2 - 7), (x2 - 14, hy2 + 7)], fill=gold_c)
    src = ("Source: GoodReturns" + (" · cross-checked with BankBazaar" if card.get("verified") else "")
           + " · Excludes 3% GST, TCS & making charges")
    footer(d, th, note=src)
    im.save(path, quality=93)


def silver_state(card, path, inr, hint=None):
    """One state's silver slide: today per kg / 100 g / 10 g / 1 g, 10-day chart, 10-day table (per kg)."""
    th = THEMES["SILVER RATE"]
    acc, ink, sub = th["tag"], th["ink"], th["sub"]
    panel, panel2, today_bg = (36, 40, 47), (30, 33, 39), (58, 64, 74)
    im = Image.new("RGB", (W, H), th["bg"])
    noise = Image.effect_noise((W, H), 9).convert("L")
    im = Image.blend(im, Image.merge("RGB", [noise] * 3), 0.04)
    d = ImageDraw.Draw(im)
    rs = rupee_sign(f("int700", 40)).strip() or "Rs"
    ser, latest = card["series"], card["latest"]
    dates = sorted(ser)[-10:]
    kg = ser[latest]

    def money(v):
        return f"{rs}{inr(v)}"

    def delta(iso):
        i = dates.index(iso)
        return None if i == 0 else ser[iso] - ser[dates[i - 1]]

    def chg(x, cy, v, font, anchor="rm"):
        if v is None:
            d.text((x, cy), "–", font=font, fill=sub, anchor=anchor)
        elif abs(v) < 0.5:
            d.text((x, cy), "no change", font=font, fill=sub, anchor=anchor)
        else:
            col = UP if v > 0 else DOWN
            t = inr(abs(v))
            d.text((x, cy), t, font=font, fill=col, anchor=anchor)
            arrow(d, x - d.textlength(t, font=font) - 22, cy, v > 0, col, 13)

    # header
    x, y0 = M + 20, 86
    for r in (21, 14, 7):
        d.ellipse([x - r, y0 - r, x + r, y0 + r], outline=ink, width=2)
    d.ellipse([x - 5, y0 - 5, x + 5, y0 + 5], fill=NEAR)
    d.text((M + 54, 64), "around us", font=f("bri800", 36), fill=ink)
    tag, tf = "SILVER RATE", f("int700", 23)
    tw = d.textlength(tag, font=tf)
    d.rounded_rectangle([W - M - tw - 44, 62, W - M, 110], radius=24, fill=acc)
    d.text((W - M - tw - 22, 72), tag, font=tf, fill=INK)
    when = datetime.strptime(latest, "%Y-%m-%d").strftime("%a %d %b %Y").upper()
    d.text((M, 132), f"SILVER RATE TODAY · {when}", font=f("int700", 22), fill=acc)
    d.text((M - 3, 248), card["state"], font=f("bri800", 86), fill=ink, anchor="ls")
    y = 270
    d.text((M, y), "Price for 1 kilogram unless shown", font=f("int500", 22), fill=sub)
    y += 58

    # today: big kg price + change
    bh = 150
    d.rounded_rectangle([M, y, W - M, y + bh], radius=18, fill=panel)
    d.text((M + 24, y + 20), "TODAY · 1 KG", font=f("int700", 21), fill=acc)
    sym_f, num_f = f("int700", 46), f("bri800", 72)
    d.text((M + 24, y + 104), rs, font=sym_f, fill=acc, anchor="ls")
    d.text((M + 28 + d.textlength(rs, font=sym_f), y + 104), inr(kg), font=num_f, fill=ink, anchor="ls")
    dv = delta(latest)
    cy = y + 128
    if dv is None or abs(dv) < 0.5:
        d.text((M + 26, cy), "no change from yesterday", font=f("int600", 20), fill=sub, anchor="lm")
    else:
        col = UP if dv > 0 else DOWN
        arrow(d, M + 28, cy, dv > 0, col, 13)
        d.text((M + 48, cy), f"{rs}{inr(abs(dv))} per kg vs yesterday", font=f("int600", 20), fill=col, anchor="lm")
    # by weight, right side of the same box
    bx = W - M - 24
    rows = (("1 gram", kg / 1000), ("10 grams", kg / 100), ("100 grams", kg / 10))
    for j, (lab, v) in enumerate(rows):
        ry = y + 30 + j * 40
        d.text((bx - 190, ry), lab, font=f("int500", 21), fill=sub, anchor="rm")
        txt = f"{rs}{inr(v)}" if v == int(v) else f"{rs}{v:,.2f}"
        d.text((bx, ry), txt, font=f("int700", 24), fill=ink, anchor="rm")

    # 10-day chart
    y += bh + 18
    ph = 210
    d.rounded_rectangle([M, y, W - M, y + ph], radius=18, fill=panel2)
    d.text((M + 20, y + 16), "1 KG · TREND", font=f("int700", 19), fill=acc)
    vals = [ser[i] for i in dates]
    lo, hi = min(vals), max(vals)
    cx0, cx1, cy0, cy1 = M + 40, W - M - 300, y + 62, y + ph - 60
    span = (hi - lo) or 1
    pts = [(cx0 + (cx1 - cx0) * i / max(len(vals) - 1, 1),
            cy1 - (v - lo) / span * (cy1 - cy0) if hi != lo else (cy0 + cy1) / 2) for i, v in enumerate(vals)]
    for gy in (cy0, cy1):
        d.line([(cx0, gy), (cx1, gy)], fill=(58, 64, 74), width=1)
    d.line(pts, fill=acc, width=4, joint="curve")
    for i, (px, py) in enumerate(pts):
        r = 7 if i == len(pts) - 1 else 4
        d.ellipse([px - r, py - r, px + r, py + r], fill=acc if i == len(pts) - 1 else (120, 128, 140))
    sf = f("int600", 15)
    d.text((cx0 - 6, cy1 + 18), date_label(dates[0]), font=sf, fill=sub, anchor="lm")
    d.text((cx1 + 6, cy1 + 18), date_label(dates[-1]), font=sf, fill=sub, anchor="rm")
    rx = W - M - 262
    d.text((rx, y + 62), "HIGH", font=f("int700", 16), fill=sub)
    d.text((rx, y + 86), money(hi), font=f("int700", 24), fill=ink)
    d.text((rx, y + 120), "LOW", font=f("int700", 16), fill=sub)
    d.text((rx, y + 144), money(lo), font=f("int700", 24), fill=ink)
    diff = vals[-1] - vals[0]
    pct = diff / vals[0] * 100 if vals[0] else 0
    col = UP if diff > 0 else DOWN if diff < 0 else sub
    tt = "no change" if abs(diff) < 0.5 else f"{'up' if diff > 0 else 'down'} {rs}{inr(abs(diff))} ({abs(pct):.1f}%)"
    d.text((M + 20, y + ph - 22), "10-day change: " + tt, font=f("int700", 18), fill=col, anchor="lm")

    # 10-day table
    y += ph + 20
    d.text((M, y), "LAST 10 DAYS", font=f("int700", 22), fill=acc)
    d.text((W - M, y + 3), "price per 1 kg, 100 g and 10 g", font=f("int500", 19), fill=sub, anchor="ra")
    y += 36
    hf = f("int700", 17)
    tcols = (M + 18, M + 470, M + 640, M + 820, W - M - 18)
    d.text((tcols[0], y), "DATE", font=hf, fill=sub)
    for lab, xx in zip(("1 KG", "CHANGE", "100 g", "10 g"), tcols[1:]):
        d.text((xx, y), lab, font=hf, fill=sub, anchor="ra")
    y += 30
    rh = min(44, (H - 150 - y) / max(len(dates), 1))
    for i, iso in enumerate(reversed(dates)):
        yy = y + i * rh
        fill = today_bg if iso == latest else (panel if i % 2 == 0 else None)
        if fill:
            d.rounded_rectangle([M, yy, W - M, yy + rh - 4], radius=9, fill=fill)
        cy = yy + (rh - 4) / 2
        bold = iso == latest
        dt = datetime.strptime(iso, "%Y-%m-%d")
        lab = ("Today, " if bold else dt.strftime("%a ")) + dt.strftime("%d %b")
        d.text((tcols[0], cy), lab, font=f("int700" if bold else "int500", 21),
               fill=acc if bold else ink, anchor="lm")
        d.text((tcols[1], cy), money(ser[iso]), font=f("int700" if bold else "int600", 22), fill=ink, anchor="rm")
        chg(tcols[2], cy, delta(iso), f("int600", 18))
        d.text((tcols[3], cy), money(ser[iso] / 10), font=f("int600", 21), fill=ink, anchor="rm")
        d.text((tcols[4], cy), money(ser[iso] / 100), font=f("int600", 21), fill=ink, anchor="rm")
    if hint:
        text, way = hint
        hf2 = f("int700", 21)
        tw2 = d.textlength(text, font=hf2)
        hy2 = H - 140
        if way == "next":
            d.text((W - M - 34, hy2), text, font=hf2, fill=acc, anchor="rm")
            d.line([(W - M - 24, hy2), (W - M - 2, hy2)], fill=acc, width=3)
            d.polygon([(W - M, hy2), (W - M - 10, hy2 - 7), (W - M - 10, hy2 + 7)], fill=acc)
        else:
            d.text((W - M, hy2), text, font=hf2, fill=acc, anchor="rm")
            x2 = W - M - tw2 - 12
            d.line([(x2 - 22, hy2), (x2, hy2)], fill=acc, width=3)
            d.polygon([(x2 - 24, hy2), (x2 - 14, hy2 - 7), (x2 - 14, hy2 + 7)], fill=acc)
    src = ("Source: GoodReturns" + (" · cross-checked with BankBazaar" if card.get("verified") else "")
           + " · Excludes 3% GST & making charges")
    footer(d, th, note=src)
    im.save(path, quality=93)


PLATFORM_COLOURS = {
    "Netflix": (229, 9, 20), "Prime Video": (0, 150, 210), "JioHotstar": (20, 90, 210), "ZEE5": (120, 60, 200),
    "SonyLIV": (190, 140, 30), "Aha": (255, 100, 30), "Sun NXT": (240, 130, 0), "ETV Win": (60, 140, 220),
    "Apple TV+": (110, 110, 115), "Lionsgate Play": (200, 60, 60), "MX Player": (40, 120, 220),
    "Theatres": (200, 40, 90),
}


def star(d, cx, cy, r, fill):
    import math
    pts = []
    for i in range(10):
        ang = -math.pi / 2 + i * math.pi / 5
        rr = r if i % 2 == 0 else r * 0.45
        pts.append((cx + rr * math.cos(ang), cy + rr * math.sin(ang)))
    d.polygon(pts, fill=fill)


def releases(sections, subtitle, path, hint=None, page=None):
    """Friday releases slide. sections = [(heading, rows)]; each row: title, type, language, platform, date,
    note, genres, runtime, rating, rating_src. Rows grow taller when there are few of them."""
    th = {"tag": (242, 150, 60), "bg": (22, 19, 28), "ink": PAPER, "sub": (160, 152, 170), "rule": (66, 58, 76)}
    acc, ink, sub = th["tag"], th["ink"], th["sub"]
    card, card2 = (36, 31, 44), (30, 26, 37)
    im = Image.new("RGB", (W, H), th["bg"])
    noise = Image.effect_noise((W, H), 9).convert("L")
    im = Image.blend(im, Image.merge("RGB", [noise] * 3), 0.04)
    d = ImageDraw.Draw(im)
    x, y0 = M + 20, 86
    for r in (21, 14, 7):
        d.ellipse([x - r, y0 - r, x + r, y0 + r], outline=ink, width=2)
    d.ellipse([x - 5, y0 - 5, x + 5, y0 + 5], fill=NEAR)
    d.text((M + 54, 64), "around us", font=f("bri800", 36), fill=ink)
    tag, tf = "RELEASES", f("int700", 23)
    tw = d.textlength(tag, font=tf)
    d.rounded_rectangle([W - M - tw - 44, 62, W - M, 110], radius=24, fill=acc)
    d.text((W - M - tw - 22, 72), tag, font=tf, fill=INK)
    d.text((M, 132), ("THIS WEEK · " + subtitle).upper(), font=f("int700", 22), fill=acc)
    big, ser = f("bri800", 84), f("iserif", 94)
    d.text((M - 3, 248), "New ", font=big, fill=ink, anchor="ls")
    d.text((M + d.textlength("New ", font=big), 248), "releases", font=ser, fill=acc, anchor="ls")
    d.text((M, 272), "Telugu · Tamil · Hindi films and series · cinemas and OTT", font=f("int500", 24), fill=sub)
    y = 324
    nrows = sum(len(r) for _, r in sections)
    nsec = len(sections)
    avail = H - 166 - y
    rh = min(150, avail / max(nrows + 0.55 * nsec, 1))
    hh = rh * 0.55
    tall = rh >= 128
    tfnt, mf, nf = f("int700", 34 if tall else 31), f("int500", 22 if tall else 20), f("int500", 20)
    for heading, rows in sections:
        d.text((M, y + hh / 2), heading.upper(), font=f("int700", 22), fill=acc, anchor="lm")
        d.line([(M + d.textlength(heading.upper(), font=f("int700", 22)) + 16, y + hh / 2), (W - M, y + hh / 2)],
               fill=th["rule"], width=1)
        y += hh
        for i, r in enumerate(rows):
            yy = y + i * rh
            d.rounded_rectangle([M, yy, W - M, yy + rh - 10], radius=16, fill=card if i % 2 == 0 else card2)
            cy = yy + (rh - 10) / 2
            pc = PLATFORM_COLOURS.get(r["platform"], (90, 90, 100))
            pf = f("int700", 17)
            plabel = r["platform"].upper()
            pw = d.textlength(plabel, font=pf) + 24
            d.rounded_rectangle([M + 16, cy - 32, M + 16 + pw, cy - 4], radius=8, fill=pc)
            d.text((M + 16 + pw / 2, cy - 18), plabel, font=pf, fill=PAPER, anchor="mm")
            dt = datetime.strptime(r["date"], "%Y-%m-%d")
            d.text((M + 16, cy + 18), dt.strftime("%a %-d %b").upper(), font=f("int600", 18), fill=sub, anchor="lm")
            tx = M + 196
            title = r["title"]
            while d.textlength(title, font=tfnt) > 560 and len(title) > 8:
                title = title[:-2].rstrip() + "…"
            meta = [r["language"], "Series" if r["type"] == "series" else "Film"] + (r.get("genres") or [])
            if r.get("runtime") and r["type"] != "series":
                meta.append(f"{r['runtime']} min")
            mline = " · ".join(m for m in meta if m)
            while d.textlength(mline, font=mf) > 560 and len(mline) > 10:
                mline = mline[:-2].rstrip() + "…"
            note = (r.get("note") or "").strip()
            if tall and note:
                d.text((tx, cy - 36), title, font=tfnt, fill=ink, anchor="lm")
                d.text((tx, cy + 2), mline, font=mf, fill=sub, anchor="lm")
                while d.textlength(note, font=nf) > 560 and len(note) > 10:
                    note = note[:-2].rstrip() + "…"
                d.text((tx, cy + 34), note[:1].upper() + note[1:], font=nf, fill=(190, 182, 200), anchor="lm")
            else:
                d.text((tx, cy - 16), title, font=tfnt, fill=ink, anchor="lm")
                d.text((tx, cy + 20), mline, font=mf, fill=sub, anchor="lm")
            if r.get("rating"):
                bx1, bx0 = W - M - 16, W - M - 16 - 150
                d.rounded_rectangle([bx0, cy - 26, bx1, cy + 26], radius=12, fill=(50, 44, 60))
                star(d, bx0 + 28, cy, 15, acc)
                d.text((bx1 - 14, cy - 8), f"{r['rating']:.1f}", font=f("bri800", 30), fill=ink, anchor="rm")
                d.text((bx1 - 14, cy + 17), r.get("rating_src", ""), font=f("int600", 14), fill=sub, anchor="rm")
            else:
                d.rounded_rectangle([W - M - 16 - 90, cy - 20, W - M - 16, cy + 20], radius=10, outline=acc, width=2)
                d.text((W - M - 16 - 45, cy), "NEW", font=f("int700", 20), fill=acc, anchor="mm")
        y += len(rows) * rh + 8
    if hint:
        text, way = hint
        hf2 = f("int700", 21)
        hy2 = H - 140
        d.text((W - M - 34, hy2), text, font=hf2, fill=acc, anchor="rm")
        d.line([(W - M - 24, hy2), (W - M - 2, hy2)], fill=acc, width=3)
        d.polygon([(W - M, hy2), (W - M - 10, hy2 - 7), (W - M - 10, hy2 + 7)], fill=acc)
    if page:
        d.text((M, H - 140), f"{page[0]} / {page[1]}", font=f("int600", 20), fill=sub, anchor="lm")
    footer(d, th, note="Checked against this week's release round-ups and TMDB · Ratings at posting · Dates as announced")
    im.save(path, quality=93)


def _dark_header(d, tag, L=48):
    th = {"tag": (242, 194, 48), "bg": INK, "ink": PAPER, "sub": (165, 165, 160), "rule": (60, 63, 70)}
    x, y0 = L + 18, 58
    for r in (19, 12, 6):
        d.ellipse([x - r, y0 - r, x + r, y0 + r], outline=PAPER, width=2)
    d.ellipse([x - 4, y0 - 4, x + 4, y0 + 4], fill=NEAR)
    d.text((L + 48, 38), "around us", font=f("bri800", 32), fill=PAPER)
    tf = f("int700", 21)
    tw = d.textlength(tag, font=tf)
    d.rounded_rectangle([W - L - tw - 40, 36, W - L, 80], radius=22, fill=th["tag"])
    d.text((W - L - tw - 20, 45), tag, font=tf, fill=INK)
    return th


def _dark_footer(d, th, note, L=48):
    d.text((L, H - 104), note, font=f("int500", 17), fill=th["sub"])
    d.line([(L, H - 72), (W - L, H - 72)], fill=th["rule"], width=1)
    d.text((L, H - 54), HANDLE, font=f("int600", 24), fill=PAPER)
    date = datetime.now(IST).strftime("%d %b %Y")
    df = f("iserif", 28)
    d.text((W - L - d.textlength(date, font=df), H - 58), date, font=df, fill=th["sub"])


def nifty_sessions(data, path):
    """Nifty 50: today's close + previous 14 sessions. Bar chart of daily % moves, then the table."""
    im = Image.new("RGB", (W, H), INK)
    noise = Image.effect_noise((W, H), 9).convert("L")
    im = Image.blend(im, Image.merge("RGB", [noise] * 3), 0.04)
    d = ImageDraw.Draw(im)
    L = 48
    th = _dark_header(d, "NIFTY 50", L)
    rows = data["rows"]
    today = rows[-1]
    when = datetime.strptime(today["date"], "%Y-%m-%d").strftime("%a %d %b %Y").upper()
    d.text((L, 104), f"NIFTY 50 · CLOSE ON {when} · LAST 15 SESSIONS", font=f("int700", 20), fill=th["sub"])
    vf = f("bri800", 82)
    val = f"{today['close']:,.2f}"
    d.text((L - 3, 206), val, font=vf, fill=PAPER, anchor="ls")
    up = today["pts"] >= 0
    col = UP if up else DOWN
    chip = f"{abs(today['pts']):,.2f}  ({abs(today['pct']):.2f}%) today"
    cx = L + d.textlength(val, font=vf) + 26
    cf = f("int700", 26)
    cw = d.textlength(chip, font=cf) + 56
    d.rounded_rectangle([cx, 156, cx + cw, 204], radius=12, fill=col)
    arrow(d, cx + 14, 180, up, PAPER, 17)
    d.text((cx + 40, 180), chip, font=cf, fill=PAPER, anchor="lm")
    # 15-session summary line
    first_prev = data["first_prev"][1]
    tot = today["close"] - first_prev
    tp = tot / first_prev * 100
    hi = max(rows, key=lambda r: r["close"])
    lo = min(rows, key=lambda r: r["close"])
    tcol = UP if tot >= 0 else DOWN
    d.text((L, 232), f"15 sessions: {'+' if tot >= 0 else '−'}{abs(tot):,.2f} pts ({abs(tp):.2f}%)   ·   "
                     f"high {hi['close']:,.2f} ({date_label(hi['date'])})   ·   low {lo['close']:,.2f} ({date_label(lo['date'])})",
           font=f("int600", 21), fill=th["sub"])
    # bar chart of daily % change
    top, bot = 300, 520
    d.rounded_rectangle([L, 276, W - L, 560], radius=14, fill=INK2)
    d.text((L + 18, 288), "DAILY CHANGE %", font=f("int700", 17), fill=th["sub"])
    n = len(rows)
    gap = 10
    bw = (W - 2 * L - 36 - gap * (n - 1)) / n
    mx = max(abs(r["pct"]) for r in rows) or 1
    zero = (top + bot) / 2
    d.line([(L + 18, zero), (W - L - 18, zero)], fill=th["rule"], width=1)
    for i, r in enumerate(rows):
        x0 = L + 18 + i * (bw + gap)
        h = (bot - top) / 2 * abs(r["pct"]) / mx
        c = UP if r["pct"] >= 0 else DOWN
        if r["pct"] >= 0:
            d.rounded_rectangle([x0, zero - h, x0 + bw, zero], radius=4, fill=c)
            d.text((x0 + bw / 2, zero - h - 12), f"{r['pct']:+.1f}", font=f("int600", 14), fill=c, anchor="mm")
        else:
            d.rounded_rectangle([x0, zero, x0 + bw, zero + h], radius=4, fill=c)
            d.text((x0 + bw / 2, zero + h + 12), f"{r['pct']:+.1f}", font=f("int600", 14), fill=c, anchor="mm")
        lab = datetime.strptime(r["date"], "%Y-%m-%d").strftime("%d")
        d.text((x0 + bw / 2, 540), lab, font=f("int500", 14), fill=th["sub"], anchor="mm")
    # table, newest first
    y = 586
    hf = f("int700", 16)
    cols = (L + 12, L + 430, L + 660, W - L - 12)
    d.text((cols[0], y), "SESSION", font=hf, fill=th["sub"])
    for lab, x in zip(("CLOSE", "CHANGE PTS", "CHANGE %"), cols[1:]):
        d.text((x, y), lab, font=hf, fill=th["sub"], anchor="ra")
    y += 28
    rh = (H - 118 - y) / n
    for i, r in enumerate(reversed(rows)):
        yy = y + i * rh
        if i == 0:
            d.rounded_rectangle([L, yy, W - L, yy + rh - 3], radius=8, fill=(64, 58, 32))
        elif i % 2 == 0:
            d.rounded_rectangle([L, yy, W - L, yy + rh - 3], radius=8, fill=INK2)
        cy = yy + (rh - 3) / 2
        dt = datetime.strptime(r["date"], "%Y-%m-%d")
        lab = ("Today, " if i == 0 else dt.strftime("%a ")) + dt.strftime("%d %b")
        d.text((cols[0], cy), lab, font=f("int700" if i == 0 else "int500", 21),
               fill=th["tag"] if i == 0 else PAPER, anchor="lm")
        d.text((cols[1], cy), f"{r['close']:,.2f}", font=f("int700" if i == 0 else "int600", 22), fill=PAPER, anchor="rm")
        c = UP if r["pts"] >= 0 else DOWN
        d.text((cols[2], cy), f"{r['pts']:+,.2f}", font=f("int600", 21), fill=c, anchor="rm")
        t = f"{abs(r['pct']):.2f}%"
        pf = f("int700", 21)
        d.text((cols[3], cy), t, font=pf, fill=c, anchor="rm")
        arrow(d, cols[3] - d.textlength(t, font=pf) - 24, cy, r["pts"] >= 0, c, 12)
    _dark_footer(d, th, "Close vs previous close · Data: NSE via Yahoo Finance · For information only, not investment advice", L)
    im.save(path, quality=93)


def indices(rows, path):
    """Every major Nifty index at the close: value, 1D points, 1D %, 1W / 1M / 1Y %. Sorted by 1D %."""
    im = Image.new("RGB", (W, H), INK)
    noise = Image.effect_noise((W, H), 9).convert("L")
    im = Image.blend(im, Image.merge("RGB", [noise] * 3), 0.04)
    d = ImageDraw.Draw(im)
    L = 40
    th = _dark_header(d, "NIFTY INDICES", L)
    n50 = next((r for r in rows if r["name"] == "Nifty 50"), rows[0])
    when = datetime.strptime(n50["date"], "%Y-%m-%d").strftime("%a %d %b %Y").upper()
    d.text((L, 104), f"ALL MAJOR NIFTY INDICES · CLOSE ON {when}", font=f("int700", 20), fill=th["sub"])
    d.text((L - 2, 190), "Nifty indices ", font=f("bri800", 58), fill=PAPER, anchor="ls")
    d.text((L + d.textlength("Nifty indices ", font=f("bri800", 58)), 190), "at the close", font=f("iserif", 64),
           fill=th["tag"], anchor="ls")
    ups = sum(1 for r in rows if r["d1"] > 0 and "VIX" not in r["name"])
    downs = sum(1 for r in rows if r["d1"] < 0 and "VIX" not in r["name"])
    d.text((L, 214), f"{ups} indices up · {downs} down · sorted by today's % change", font=f("int500", 21), fill=th["sub"])
    y = 262
    hf = f("int700", 15)
    cols = (L + 10, L + 470, L + 600, L + 700, L + 800, L + 900, W - L - 8)   # name, close, pts, 1D, 1W, 1M, 1Y
    d.text((cols[0], y), "INDEX", font=hf, fill=th["sub"])
    for lab, x in zip(("CLOSE", "PTS", "1D", "1W", "1M", "1Y"), cols[1:]):
        d.text((x, y), lab, font=hf, fill=th["sub"], anchor="ra")
    y += 26
    rh = min(34, (H - 116 - y) / max(len(rows), 1))
    nf = f("int600", 17)
    for i, r in enumerate(rows):
        yy = y + i * rh
        if i % 2 == 0:
            d.rounded_rectangle([L, yy, W - L, yy + rh - 3], radius=6, fill=INK2)
        cy = yy + (rh - 3) / 2
        bold = r["name"] == "Nifty 50"
        d.text((cols[0], cy), r["name"], font=f("int700" if bold else "int600", 19), fill=th["tag"] if bold else PAPER, anchor="lm")
        c = r["close"]
        d.text((cols[1], cy), f"{c:,.2f}" if c < 10000 else f"{c:,.0f}", font=f("int600", 18), fill=PAPER, anchor="rm")
        pts = r["close"] - r["prev"]
        col = UP if r["d1"] >= 0 else DOWN
        d.text((cols[2], cy), f"{pts:+,.0f}" if abs(pts) >= 100 else f"{pts:+,.1f}", font=nf, fill=col, anchor="rm")
        d.text((cols[3], cy), f"{r['d1']:+.2f}%", font=f("int700", 17), fill=col, anchor="rm")
        for key, x in zip(("w1", "m1", "y1"), cols[4:]):
            v = r.get(key)
            txt = "–" if v is None else (f"{v:+.0f}%" if abs(v) >= 99.95 else f"{v:+.1f}%")
            d.text((x, cy), txt, font=nf, fill=th["sub"] if v is None else (UP if v >= 0 else DOWN), anchor="rm")
    _dark_footer(d, th, "Index value at close · PTS = change in points today · Data: NSE via Yahoo Finance · Not investment advice", L)
    im.save(path, quality=93)
