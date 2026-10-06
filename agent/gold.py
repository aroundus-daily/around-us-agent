"""Around Us - Gold rate carousel (every day, late morning).

ONE Instagram post with TWO slides:
  1. Gold rate in Andhra Pradesh, last 10 days (Vijayawada, Visakhapatnam, Tirupati, Guntur, Nellore)
  2. Gold rate in Telangana, last 10 days (Hyderabad, Warangal)
Each slide shows only the state name (no city names): today's 24K / 22K / 18K, price for
1 g / 8 g / 10 g, a 10-day 22K chart with high, low and 10-day change, and the 10-day table.
The state's rate = the rate its cities share; if a city differs, Telegram tells you (not the slide).

No AI, zero Claude credits. Accuracy rules:
  * Main source: GoodReturns city pages (per gram, last 10 days).
  * Cross-check: BankBazaar's STATE page (22K, and 18K when shown) must agree within 0.5%.
    A city that disagrees is dropped and Telegram shows both numbers. If BankBazaar can't be
    reached, the post is still sent to Telegram but marked "1 source only", so you decide.
  * Sanity checks: 24K / 22K ratio 1.08-1.10, no day moves more than 8%.
  * A city page that is not updated today (e.g. stuck on an old date) is left out.
  * Only posts once today's rate is published (2nd run at 1:17 PM). Never twice a day.
  * If only one state has good data, it goes out as a single image instead of a carousel.
Rates exclude GST, TCS and making charges (said on every slide).
"""
import html
import json
import os
import re
import sys
from collections import Counter
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import daily  # noqa: E402
import slides  # noqa: E402

VERSION = "gold v2 (AP + Telangana carousel)"
STATES = [
    {"name": "Andhra Pradesh", "short": "AP", "file": "08-gold-ap.jpg", "check": "andhra-pradesh",
     "cities": [("Vijayawada", "vijayawada"), ("Visakhapatnam", "visakhapatnam"), ("Tirupati", "tirupati"),
                ("Guntur", "guntur"), ("Nellore", "nellore")]},
    {"name": "Telangana", "short": "TG", "file": "08-gold-tg.jpg", "check": "telangana",
     "cities": [("Hyderabad", "hyderabad"), ("Warangal", "warangal")]},
]
TELUGU = {"Andhra Pradesh": "ఆంధ్రప్రదేశ్", "Telangana": "తెలంగాణ"}
MAIN_URL = "https://www.goodreturns.in/gold-rates/{slug}.html"
CHECK_URL = "https://www.bankbazaar.com/gold-rate-{slug}.html"
GOLD_PATH = os.path.join(daily.ROOT, "data", "gold.json")
BROWSER = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                         "(KHTML, like Gecko) Chrome/126.0 Safari/537.36",
           "Accept": "text/html,application/xhtml+xml", "Accept-Language": "en-IN,en;q=0.9"}
GRAM_MIN, GRAM_MAX = 5000, 40000      # plausible price of 1 gram (rejects 8 g / 10 g tables)
RATIO_MIN, RATIO_MAX = 1.08, 1.10     # 24K / 22K (theory: 24/22 = 1.0909)
TOLERANCE = 0.005                     # sources must agree within 0.5%

MONTHS = {m: i for i, m in enumerate(
    ["jan", "feb", "mar", "apr", "may", "jun", "jul", "aug", "sep", "oct", "nov", "dec"], 1)}
MON = r"(Jan|Feb|Mar|Apr|May|Jun|Jul|Aug|Sep|Sept|Oct|Nov|Dec)[a-z]*\.?"
DATE_RES = [
    (re.compile(r"\b(\d{1,2})(?:st|nd|rd|th)?[\s\-/]+" + MON + r",?[\s\-/]+(20\d\d)\b", re.I), "dmy"),
    (re.compile(r"\b" + MON + r"\s+(\d{1,2})(?:st|nd|rd|th)?,?\s+(20\d\d)\b", re.I), "mdy"),
    (re.compile(r"\b(\d{1,2})[/\-.](\d{1,2})[/\-.](20\d\d)\b"), "num"),
]
AMOUNT_RE = re.compile(r"(?<![\d.,])(\d{1,3}(?:,\d{2,3})+|\d{4,7})(?:\.\d{1,2})?(?![\d,])")


