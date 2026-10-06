"""Around Us - Silver rate carousel (runs in the same job as the gold post, right after it).

ONE Instagram post with TWO slides:
  1. Silver rate in Andhra Pradesh, last 10 days (Vijayawada, Visakhapatnam, Tirupati, Guntur, Nellore)
  2. Silver rate in Telangana, last 10 days (Hyderabad, Warangal)
Each slide shows only the state name: today's rate per kg / 100 g / 10 g / 1 g, the change from
yesterday, a 10-day chart with high, low and 10-day change, and the full 10-day table.

No AI, zero Claude credits. Accuracy rules (same idea as gold):
  * Main source: GoodReturns city pages (10-day table with 10 g, 100 g and 1 kg columns; a date is
    accepted only when those three columns agree with each other).
  * Cross-check: BankBazaar's STATE page (per gram) must agree within 0.5%. A city that disagrees is
    dropped and Telegram shows both numbers. If BankBazaar can't be reached, the post is still sent
    but marked "1 source only".
  * Sanity: 1 kg between Rs 30,000 and Rs 10,00,000; no day moves more than 10%.
  * A city page not updated in 3 days is left out. Only posts once today's rate is published
    (2nd run at 1:17 PM). Never twice a day.
Rates exclude GST and making charges (said on every slide).
"""
import json
import os
import re
import sys
from collections import Counter
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import daily  # noqa: E402
import gold  # noqa: E402  (shared page parsing: page_text, windows, fetch, inr)
import slides  # noqa: E402

VERSION = "silver v1 (AP + Telangana carousel)"
STATES = [
    {"name": "Andhra Pradesh", "short": "AP", "file": "09-silver-ap.jpg", "check": "andhra-pradesh",
     "cities": [("Vijayawada", "vijayawada"), ("Visakhapatnam", "visakhapatnam"), ("Tirupati", "tirupati"),
                ("Guntur", "guntur"), ("Nellore", "nellore")]},
    {"name": "Telangana", "short": "TG", "file": "09-silver-tg.jpg", "check": "telangana",
     "cities": [("Hyderabad", "hyderabad"), ("Warangal", "warangal")]},
]
MAIN_URL = "https://www.goodreturns.in/silver-rates/{slug}.html"
CHECK_URL = "https://www.bankbazaar.com/silver-rate-{slug}.html"
SILVER_PATH = os.path.join(daily.ROOT, "data", "silver.json")
KG_MIN, KG_MAX = 30000, 1000000      # plausible price of 1 kg
TOLERANCE = 0.005
# silver per gram is a 3-digit number (e.g. 245), so the check page needs a wider amount pattern
SMALL_RE = re.compile(r"(?<![\d.,])(\d{1,3}(?:,\d{2,3})+|\d{2,7})(?:\.\d{1,2})?(?![\d,])")


def parse_main(raw, today):
    """GoodReturns silver page -> {date: kg_price}. A date counts only when the 1 kg figure is backed
    by its 100 g (kg/10) or 10 g (kg/100) figure in the same row, so stray numbers can't be mistaken."""
    votes = {}
    for iso, amounts in gold.windows(gold.page_text(raw), today):
        kgs = [a for a in amounts if KG_MIN <= a <= KG_MAX]
        for kg in kgs:
            backed = any(abs(a - kg / 10) <= 1 for a in amounts) or any(abs(a - kg / 100) <= 0.5 for a in amounts)
            if backed:
                votes.setdefault(iso, []).append(kg)
                break
    return {iso: Counter(v).most_common(1)[0][0] for iso, v in votes.items()}


def check(raw, series, today):
    """BankBazaar silver page (per gram, or per kg): does their figure agree with our kg price per date?
    Returns (matched, compared, {date: their kg price} for mismatches)."""
    theirs = {}
    for iso, amounts in gold.windows(gold.page_text(raw), today, amount_re=SMALL_RE):
        if iso in series:
            theirs.setdefault(iso, []).extend(amounts)
    matched, compared, bad = 0, 0, {}
    for iso, amounts in theirs.items():
        ours = series[iso]
        cands = [a * mult for a in amounts for mult in (1000, 100, 10, 1) if KG_MIN <= a * mult <= KG_MAX]
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
    probs, prev = [], None
    for iso in sorted(series):
        v = series[iso]
        if prev and abs(v / prev - 1) > 0.10:
            probs.append(f"{iso}: silver moved more than 10% in a day")
        prev = v
    return probs


