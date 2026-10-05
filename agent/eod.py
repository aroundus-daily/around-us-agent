"""Around Us - end-of-day posts (weekdays, after the 3:30 PM close):
  1. Rupee today        8 currencies, 3 sources must agree (posted even on market holidays)
  2. Nifty 50           index + all 50 stocks: price, 1D / 1W / 1M / 1Y
  3. Nifty 50 movers    top 10 gainers and top 10 losers

No AI, zero Claude credits. Uses the same verified Nifty data as the morning post (daily.get_nifty):
stale or implausible stocks are dropped, and the post is skipped if fewer than 45 stocks pass.
Only publishes if the data is from TODAY's session (so holidays are skipped).
"""
import json
import os
import sys
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import daily  # noqa: E402
import slides  # noqa: E402

CAPTIONS = {
    "rupee": daily.DEFAULT_CAPTIONS["rupee"],
    "nifty": daily.DEFAULT_CAPTIONS["nifty"],
}
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