def page_text(raw):
    """HTML -> plain text, one table row / block per line. Works for tables and div layouts."""
    t = raw.decode("utf-8", "ignore") if isinstance(raw, bytes) else raw
    t = re.sub(r"(?is)<(script|style|noscript|svg)\b.*?</\1>", " ", t)
    t = re.sub(r"(?i)</(tr|li|p|div|h\d|table|section)>|<br\s*/?>", "\n", t)
    t = re.sub(r"(?i)</t[dh]>", " | ", t)
    t = html.unescape(re.sub(r"<[^>]+>", " ", t))
    return re.sub(r"[ \t\r\f\v\xa0]+", " ", t)


def find_dates(text, today):
    """All dates in the text within the last 20 days -> [(start, end, 'YYYY-MM-DD')]."""
    out = []
    for rx, kind in DATE_RES:
        for m in rx.finditer(text):
            try:
                if kind == "dmy":
                    d, mo, y = int(m.group(1)), MONTHS[m.group(2)[:3].lower()], int(m.group(3))
                elif kind == "mdy":
                    mo, d, y = MONTHS[m.group(1)[:3].lower()], int(m.group(2)), int(m.group(3))
                else:
                    d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
                dt = datetime(y, mo, d).date()
            except (ValueError, KeyError):
                continue
            if timedelta(0) <= today - dt <= timedelta(days=20):
                out.append((m.start(), m.end(), dt.isoformat()))
    out.sort()
    keep, last_end = [], -1
    for s, e, iso in out:          # drop overlapping matches
        if s >= last_end:
            keep.append((s, e, iso))
            last_end = e
    return keep


def windows(text, today, size=600, amount_re=None):
    """For every date, the text that follows it (up to the next date) with the amounts in it."""
    amount_re = amount_re or AMOUNT_RE
    dates = find_dates(text, today)
    for i, (s, e, iso) in enumerate(dates):
        stop = dates[i + 1][0] if i + 1 < len(dates) else len(text)
        chunk = text[e:min(stop, e + size)]
        chunk = re.sub(r"\([^)]{0,24}\)", " ", chunk)       # drop "(+104)" / "(800 ▼)" change figures
        amounts = [float(a.replace(",", "")) for a in amount_re.findall(chunk)]
        yield iso, amounts


def parse_main(raw, today):
    """GoodReturns-style page -> {date: {'k24','k22','k18'}} per gram, using the 24K/22K ratio
    to recognise the pair (so the column order or HTML layout doesn't matter)."""
    votes = {}
    for iso, amounts in windows(page_text(raw), today):
        grams = [a for a in amounts if GRAM_MIN <= a < GRAM_MAX]
        for i, a in enumerate(grams):
            pair = next(((a, b) for b in grams[i + 1:i + 4] if RATIO_MIN <= a / b <= RATIO_MAX), None) or \
                   next(((b, a) for b in grams[i + 1:i + 4] if RATIO_MIN <= b / a <= RATIO_MAX), None)
            if pair:
                k18 = next((c for c in grams if 1.20 <= pair[1] / c <= 1.24), None)
                votes.setdefault(iso, []).append((pair[0], pair[1], k18))
                break
    series = {}
    for iso, v in votes.items():
        (k24, k22), n = Counter((a, b) for a, b, _ in v).most_common(1)[0]
        k18 = next((c for a, b, c in v if (a, b) == (k24, k22) and c), None)
        series[iso] = {"k24": k24, "k22": k22, "k18": k18}
    return series


def check_22k(raw, series, today, key="k22"):
    """BankBazaar-style page: for each date, does any 22K amount (1 g, 8 g or 10 g) agree with ours?
    Returns (dates matched, dates compared, {date: their value} for mismatches)."""
    theirs = {}
    for iso, amounts in windows(page_text(raw), today):
        if iso in series:
            theirs.setdefault(iso, []).extend(amounts)
    matched, compared, bad = 0, 0, {}
    for iso, amounts in theirs.items():
        ours = series[iso].get(key)
        if not ours:
            continue
        cands = [a / dv for a in amounts for dv in (1, 8, 10) if GRAM_MIN <= a / dv < GRAM_MAX]
        if not cands:
            continue
        compared += 1
        best = min(cands, key=lambda c: abs(c - ours))
        if abs(best - ours) / ours <= TOLERANCE:
            matched += 1
        else:
            bad[iso] = best
    return matched, compared, bad


def sane(series):
    """Problems with a series, or [] if it looks right."""
    probs, prev = [], None
    for iso in sorted(series):
        r = series[iso]
        if not RATIO_MIN <= r["k24"] / r["k22"] <= RATIO_MAX:
            probs.append(f"{iso}: 24K/22K ratio {r['k24'] / r['k22']:.3f}")
        if prev and abs(r["k22"] / prev - 1) > 0.08:
            probs.append(f"{iso}: 22K moved more than 8% in a day")
        prev = r["k22"]
    return probs


