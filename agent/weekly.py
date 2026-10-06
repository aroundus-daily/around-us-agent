"""Around Us - weekly markets recap Reel (Saturday morning). No AI, zero Claude credits.

What it shows (Friday close vs the previous Friday close):
  * Nifty 50: weekly change, and each day's close drawn as a line
  * Top 10 gainers and top 10 losers of the week among the Nifty 50
  * Rupee vs 8 currencies over the week (ECB reference rates, checked against the daily 2-of-3 rate)

Data rules: same verified Nifty data as the daily posts (daily.get_nifty: stale or implausible stocks
dropped, at least 45 of 50 must pass). The reel is only made when the latest session is within the
last 3 days (so a holiday week still works, an outage does not). The rupee scene is dropped if the
ECB weekly figure disagrees with the verified daily rate by more than 0.6%.
"""
import json
import os
import sys
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import daily  # noqa: E402
import reel  # noqa: E402

VERSION = "weekly v1 (markets recap reel)"
FILE_MP4, FILE_COVER = "13-weekly.mp4", "13-weekly-cover.jpg"
MAX_MB = 18   # jsDelivr serves GitHub files up to 20 MB


def week_label(start, end):
    s, e = datetime.strptime(start, "%Y-%m-%d"), datetime.strptime(end, "%Y-%m-%d")
    if s.month == e.month:
        return f"{s.day}–{e.day} {e.strftime('%b %Y')}"
    return f"{s.strftime('%-d %b')} – {e.strftime('%-d %b %Y')}"


def weekly_fx(verified):
    """ECB rates for the last ~9 days -> [{code, country, inr, prev, w1}], checked against the verified daily rate."""
    codes = ",".join(c for c, _ in daily.FX)
    start = (datetime.now(daily.IST) - timedelta(days=9)).strftime("%Y-%m-%d")
    code, js = daily.http("GET", f"https://api.frankfurter.app/{start}..?from=INR&to={codes}")
    if code != 200 or not js.get("rates"):
        return [], ["Rupee scene skipped: ECB rates not reachable"]
    days = sorted(js["rates"])
    if len(days) < 2:
        return [], ["Rupee scene skipped: not enough ECB days"]
    last, first = js["rates"][days[-1]], js["rates"][days[0]]
    checked = {v["code"]: v["inr"] for v in verified}
    out, notes = [], []
    for c, country in daily.FX:
        mult = 100 if c == "JPY" else 1
        if not (last.get(c) and first.get(c)):
            continue
        inr, prev = mult / last[c], mult / first[c]
        if c in checked and abs(inr - checked[c]) / checked[c] > 0.006:
            notes.append(f"{c}: ECB {inr:.2f} differs from the verified rate {checked[c]:.2f}; left out")
            continue
        out.append({"code": c, "country": country, "inr": inr, "prev": prev, "w1": (inr - prev) / prev * 100})
    if len(out) < 5:
        return [], notes + ["Rupee scene skipped: fewer than 5 currencies verified"]
    return out, notes + [f"Rupee: ECB {days[0]} → {days[-1]}"]


def get_week():
    notes = []
    data, problems = daily.get_nifty()
    notes += problems[:6]
    if not data:
        return None, notes + ["Nifty data not available; no weekly reel"]
    ix = data["index"]
    today = datetime.now(daily.IST).date()
    if datetime.strptime(ix["date"], "%Y-%m-%d").date() < today - timedelta(days=3):
        return None, notes + [f"Latest session is {ix['date']}, too old; no weekly reel"]
    hist, latest = daily.yahoo_history("^NSEI")
    if not hist:
        return None, notes + ["Nifty history not available; no weekly reel"]
    if latest and latest[0] == hist[-1][0]:
        hist[-1] = (latest[0], latest[1])
    end_d = datetime.strptime(ix["date"], "%Y-%m-%d")
    base_target = (end_d - timedelta(days=7)).strftime("%Y-%m-%d")
    older = [(d, c) for d, c in hist if d <= base_target]
    if not older:
        return None, notes + ["No previous-week close; no weekly reel"]
    prev_d, prev_c = older[-1]
    closes = [(prev_d, prev_c)] + [(d, c) for d, c in hist if prev_d < d <= ix["date"]]
    if len(closes) < 3:
        return None, notes + ["Fewer than 2 sessions this week; no weekly reel"]
    w1 = (ix["close"] - prev_c) / prev_c * 100
    rows = [r for r in data["rows"] if r.get("w1") is not None]
    gainers = sorted([r for r in rows if r["w1"] > 0], key=lambda r: -r["w1"])[:10]
    losers = sorted([r for r in rows if r["w1"] < 0], key=lambda r: r["w1"])[:10]
    fx_today, _, fx_problems = daily.get_fx()
    fx, fx_notes = weekly_fx(fx_today) if fx_today else ([], ["Rupee scene skipped: daily rate not verified"])
    notes += fx_notes
    start = closes[1][0]
    return {"week": {"start": start, "end": ix["date"], "label": week_label(start, ix["date"])},
            "index": {"close": ix["close"], "prev_week": prev_c, "w1": w1, "closes": closes},
            "gainers": gainers, "losers": losers, "fx": fx, "stocks": len(rows)}, notes


