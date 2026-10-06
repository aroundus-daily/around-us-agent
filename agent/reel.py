"""Around Us - animated Reel renderer (1080x1920, 30 fps) built with Pillow + ffmpeg. No AI.

weekly_markets(data, mp4_path, cover_path) makes the Saturday "This week in markets" reel:
  scene 1  Nifty 50: value counts up, weekly change chip, the week's closes draw as a line   (0-4.5 s)
  scene 2  Top 10 gainers of the week: bars grow in one by one                             (4.5-10 s)
  scene 3  Top 10 losers of the week                                                       (10-15.5 s)
  scene 4  Rupee this week: 8 currencies with the weekly move, then the sign-off           (15.5-20 s)
Every frame is drawn in Python and piped straight into ffmpeg (H.264 + AAC, faststart), which is what
Instagram Reels expects. Audio = quiet background music from music.py (or assets/music.* if you add one).
"""
import glob
import os
import subprocess
from datetime import datetime

from PIL import Image, ImageDraw

import music
import slides
from slides import f, arrow, has_glyph

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))

W, H, FPS = 1080, 1920, 30
BG = (18, 20, 25)
CARD = (30, 33, 40)
PAPER = slides.PAPER
MUTE = (160, 162, 168)
UP, DOWN, NEAR = slides.UP, slides.DOWN, slides.NEAR
ACC = (242, 194, 48)
BLUE = (86, 132, 255)


# ---------------------------------------------------------------- helpers
def ease(t):
    """Ease-out cubic, clamped to 0..1."""
    t = max(0.0, min(1.0, t))
    return 1 - (1 - t) ** 3


def lerp(a, b, t):
    return a + (b - a) * t


def fmt_inr(v, dec=2):
    return f"{v:,.{dec}f}"


def rs(font):
    return "₹" if has_glyph(font, "₹") else "Rs "


def header(d, label):
    x, y0 = 86, 110
    for r in (26, 17, 8):
        d.ellipse([x - r, y0 - r, x + r, y0 + r], outline=PAPER, width=3)
    d.ellipse([x - 6, y0 - 6, x + 6, y0 + 6], fill=NEAR)
    d.text((128, 82), "around us", font=f("bri800", 48), fill=PAPER)
    tf = f("int700", 26)
    tw = d.textlength(label, font=tf)
    d.rounded_rectangle([W - 60 - tw - 52, 82, W - 60, 138], radius=28, fill=ACC)
    d.text((W - 60 - tw - 26, 95), label, font=tf, fill=slides.INK)


def footer(d, handle, alpha=1.0):
    col = tuple(int(lerp(BG[i], MUTE[i], alpha)) for i in range(3))
    d.line([(60, H - 150), (W - 60, H - 150)], fill=(50, 54, 62), width=2)
    d.text((60, H - 126), handle, font=f("int600", 32), fill=col)
    d.text((W - 60, H - 126), "every Saturday", font=f("iserif", 36), fill=col, anchor="ra")


def fade_in(d, box, t):
    """Darken a region by (1 - t) so content under it fades in."""
    if t >= 1:
        return
    ov = Image.new("RGBA", (box[2] - box[0], box[3] - box[1]), BG + (int(255 * (1 - ease(t))),))
    d._image.paste(ov, (box[0], box[1]), ov)