def get_state(state, today):
    notes, cities = [], []
    check_raw, check_err = gold.fetch(CHECK_URL.format(slug=state["check"]))
    for name, slug in state["cities"]:
        raw, err = gold.fetch(MAIN_URL.format(slug=slug))
        if not raw:
            notes.append(f"{name}: GoodReturns silver page not reachable ({err})")
            continue
        series = parse_main(raw, today)
        if len(series) < 5:
            notes.append(f"{name}: no recent silver rates on the page ({len(series)} days in the last 20), left out")
            continue
        if max(series) < (today - timedelta(days=3)).isoformat():
            notes.append(f"{name}: silver page not updated since {max(series)}, left out")
            continue
        probs = sane(series)
        if probs:
            notes.append(f"{name}: failed sanity check: {probs[0]}")
            continue
        series = dict(sorted(series.items())[-10:])
        if check_raw:
            matched, compared, bad = check(check_raw, series, today)
            latest = max(series)
            if latest in bad:
                notes.append(f"{name}: sources DISAGREE on silver for {latest}: GoodReturns "
                             f"₹{series[latest]:,.0f}/kg vs BankBazaar ₹{bad[latest]:,.0f}/kg. City dropped.")
                continue
            chk = f"{matched}/{compared} days match BankBazaar {state['short']}" if compared \
                else "BankBazaar had no matching dates"
            verified = compared > 0 and matched >= max(1, compared - 1)
        else:
            chk, verified = f"BankBazaar not reachable ({check_err})", False
        cities.append({"name": name, "series": series, "verified": verified, "check": chk})
        daily.log(f"silver {name}: {len(series)} days, latest {max(series)}, {chk}")
    if not cities:
        return None, notes
    latest = max(max(c["series"]) for c in cities)
    cities = [c for c in cities if max(c["series"]) == latest or
              notes.append(f"{c['name']}: no silver rate for {latest} yet, left out")]
    counts = Counter(json.dumps(c["series"], sort_keys=True) for c in cities)
    ref = json.loads(counts.most_common(1)[0][0])
    if len(counts) > 1:
        odd = [c["name"] for c in cities if c["series"] != ref]
        notes.append(f"{state['name']}: silver rates differ between cities; slide shows the rate most "
                     f"cities share (different: {', '.join(odd)})")
    return {"state": state["name"], "short": state["short"], "file": state["file"], "cities": cities,
            "series": ref, "latest": latest, "same": len(counts) == 1,
            "verified": any(c["verified"] for c in cities)}, notes


def caption(cards):
    kg = cards[0]["series"][cards[0]["latest"]]
    names = [c["state"] for c in cards]
    tel = ", ".join(gold.TELUGU[n] for n in names)
    same_all = all(c["series"][c["latest"]] == kg for c in cards)
    if len(cards) == 2 and same_all:
        top = (f"Silver rate in Andhra Pradesh and Telangana, last 10 days. Today ₹{gold.inr(kg)} per kg "
               f"(₹{gold.inr(kg / 1000)} per gram) in both states. Swipe for Telangana.")
    elif len(cards) == 2:
        top = "Silver rate in Andhra Pradesh and Telangana, last 10 days, per kg. Swipe for Telangana."
    else:
        top = f"Silver rate in {names[0]}, last 10 days. Today ₹{gold.inr(kg)} per kg (₹{gold.inr(kg / 1000)} per gram)."
    return (top + "\n" + tel + ("‌" if tel.endswith("్") else "") + "లో గత 10 రోజుల వెండి ధరలు.\n"
            "Rates exclude GST and making charges. Check with your jeweller before buying.\n"
            "#AroundUs #SilverRate #SilverPriceToday " + " ".join("#" + n.replace(" ", "") for n in names))


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
    marker = os.path.join(folder, "silver_pending.txt")
    summary_path = os.path.join(folder, "silver_summary.txt")
    if any(v.get("name") == "silver" for v in queue.values()):
        daily.log("silver post already made today, nothing to do")
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
        except Exception as e:
            card, n = None, [f"{state['name']}: error {str(e)[:120]}"]
        notes += n
        if card and card["latest"] != day:
            notes.append(f"{state['name']}: today's silver rate not published yet (latest {card['latest']})."
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
            slides.silver_state(card, os.path.join(folder, card["file"]), gold.inr, hint=hint)
        files = [c["file"] for c in cards]
        key = f"{day}/{files[0]}"
        queue[key] = {"name": "silver", "caption": caption(cards), "status": "waiting", "files": files}
        with open(qpath, "w") as fh:
            json.dump(queue, fh, ensure_ascii=False, indent=1)
        keys.append(key)
        try:
            with open(SILVER_PATH) as fh:
                hist = json.load(fh)
        except Exception:
            hist = {}
        for c in cards:
            hist.setdefault(c["state"], {}).update(c["series"])
            hist[c["state"]] = dict(sorted(hist[c["state"]].items())[-60:])
        os.makedirs(os.path.dirname(SILVER_PATH), exist_ok=True)
        with open(SILVER_PATH, "w") as fh:
            json.dump(hist, fh, indent=1)
        lines = [f"🥈 Around Us · silver rate · {now.strftime('%A, %d %b')}",
                 f"{len(cards)} slide{'s' if len(cards) > 1 else ''} in one post: "
                 + " + ".join(c["state"] for c in cards), ""]
        for c in cards:
            ok = "✅ cross-checked with BankBazaar" if c["verified"] else "⚠️ 1 source only, check the numbers"
            lines.append(f"{c['state']}: {ok}")
            lines += [f"   • {x['name']}: {x['check']}" for x in c["cities"]]
    elif cards:
        notes.append("Waiting for both states before posting; will try again at 1:17 PM.")
    if not keys:
        lines = [f"🥈 Around Us · silver rate · {now.strftime('%A, %d %b')}", "", "No silver post this time."]
    if notes:
        lines += ["", "Notes:"] + ["• " + n for n in notes[:10]]
    with open(summary_path, "w") as fh:
        fh.write("\n".join(lines))
    with open(marker, "w") as fh:
        fh.write("\n".join(keys))
    if not keys and not final_run:
        open(summary_path, "w").close()
    daily.log("silver saved", keys, notes)


if __name__ == "__main__":
    main()
