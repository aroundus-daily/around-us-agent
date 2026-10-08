"""Around Us - end-of-day posts (weekdays, after the 3:30 PM close):
  1. Rupee today        8 currencies, 3 sources must agree (posted even on market holidays)
  2. Nifty 50           index + all 50 stocks: price, 1D / 1W / 1M / 1Y
  3. Nifty 50 movers    top 10 gainers and top 10 losers
  4. Nifty 50 sessions  today's close + the previous 14 sessions, points and % change each day
  5. Nifty indices      every major NSE index at the close: value, 1D points, 1D %, 1W, 1M, 1Y

No AI, zero Claude credits. Uses the same verified Nifty data as the morning post (daily.get_nifty):
stale or implausible stocks are dropped, and the post is skipped if fewer than 45 stocks pass.
Only publishes if the data is from TODAY's session (so holidays are skipped).
"""
import json
import os
import sys
import time
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import daily  # noqa: E402
import slides  # noqa: E402

CAPTIONS = {
    "rupee": daily.DEFAULT_CAPTIONS["rupee"],
    "nifty": daily.DEFAULT_CAPTIONS["nifty"],
}
CAPTION_SESSIONS = ("Nifty 50 today and the previous 14 sessions: close, change in points and %.\n"
                    "నిఫ్టీ 50 గత 15 రోజుల ముగింపులు.\n"
                    "For information only, not investment advice.\n#AroundUs #Nifty50 #StockMarket")
CAPTION_INDICES = ("How every major Nifty index closed today: value, change in points and %, and the 1 week, "
                   "1 month and 1 year move.\nనిఫ్టీ ఇండెక్స్‌లు ఈరోజు ఎలా ముగిశాయి.\n"
                   "For information only, not investment advice.\n#AroundUs #Nifty #BankNifty #StockMarket")
# NSE indices on Yahoo Finance: name -> symbols to try, in order (Yahoo's naming is inconsistent)
INDICES = [
    ("Nifty 50", ["^NSEI"]), ("Nifty Next 50", ["^NSMIDCP", "NIFTY_NEXT_50.NS"]), ("Nifty 100", ["^CNX100"]),
    ("Nifty 200", ["^CNX200"]), ("Nifty 500", ["^CNX500"]), ("Nifty Midcap 50", ["^NSEMDCP50"]),
    ("Nifty Midcap 100", ["NIFTY_MIDCAP_100.NS", "^CNXMIDCAP"]), ("Nifty Smallcap 100", ["^CNXSC"]),
    ("Nifty Bank", ["^NSEBANK"]), ("Nifty Fin Services", ["NIFTY_FIN_SERVICE.NS", "^CNXFIN"]),
    ("Nifty Private Bank", ["NIFTY_PVT_BANK.NS"]), ("Nifty PSU Bank", ["^CNXPSUBANK"]), ("Nifty IT", ["^CNXIT"]),
    ("Nifty Auto", ["^CNXAUTO"]), ("Nifty Pharma", ["^CNXPHARMA"]), ("Nifty Healthcare", ["NIFTY_HEALTHCARE.NS"]),
    ("Nifty FMCG", ["^CNXFMCG"]), ("Nifty Metal", ["^CNXMETAL"]), ("Nifty Realty", ["^CNXREALTY"]),
    ("Nifty Energy", ["^CNXENERGY"]), ("Nifty Oil & Gas", ["NIFTY_OIL_AND_GAS.NS"]), ("Nifty Infra", ["^CNXINFRA"]),
    ("Nifty Media", ["^CNXMEDIA"]), ("Nifty Consumption", ["^CNXCONSUM"]), ("Nifty Consumer Durables", ["NIFTY_CONSR_DURBL.NS"]),
    ("Nifty MNC", ["^CNXMNC"]), ("Nifty PSE", ["^CNXPSE"]), ("Nifty Commodities", ["^CNXCMDT"]), ("Nifty Services", ["^CNXSERVICE"]),
    ("India VIX", ["^INDIAVIX"]),
]


def nifty_sessions(day, n=15):
    """Today's close and the previous n-1 sessions with points and % change each day. None unless today is a session."""
    hist, latest = daily.yahoo_history("^NSEI")
    if not hist:
        return None, "Nifty history not available"
    if latest and hist and latest[0] == hist[-1][0]:
        hist[-1] = (latest[0], latest[1])
    elif latest and hist and latest[0] > hist[-1][0]:
        hist.append((latest[0], latest[1]))
    if hist[-1][0] != day:
        return None, f"no session today (latest {hist[-1][0]})"
    if len(hist) < n + 1:
        return None, "not enough history"
    rows = []
    for i in range(len(hist) - n, len(hist)):
        d, c = hist[i]
        p = hist[i - 1][1]
        rows.append({"date": d, "close": c, "pts": c - p, "pct": (c - p) / p * 100})
    if any(abs(r["pct"]) > 15 for r in rows):
        return None, "implausible daily move in history"
    return {"rows": rows, "first_prev": hist[len(hist) - n - 1]}, ""