# ---------------------------------------------------------------- scenes
def scene_nifty(im, d, data, t, handle):
    ix = data["index"]
    header(d, "WEEKLY RECAP")
    wk = data["week"]
    d.text((60, 230), "THIS WEEK IN MARKETS", font=f("int700", 30), fill=ACC)
    d.text((60, 300), f"{wk['label']}", font=f("bri800", 64), fill=PAPER)
    # Nifty value counting up
    d.text((60, 470), "NIFTY 50 · FRIDAY CLOSE", font=f("int700", 28), fill=MUTE)
    k = ease(t / 1.6)
    val = lerp(ix["prev_week"], ix["close"], k)
    d.text((56, 600), fmt_inr(val), font=f("bri800", 128), fill=PAPER, anchor="ls")
    # weekly change chip slides in from the right
    if t > 1.2:
        s = ease((t - 1.2) / 0.6)
        up = ix["w1"] >= 0
        col = UP if up else DOWN
        chip = f"{abs(ix['close'] - ix['prev_week']):,.2f}  ({abs(ix['w1']):.2f}%) this week"
        cf = f("int700", 36)
        cw = d.textlength(chip, font=cf) + 90
        cx = 60 + (1 - s) * 400
        d.rounded_rectangle([cx, 640, cx + cw, 712], radius=16, fill=col)
        arrow(d, cx + 24, 676, up, PAPER, 22)
        d.text((cx + 62, 676), chip, font=cf, fill=PAPER, anchor="lm")
    # the week's closes, drawn progressively
    closes = data["index"]["closes"]           # [(date, close)] incl. previous Friday first
    top, bot, left, right = 830, 1310, 100, W - 100
    d.rounded_rectangle([60, 770, W - 60, 1440], radius=28, fill=CARD)
    d.text((90, 800), "DAY BY DAY", font=f("int700", 26), fill=MUTE)
    vals = [c for _, c in closes]
    lo, hi = min(vals), max(vals)
    pad = (hi - lo) * 0.15 or 1
    lo, hi = lo - pad, hi + pad
    n = len(closes)
    pts = [(left + (right - left) * i / max(n - 1, 1), bot - (v - lo) / (hi - lo) * (bot - top)) for i, v in enumerate(vals)]
    prog = ease((t - 0.4) / 2.2) * (n - 1)
    for gy in (top, (top + bot) / 2, bot):
        d.line([(left, gy), (right, gy)], fill=(48, 52, 60), width=2)
    seg = []
    for i in range(n):
        if i <= prog:
            seg.append(pts[i])
        elif i - 1 < prog:
            fr = prog - (i - 1)
            seg.append((lerp(pts[i - 1][0], pts[i][0], fr), lerp(pts[i - 1][1], pts[i][1], fr)))
            break
    if len(seg) >= 2:
        d.line(seg, fill=ACC, width=8, joint="curve")
    for i, (px, py) in enumerate(pts):
        if i <= prog:
            d.ellipse([px - 11, py - 11, px + 11, py + 11], fill=ACC if i in (0, n - 1) else (120, 100, 40))
            lab = datetime.strptime(closes[i][0], "%Y-%m-%d").strftime("%a")
            d.text((px, bot + 34), lab.upper(), font=f("int600", 24), fill=MUTE, anchor="mm")
            vt = f"{vals[i]:,.0f}"
            d.text((px, py - 34), vt, font=f("int600", 24), fill=PAPER, anchor="mm")
    d.text((90, 1396), f"Week high {max(vals):,.0f}  ·  low {min(vals):,.0f}  ·  first point = last Friday's close",
           font=f("int500", 24), fill=MUTE)
    # teaser cards: the week's best and worst stock
    if t > 2.6:
        a = ease((t - 2.6) / 0.6)
        g = data["gainers"][:1]
        l = data["losers"][:1]
        cw = (W - 120 - 20) / 2
        for i, (lab, row, col) in enumerate((("WEEK'S BEST", g, UP), ("WEEK'S WORST", l, DOWN))):
            x0 = 60 + i * (cw + 20)
            yy = 1480 + (1 - a) * 40
            d.rounded_rectangle([x0, yy, x0 + cw, yy + 170], radius=24, fill=CARD)
            d.text((x0 + 28, yy + 30), lab, font=f("int700", 24), fill=MUTE)
            if row:
                d.text((x0 + 28, yy + 92), row[0]["sym"][:11], font=f("int700", 40), fill=PAPER, anchor="lm")
                d.text((x0 + 28, yy + 140), f"{row[0]['w1']:+.1f}% this week", font=f("bri800", 32), fill=col, anchor="lm")
            else:
                d.text((x0 + 28, yy + 100), "none", font=f("int600", 32), fill=MUTE, anchor="lm")
        fade_in(d, (60, 1470, W - 60, 1700), a)
    footer(d, handle)