def fetch(url):
    code, raw = daily.http("GET", url, headers=BROWSER, timeout=30, raw=True)
    if code != 200 or not raw:
        return None, f"HTTP {code}"
    return raw, ""


def get_state(state, today):
    """One state's cities -> (card data or None, notes)."""
    notes, cities = [], []
    check_raw, check_err = fetch(CHECK_URL.format(slug=state["check"]))
    for name, slug in state["cities"]:
        raw, err = fetch(MAIN_URL.format(slug=slug))
        if not raw:
            notes.append(f"{name}: GoodReturns not reachable ({err})")
            continue
        series = parse_main(raw, today)
        if len(series) < 5:
            notes.append(f"{name}: no recent rates on the page ({len(series)} days in the last 20), left out")
            continue
        if max(series) < (today - timedelta(days=3)).isoformat():
            notes.append(f"{name}: page not updated since {max(series)}, left out")
            continue
        probs = sane(series)
        if probs:
            notes.append(f"{name}: failed sanity check: {probs[0]}")
            continue
        series = dict(sorted(series.items())[-10:])
        if check_raw:
            matched, compared, bad = check_22k(check_raw, series, today)
            latest = max(series)
            if latest in bad:
                notes.append(f"{name}: sources DISAGREE on 22K for {latest}: GoodReturns "
                             f"₹{series[latest]['k22']:,.0f} vs BankBazaar ₹{bad[latest]:,.0f} per gram. City dropped.")
                continue
            check = f"{matched}/{compared} days match BankBazaar {state['short']}" if compared \
                else "BankBazaar had no matching dates"
            verified = compared > 0 and matched >= max(1, compared - 1)
        else:
            check, verified = f"BankBazaar not reachable ({check_err})", False
        cities.append({"name": name, "series": series, "verified": verified, "check": check})
        daily.log(f"gold {name}: {len(series)} days, latest {max(series)}, {check}")
    if not cities:
        return None, notes
    latest = max(max(c["series"]) for c in cities)
    keep = []
    for c in cities:
        if max(c["series"]) != latest:
            notes.append(f"{c['name']}: no rate for {latest} yet, left out")
            continue
        keep.append(c)
    cities = keep
    # the slide's main numbers = the rate most cities share (all of them, on a normal day)
    counts = Counter(json.dumps(c["series"], sort_keys=True) for c in cities)
    ref = json.loads(counts.most_common(1)[0][0])
    same = len(counts) == 1
    if not same:
        odd = [c["name"] for c in cities if c["series"] != ref]
        notes.append(f"{state['name']}: rates differ between cities; slide shows the rate most cities share "
                     f"(different: {', '.join(odd)})")
    k18_check = ""
    if check_raw and ref[latest].get("k18"):
        m18, c18, _ = check_22k(check_raw, {latest: ref[latest]}, today, key="k18")
        k18_check = "18K matches" if m18 else ("18K differs, hidden" if c18 else "")
        if c18 and not m18:
            ref[latest]["k18"] = None
    return {"state": state["name"], "short": state["short"], "file": state["file"], "cities": cities,
            "series": ref, "latest": latest, "same": same,
            "verified": any(c["verified"] for c in cities), "k18_check": k18_check}, notes


def inr(n):
    """Indian digit grouping: 149180 -> '1,49,180'."""
    s = f"{int(round(n))}"
    if len(s) <= 3:
        return s
    head, tail = s[:-3], s[-3:]
    parts = []
    while len(head) > 2:
        parts.insert(0, head[-2:])
        head = head[:-2]
    if head:
        parts.insert(0, head)
    return ",".join(parts + [tail])


def caption(cards):
    t = cards[0]["series"][cards[0]["latest"]]
    names = [c["state"] for c in cards]
    tel = ", ".join(TELUGU[n] for n in names)
    same_all = all(c["series"][c["latest"]] == t for c in cards)
    if len(cards) == 2 and same_all:
        top = (f"Gold rate in Andhra Pradesh and Telangana, last 10 days. Today 24K ₹{inr(t['k24'] * 10)} and "
               f"22K ₹{inr(t['k22'] * 10)} per 10 grams in both states. Swipe for Telangana.")
    elif len(cards) == 2:
        top = "Gold rate in Andhra Pradesh and Telangana, last 10 days, per 10 grams. Swipe for Telangana."
    else:
        top = (f"Gold rate in {names[0]}, last 10 days. Today 24K ₹{inr(t['k24'] * 10)} and "
               f"22K ₹{inr(t['k22'] * 10)} per 10 grams.")
    return (top + "\n" + tel + ("\u200c" if tel.endswith("\u0c4d") else "") + "లో గత 10 రోజుల బంగారం ధరలు.\n"
            "Rates exclude GST, TCS and making charges. Check with your jeweller before buying.\n"
            "#AroundUs #GoldRate #GoldPriceToday " + " ".join("#" + n.replace(" ", "") for n in names))


