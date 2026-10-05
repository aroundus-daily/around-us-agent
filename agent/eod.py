"""Around Us - end-of-day post: Nifty 50 top 10 gainers and top 10 losers (weekdays, after 3:30 PM close).

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
    data, problems = daily.get_nifty()
    if not data:
        daily.tg("sendMessage", chat_id=daily.TG_CHAT,
                 text="⚠️ End-of-day movers post skipped: " + "; ".join(problems[-3:]))
        return
    if data["index"]["date"] != day:
        daily.tg("sendMessage", chat_id=daily.TG_CHAT,
                 text=f"📅 No market session today ({day}), so no gainers/losers post.")
        return
    folder = os.path.join(daily.POSTS_DIR, day)
    os.makedirs(folder, exist_ok=True)
    path = os.path.join(folder, "09-movers.jpg")
    slides.movers(data, path)
    qpath = os.path.join(folder, "queue.json")
    try:
        with open(qpath) as fh:
            queue = json.load(fh)
    except Exception:
        queue = {}
    key = f"{day}/09-movers.jpg"
    queue[key] = {"name": "movers", "caption": CAPTION, "status": "waiting"}
    with open(qpath, "w") as fh:
        json.dump(queue, fh, ensure_ascii=False, indent=1)
    with open(os.path.join(folder, "eod_pending.txt"), "w") as fh:
        fh.write(key)
    if problems:
        daily.log("notes:", problems[:6])
    daily.log("saved", key)


if __name__ == "__main__":
    main()