def scene_movers(im, d, rows, t, title, up, handle):
    header(d, "WEEKLY RECAP")
    col = UP if up else DOWN
    d.text((60, 230), "THIS WEEK IN MARKETS", font=f("int700", 30), fill=ACC)
    d.text((60, 300), title, font=f("bri800", 64), fill=PAPER)
    d.text((60, 380), "Nifty 50 stocks · Friday close vs last Friday", font=f("int500", 28), fill=MUTE)
    top, rh = 470, 118
    maxpct = max((abs(r["w1"]) for r in rows), default=1) or 1
    barx0, barx1 = 420, W - 60 - 210
    for i, r in enumerate(rows[:10]):
        yy = top + i * rh
        s = ease((t - 0.25 - i * 0.14) / 0.7)
        if s <= 0:
            continue
        d.rounded_rectangle([60, yy, W - 60, yy + rh - 12], radius=18, fill=CARD)
        d.text((88, yy + 30), f"{i + 1}", font=f("int700", 30), fill=MUTE, anchor="lm")
        d.text((140, yy + 30), r["sym"][:11], font=f("int700", 34), fill=PAPER, anchor="lm")
        d.text((140, yy + 74), f"{rs(f('int500', 24))}{r['close']:,.2f}", font=f("int500", 24), fill=MUTE, anchor="lm")
        bw = (barx1 - barx0) * abs(r["w1"]) / maxpct * s
        d.rounded_rectangle([barx0, yy + 38, barx0 + max(bw, 6), yy + 68], radius=8, fill=col)
        pct = abs(r["w1"]) * s
        d.text((W - 88, yy + 53), f"{'+' if up else '−'}{pct:.1f}%", font=f("bri800", 42), fill=col, anchor="rm")
    footer(d, handle)


def scene_rupee(im, d, fx, t, handle, week_label):
    header(d, "WEEKLY RECAP")
    d.text((60, 230), "THIS WEEK IN MARKETS", font=f("int700", 30), fill=ACC)
    d.text((60, 300), "Rupee this week", font=f("bri800", 64), fill=PAPER)
    d.text((60, 380), "Rupees for 1 unit · Friday vs last Friday", font=f("int500", 28), fill=MUTE)
    top, rh = 470, 128
    names = {"USD": "US dollar", "EUR": "Euro", "GBP": "British pound", "JPY": "Japanese yen · 100",
             "CNY": "Chinese yuan", "CAD": "Canadian dollar", "SGD": "Singapore dollar", "AED": "UAE dirham"}
    rf = f("int700", 44)
    for i, r in enumerate(fx[:8]):
        yy = top + i * rh
        s = ease((t - 0.2 - i * 0.12) / 0.6)
        if s <= 0:
            continue
        d.rounded_rectangle([60, yy, W - 60, yy + rh - 14], radius=18, fill=CARD)
        d.text((92, yy + 40), r["code"], font=f("int700", 38), fill=PAPER, anchor="lm")
        d.text((92, yy + 82), names.get(r["code"], ""), font=f("int500", 26), fill=MUTE, anchor="lm")
        val = lerp(r["prev"], r["inr"], s)
        d.text((640, yy + 57), f"{rs(rf)}{val:.2f}", font=rf, fill=PAPER, anchor="rm")
        ch = r["w1"]
        # rupee weaker when the price of a foreign unit rises
        col = DOWN if ch > 0.005 else UP if ch < -0.005 else MUTE
        txt = f"{abs(ch) * s:.2f}%"
        pf = f("int700", 36)
        d.text((W - 92, yy + 57), txt, font=pf, fill=col, anchor="rm")
        if col != MUTE:
            arrow(d, W - 92 - d.textlength(txt, font=pf) - 34, yy + 57, ch > 0, col, 18)
    if t > 1.6:
        a = ease((t - 1.6) / 0.8)
        col = tuple(int(lerp(BG[i], MUTE[i], a)) for i in range(3))
        d.text((60, 1540), "Red = rupee weaker over the week · Green = stronger", font=f("int500", 26), fill=col)
        col2 = tuple(int(lerp(BG[i], PAPER[i], a)) for i in range(3))
        d.text((60, 1610), f"Follow {handle} for the daily numbers", font=f("int600", 34), fill=col2)
    footer(d, handle)