def nifty_indices(day):
    """Every index in INDICES with today's close. Returns (rows sorted by 1-day %, problems)."""
    rows, problems = [], []
    for name, syms in INDICES:
        ch = None
        for sym in syms:
            ch = daily.changes(*daily.yahoo_history(sym))
            time.sleep(0.25)
            if ch and ch["d1"] is not None:
                break
        if not ch or ch["d1"] is None:
            problems.append(f"{name}: no data")
            continue
        if ch["date"] != day:
            problems.append(f"{name}: stale ({ch['date']})")
            continue
        limit = 40 if "VIX" in name else 15
        if abs(ch["d1"]) > limit or ch["close"] <= 0:
            problems.append(f"{name}: implausible move {ch['d1']:.1f}%")
            continue
        rows.append({"name": name, **ch})
    vix = [r for r in rows if "VIX" in r["name"]]
    rows = sorted([r for r in rows if "VIX" not in r["name"]], key=lambda r: -r["d1"]) + vix
    return rows, problems


CAPTION = ("Nifty 50 at the close: today's top 10 gainers and top 10 losers, with price and change.\n"
           "నిఫ్టీ 50 ఈరోజు టాప్ గెయినర్లు, లూజర్లు.\n"
           "For information only, not investment advice.\n#AroundUs #Nifty50 #StockMarket")


def main():
    for k in ("TELEGRAM_BOT_TOKEN", "TELEGRAM_ADMIN_CHAT_ID"):
        if not os.environ.get(k):
            raise SystemExit(f"{k} missing")
    now = datetime.now(daily.IST)
    day = now.strftime("%Y-%m-%d")
    daily.log("EOD movers", day)
    if now.weekday() >= 5:
        daily.log("weekend, nothing to do")
        return
    handle = daily.ig_handle()
    if handle:
        slides.HANDLE = handle
    folder = os.path.join(daily.POSTS_DIR, day)
    os.makedirs(folder, exist_ok=True)
    made, notes = [], []

    # 1. Rupee today (currency markets trade even on NSE holidays)
    try:
        fx, fx_note, fx_problems = daily.get_fx()
        notes += fx_problems[:4]
        if fx:
            p = os.path.join(folder, "10-rupee.jpg")
            slides.rupee(fx, p, note=fx_note)
            made.append(("rupee", p, CAPTIONS["rupee"]))
        else:
            notes.append("Rupee post skipped: sources did not agree")
    except Exception as e:
        notes.append(f"Rupee post skipped: {str(e)[:120]}")

    # 2 + 3. Nifty 50 list and movers (only if there was a market session today)
    try:
        data, problems = daily.get_nifty()
        notes += problems[:6]
        if not data:
            notes.append("Nifty posts skipped")
        elif data["index"]["date"] != day:
            notes.append(f"No market session today ({day}): Nifty posts skipped")
        else:
            p = os.path.join(folder, "11-nifty.jpg")
            slides.nifty(data, p)
            made.append(("nifty", p, CAPTIONS["nifty"]))
            p = os.path.join(folder, "12-movers.jpg")
            slides.movers(data, p)
            made.append(("movers", p, CAPTION))
    except Exception as e:
        notes.append(f"Nifty posts skipped: {str(e)[:120]}")

    # 4. Nifty 50: today + previous 14 sessions
    try:
        sess, why = nifty_sessions(day)
        if sess:
            p = os.path.join(folder, "15-sessions.jpg")
            slides.nifty_sessions(sess, p)
            made.append(("sessions", p, CAPTION_SESSIONS))
        else:
            notes.append(f"Nifty sessions post skipped: {why}")
    except Exception as e:
        notes.append(f"Nifty sessions post skipped: {str(e)[:120]}")

    # 5. All Nifty indices at the close
    try:
        idx_rows, idx_problems = nifty_indices(day)
        notes += idx_problems[:8]
        if len(idx_rows) >= 12:
            p = os.path.join(folder, "16-indices.jpg")
            slides.indices(idx_rows, p)
            made.append(("indices", p, CAPTION_INDICES))
        else:
            notes.append(f"Nifty indices post skipped: only {len(idx_rows)} indices had today's close")
    except Exception as e:
        notes.append(f"Nifty indices post skipped: {str(e)[:120]}")

    qpath = os.path.join(folder, "queue.json")
    try:
        with open(qpath) as fh:
            queue = json.load(fh)
    except Exception:
        queue = {}
    keys = []
    for name, p, cap in made:
        key = f"{day}/{os.path.basename(p)}"
        if queue.get(key, {}).get("status") not in ("posted", "skipped"):
            queue[key] = {"name": name, "caption": cap, "status": "waiting"}
        keys.append(key)
    with open(qpath, "w") as fh:
        json.dump(queue, fh, ensure_ascii=False, indent=1)
    with open(os.path.join(folder, "eod_pending.txt"), "w") as fh:
        fh.write("\n".join(keys))
    summary = (f"🌇 Around Us · evening posts · {now.strftime('%A, %d %b')}\n\n"
               f"{len(made)} posts ready: " + (", ".join(n for n, _, _ in made) or "none")
               + ("\n\nNotes:\n" + "\n".join("• " + x for x in notes[:8]) if notes else "")
               + "\n\nTap ✅ Post under any post to publish it.")
    with open(os.path.join(folder, "eod_summary.txt"), "w") as fh:
        fh.write(summary)
    daily.log("saved", keys, notes)


if __name__ == "__main__":
    main()