def main():
    for k in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_ADMIN_CHAT_ID"):
        if not os.environ.get(k):
            raise SystemExit(f"{k} missing")
    now = datetime.now(daily.IST)
    day = now.strftime("%Y-%m-%d")
    daily.log(VERSION, day)
    folder = os.path.join(daily.POSTS_DIR, day)
    os.makedirs(folder, exist_ok=True)
    qpath = os.path.join(folder, "queue.json")
    try:
        with open(qpath) as fh:
            queue = json.load(fh)
    except Exception:
        queue = {}
    marker = os.path.join(folder, "gold_pending.txt")
    summary_path = os.path.join(folder, "gold_summary.txt")
    if any(v.get("name") == "gold" for v in queue.values()):
        daily.log("gold post already made today, nothing to do")
        open(marker, "w").close()
        open(summary_path, "w").close()
        return
    handle = daily.ig_handle()
    if handle:
        slides.HANDLE = handle
    final_run = os.environ.get("GOLD_FINAL_RUN") == "1"
    cards, notes = [], []
    for state in STATES:
        try:
            card, n = get_state(state, now.date())
        except Exception as e:      # one state's problem never blocks the other
            card, n = None, [f"{state['name']}: error {str(e)[:120]}"]
        notes += n
        if card and card["latest"] != day:
            notes.append(f"{state['name']}: today's rate not published yet (latest {card['latest']})."
                         + ("" if final_run else " Will try again at 1:17 PM."))
            card = None
        if card:
            cards.append(card)
    keys = []
    if cards and (len(cards) == len(STATES) or final_run):
        for i, card in enumerate(cards):
            hint = None
            if len(cards) == 2:
                hint = ("Swipe for Telangana", "next") if i == 0 else ("Andhra Pradesh on the first slide", "back")
            slides.gold_state(card, os.path.join(folder, card["file"]), inr, hint=hint)
        files = [c["file"] for c in cards]
        key = f"{day}/{files[0]}"
        queue[key] = {"name": "gold", "caption": caption(cards), "status": "waiting", "files": files}
        with open(qpath, "w") as fh:
            json.dump(queue, fh, ensure_ascii=False, indent=1)
        keys.append(key)
        try:
            with open(GOLD_PATH) as fh:
                hist = json.load(fh)
        except Exception:
            hist = {}
        for c in cards:
            hist.setdefault(c["state"], {}).update(c["series"])
            hist[c["state"]] = dict(sorted(hist[c["state"]].items())[-60:])
        os.makedirs(os.path.dirname(GOLD_PATH), exist_ok=True)
        with open(GOLD_PATH, "w") as fh:
            json.dump(hist, fh, indent=1)
        lines = [f"🪙 Around Us · gold rate · {now.strftime('%A, %d %b')}",
                 f"{len(cards)} slide{'s' if len(cards) > 1 else ''} in one post: "
                 + " + ".join(c["state"] for c in cards), ""]
        for c in cards:
            ok = "✅ cross-checked with BankBazaar" if c["verified"] else "⚠️ 1 source only, check the numbers"
            lines.append(f"{c['state']}: {ok}" + (f" ({c['k18_check']})" if c["k18_check"] else ""))
            lines += [f"   • {x['name']}: {x['check']}" for x in c["cities"]]
    elif cards:
        notes.append("Waiting for both states before posting; will try again at 1:17 PM.")
    if not keys:
        lines = [f"🪙 Around Us · gold rate · {now.strftime('%A, %d %b')}", "", "No gold post this time."]
    if notes:
        lines += ["", "Notes:"] + ["• " + n for n in notes[:10]]
    with open(summary_path, "w") as fh:
        fh.write("\n".join(lines))
    with open(marker, "w") as fh:
        fh.write("\n".join(keys))
    # first run with nothing ready yet: stay quiet, the 1:17 PM run reports
    if not keys and not final_run:
        open(summary_path, "w").close()
    daily.log("gold saved", keys, notes)


if __name__ == "__main__":
    main()