def caption(w):
    ix = w["index"]
    g, l = w["gainers"][:1], w["losers"][:1]
    parts = [f"Markets this week ({w['week']['label']}): Nifty 50 {'up' if ix['w1'] >= 0 else 'down'} "
             f"{abs(ix['w1']):.2f}% to {ix['close']:,.2f}."]
    if g:
        parts.append(f"Top gainer {g[0]['sym']} +{g[0]['w1']:.1f}%.")
    if l:
        parts.append(f"Top loser {l[0]['sym']} {l[0]['w1']:.1f}%.")
    usd = next((x for x in w["fx"] if x["code"] == "USD"), None)
    if usd:
        parts.append(f"Rupee {'weaker' if usd['w1'] > 0 else 'stronger'} vs the dollar at {usd['inr']:.2f}.")
    return (" ".join(parts) + "\nఈ వారం మార్కెట్లు: నిఫ్టీ, టాప్ గెయినర్లు, లూజర్లు, రూపాయి.\n"
            "For information only, not investment advice. Data: NSE via Yahoo Finance, ECB.\n"
            "#AroundUs #Nifty50 #StockMarket #WeeklyRecap #Rupee")


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
    marker = os.path.join(folder, "weekly_pending.txt")
    summary_path = os.path.join(folder, "weekly_summary.txt")
    if any(v.get("name") == "weekly" for v in queue.values()):
        daily.log("weekly reel already made today")
        open(marker, "w").close()
        open(summary_path, "w").close()
        return
    handle = daily.ig_handle() or "@around_us.daily"
    keys = []
    try:
        w, notes = get_week()
    except Exception as e:
        w, notes = None, [f"error: {str(e)[:150]}"]
    if w:
        mp4 = os.path.join(folder, FILE_MP4)
        cover = os.path.join(folder, FILE_COVER)
        secs, size = reel.weekly_markets(w, mp4, cover, handle=handle)
        if size > MAX_MB * 1024 * 1024:
            notes.append(f"Reel is {size / 1e6:.1f} MB, over the {MAX_MB} MB limit; not queued")
            os.remove(mp4)
        else:
            key = f"{day}/{FILE_MP4}"
            queue[key] = {"name": "weekly", "kind": "reel", "caption": caption(w), "status": "waiting",
                          "files": [FILE_MP4], "cover": FILE_COVER}
            with open(qpath, "w") as fh:
                json.dump(queue, fh, ensure_ascii=False, indent=1)
            keys.append(key)
            notes.insert(0, f"Reel: {secs:.0f} s, {size / 1e6:.1f} MB, {w['stocks']}/50 stocks, "
                            f"{len(w['fx'])} currencies")
    lines = [f"📈 Around Us · weekly markets reel · {now.strftime('%A, %d %b')}", ""]
    lines += ["Ready: Nifty week + top 10 gainers/losers" + (" + rupee" if w and w["fx"] else "")] if keys \
        else ["No weekly reel this time."]
    if notes:
        lines += ["", "Notes:"] + ["• " + n for n in notes[:10]]
    with open(summary_path, "w") as fh:
        fh.write("\n".join(lines))
    with open(marker, "w") as fh:
        fh.write("\n".join(keys))
    daily.log("weekly saved", keys, notes)


if __name__ == "__main__":
    main()