# ---------------------------------------------------------------- render
def weekly_markets(data, mp4_path, cover_path, handle="@around_us.daily"):
    """Render the reel; returns (seconds, bytes)."""
    scenes = [("nifty", 4.5), ("gainers", 5.5), ("losers", 5.5)]
    if data.get("fx"):
        scenes.append(("rupee", 4.5))
    fade = 0.35
    total = sum(s for _, s in scenes)

    watermark = os.environ.get("REEL_WATERMARK", "")

    def draw_scene(name, t):
        im = Image.new("RGB", (W, H), BG)
        d = ImageDraw.Draw(im)
        if watermark:
            d.rectangle([0, 0, W, 54], fill=(200, 40, 35))
            d.text((W / 2, 27), watermark, font=f("int700", 28), fill=(255, 255, 255), anchor="mm")
        if name == "nifty":
            scene_nifty(im, d, data, t, handle)
        elif name == "gainers":
            scene_movers(im, d, data["gainers"], t, "Top 10 gainers", True, handle)
        elif name == "losers":
            scene_movers(im, d, data["losers"], t, "Top 10 losers", False, handle)
        else:
            scene_rupee(im, d, data["fx"], t, handle, data["week"]["label"])
        return im

    def frame_at(gt):
        acc = 0.0
        for i, (name, dur) in enumerate(scenes):
            if gt < acc + dur or i == len(scenes) - 1:
                local = gt - acc
                im = draw_scene(name, local)
                if i > 0 and local < fade:               # cross-fade from the previous scene's last frame
                    prev_name, prev_dur = scenes[i - 1]
                    prev = draw_scene(prev_name, prev_dur)
                    im = Image.blend(prev, im, ease(local / fade))
                return im
            acc += dur
        return draw_scene(scenes[-1][0], scenes[-1][1])

    # cover = the Nifty scene fully drawn
    frame_at(3.6).save(cover_path, quality=92)

    # soundtrack: quiet ambient background music composed in music.py (no sound effects), or your own
    # track from assets/music.* if present
    events = []
    own = sorted(glob.glob(os.path.join(ROOT, "assets", "music.*")))
    wav = os.path.splitext(mp4_path)[0] + "-audio.wav"
    music.make_track(total, events, wav, music=not own)
    audio_in = ["-i", wav]
    if own:   # user's own track, looped/trimmed to the reel, faded out, with the effects mixed on top
        audio_in = ["-stream_loop", "-1", "-i", own[0], "-i", wav]
    afilter = []
    if own:
        afilter = ["-filter_complex",
                   f"[1:a]volume=0.35,atrim=0:{total},afade=t=in:d=1,afade=t=out:st={total - 2}:d=2[m];"
                   "[2:a][m]amix=inputs=2:duration=first:normalize=0[a]", "-map", "0:v", "-map", "[a]"]
    nframes = int(total * FPS)
    cmd = (["ffmpeg", "-y", "-loglevel", "error",
            "-f", "rawvideo", "-pix_fmt", "rgb24", "-s", f"{W}x{H}", "-r", str(FPS), "-i", "-"]
           + audio_in + afilter +
           ["-shortest", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-preset", "medium", "-crf", "24",
            "-profile:v", "high", "-level", "4.1", "-movflags", "+faststart", "-c:a", "aac", "-b:a", "128k",
            "-ar", "44100", "-r", str(FPS), mp4_path])
    proc = subprocess.Popen(cmd, stdin=subprocess.PIPE)
    for n in range(nframes):
        proc.stdin.write(frame_at(n / FPS).tobytes())
    proc.stdin.close()
    proc.wait()
    try:
        os.remove(wav)
    except OSError:
        pass
    if proc.returncode != 0 or not os.path.exists(mp4_path):
        raise RuntimeError("ffmpeg failed")
    return total, os.path.getsize(mp4_path)
