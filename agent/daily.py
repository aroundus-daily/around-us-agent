"""Around Us - daily agent v10 (simple, low cost).

Every morning it makes 5-7 SEPARATE Instagram posts (one image + one caption each):
  1. India in the world        5-10 lines
  2. Rupee today               8 currencies (3 sources must agree)
  3. Markets at close          top 10 exchanges (weekdays only; MARKETS_POST=0 turns it off)
  4. Top 10 in India           10 lines
  5. Across the South          5-10 lines
  6. Andhra today              5-10 lines

Accuracy level: MEDIUM. Every line comes from a real published headline. Its source and date are taken
from that headline by the code (not by AI). Lines whose numbers don't match their headline are replaced by
the headline itself. If Claude gives fewer than 5 lines, the code fills up with real headlines.
Cost: one Claude call per day.
"""
import hashlib
import html
import json
import os
import re
import sys
import time
import urllib.error
import urllib.parse
import urllib.request
import xml.etree.ElementTree as ET
from datetime import datetime, timedelta, timezone
from email.utils import parsedate_to_datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import slides  # noqa: E402

VERSION = "v18 (+ 4 PM gainers & losers post)"
ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEEN_PATH = os.path.join(ROOT, "data", "seen.json")
MKT_PATH = os.path.join(ROOT, "data", "markets.json")
POSTS_DIR = os.path.join(ROOT, "posts")
IST = timezone(timedelta(hours=5, minutes=30))

ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "").strip()
TG_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
TG_CHAT = os.environ.get("TELEGRAM_ADMIN_CHAT_ID", "").strip()
IG_TOKEN = os.environ.get("IG_ACCESS_TOKEN", "").strip()
MODEL = os.environ.get("CLAUDE_MODEL", "").strip()
MARKETS_POST = os.environ.get("MARKETS_POST", "1") != "0"

SECTIONS = ("world", "india", "south", "andhra")
MIN_LINES, MAX_LINES = 5, 10
TARGET = {"world": 8, "india": 10, "south": 8, "andhra": 8}


def gn(q, days=1, lang="en"):
    hl, ceid = ("te", "IN:te") if lang == "te" else ("en-IN", "IN:en")
    return (f"https://news.google.com/rss/search?q={urllib.parse.quote(q + f' when:{days}d')}"
            f"&hl={hl}&gl=IN&ceid={ceid}")


def topic(t):
    return f"https://news.google.com/rss/headlines/section/topic/{t}?hl=en-IN&gl=IN&ceid=IN:en"


# feed name -> (section, url)
FEEDS = {
    "INDIA_ABROAD": ("world", gn('India (US OR China OR EU OR Russia OR UN OR trade OR visa OR summit OR exports)')),
    "INDIA_GLOBAL": ("world", gn('India ranks OR India wins OR India tops OR "India becomes" OR India global', days=2)),
    "INDIA_DIPLO":  ("world", gn('India foreign minister OR MEA India OR India bilateral OR India agreement', days=2)),
    "INDIA_TRADE":  ("world", gn('India exports OR India imports OR India FTA OR India investment abroad', days=2)),
    "INDIANS_ABROAD": ("world", gn('Indian-origin OR Indians abroad OR NRI OR H-1B OR Gulf Indians', days=2)),
    "NATION":       ("india", topic("NATION")),
    "BUSINESS":     ("india", topic("BUSINESS")),
    "SCI_TECH":     ("india", topic("SCIENCE")),
    "SPORTS":       ("india", topic("SPORTS")),
    "CRICKET":      ("india", gn("India cricket OR IPL OR BCCI OR Team India")),
    "MARKETS_IN":   ("india", gn("Sensex OR Nifty OR stock market OR IPO")),
    "EV":           ("india", gn("electric vehicle India sales OR EV India", days=3)),
    "SOLAR":        ("india", gn("solar power India OR renewable energy India", days=3)),
    "MOVIES":       ("india", gn("box office collection", days=3)),
    "TECH_IN":      ("india", gn("India startup OR smartphone India OR UPI OR ISRO", days=2)),
    "TAMIL_NADU":   ("south", gn("Tamil Nadu OR Chennai")),
    "KARNATAKA":    ("south", gn("Karnataka OR Bengaluru")),
    "KERALA":       ("south", gn("Kerala OR Kochi OR Thiruvananthapuram")),
    "TELANGANA":    ("south", gn("Telangana OR Hyderabad")),
    "ANDHRA":       ("andhra", gn('"Andhra Pradesh"')),
    "ANDHRA_CITIES": ("andhra", gn("Amaravati OR Vijayawada OR Visakhapatnam OR Tirupati OR Guntur OR Nellore OR Kurnool")),
    "AP_PROJECTS":  ("andhra", gn("Polavaram OR Amaravati capital OR Andhra investment OR Visakhapatnam port", days=3)),
    "TOLLYWOOD":    ("andhra", gn("Telugu film box office OR Tollywood", days=3)),
    "ANDHRA_TE":    ("andhra", gn("ఆంధ్రప్రదేశ్", lang="te")),
}

FX = [("USD", "US dollar"), ("EUR", "Euro"), ("GBP", "British pound"), ("JPY", "Japanese yen · 100"),
      ("CNY", "Chinese yuan"), ("CAD", "Canadian dollar"), ("SGD", "Singapore dollar"), ("AED", "UAE dirham")]
EXCHANGES = [
    ("NYSE", "NYSE Composite", "^NYA"), ("Nasdaq", "Nasdaq Composite", "^IXIC"),
    ("Shanghai", "SSE Composite", "000001.SS"), ("Japan", "Nikkei 225", "^N225"),
    ("Euronext", "Euronext 100", "^N100"), ("Shenzhen", "SZSE Component", "399001.SZ"),
    ("Hong Kong", "Hang Seng", "^HSI"), ("NSE India", "Nifty 50", "^NSEI"),
    ("BSE India", "Sensex", "^BSESN"), ("London", "FTSE 100", "^FTSE"),
]


def log(*a):
    print(datetime.now(IST).strftime("%H:%M:%S"), *a, flush=True)


def http(method, url, headers=None, data=None, timeout=40, raw=False):
    if isinstance(data, (dict, list)):
        body = json.dumps(data).encode()
        headers = {"Content-Type": "application/json", **(headers or {})}
    else:
        body = data
    req = urllib.request.Request(url, data=body, method=method,
                                 headers={"User-Agent": "Mozilla/5.0 (AroundUsBot)", **(headers or {})})
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            content = r.read()
            return r.status, content if raw else json.loads(content.decode() or "{}")
    except urllib.error.HTTPError as e:
        content = e.read()
        try:
            return e.code, content if raw else json.loads(content.decode() or "{}")
        except Exception:
            return e.code, b"" if raw else {}
    except Exception as e:
        log("network error:", url[:70], e)
        return 0, b"" if raw else {}


def _fx_frankfurter():
    """ECB reference rates (+ previous day for % change)."""
    codes = ",".join(c for c, _ in FX)
    start = (datetime.now(IST) - timedelta(days=8)).strftime("%Y-%m-%d")
    code, js = http("GET", f"https://api.frankfurter.app/{start}..?from=INR&to={codes}")
    if code != 200 or not js.get("rates"):
        return None, None, None
    days = sorted(js["rates"])
    prev = js["rates"][days[-2]] if len(days) > 1 else None
    return js["rates"][days[-1]], prev, days[-1]


def _fx_erapi():
    code, js = http("GET", "https://open.er-api.com/v6/latest/INR")
    return js.get("rates") if code == 200 and js.get("result") == "success" else None


def _fx_fawaz():
    for url in ("https://cdn.jsdelivr.net/npm/@fawazahmed0/currency-api@latest/v1/currencies/inr.json",
                "https://latest.currency-api.pages.dev/v1/currencies/inr.json"):
        code, js = http("GET", url)
        if code == 200 and js.get("inr"):
            return {k.upper(): v for k, v in js["inr"].items()}
    return None


def get_fx():
    """Rupee price of 1 unit (100 JPY). Published only if 2+ independent sources agree within 1%."""
    ecb, ecb_prev, ecb_day = _fx_frankfurter()
    srcs = {"ECB": ecb, "ER-API": _fx_erapi(), "Currency-API": _fx_fawaz()}
    out, problems = [], []
    for c, country in FX:
        mult = 100 if c == "JPY" else 1
        vals = {n: mult / r[c] for n, r in srcs.items() if r and r.get(c)}
        if len(vals) < 2:
            problems.append(f"{c}: only {len(vals)} source")
            continue
        # keep the largest group of sources that agree within 0.6% (drops a single outlier)
        names = sorted(vals)
        best = []
        for n1 in names:
            grp = [n2 for n2 in names if abs(vals[n2] - vals[n1]) / vals[n1] * 100 <= 0.6]
            if len(grp) > len(best):
                best = grp
        if len(best) < 2:
            problems.append(f"{c}: sources disagree " + ", ".join(f"{n} {vals[n]:.2f}" for n in names))
            continue
        if len(best) < len(names):
            problems.append(f"{c}: ignored outlier " + ", ".join(f"{n} {vals[n]:.2f}" for n in names if n not in best))
        mid = sum(vals[n] for n in best) / len(best)
        vals = {n: vals[n] for n in best}
        ch = None
        if ecb and ecb_prev and c in ecb and c in ecb_prev:
            ch = ((mult / ecb[c]) - (mult / ecb_prev[c])) / (mult / ecb_prev[c]) * 100
        out.append(dict(code=c, country=country, inr=mid, change=ch, sources=sorted(vals)))
    # sanity: USD must be in a believable range
    usd = next((x for x in out if x["code"] == "USD"), None)
    if usd and not (60 < usd["inr"] < 150):
        problems.append(f"USD looks wrong: {usd['inr']:.2f}")
        out = []
    if len(out) < 5:
        return [], "", problems
    used = sorted({s for x in out for s in x["sources"]})
    note = f"Checked: {' + '.join(used)}" + (f" · ECB {ecb_day}" if ecb_day else "")
    return out, note, problems


def get_index(symbol):
    url = f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(symbol)}?range=7d&interval=1d"
    code, js = http("GET", url, timeout=20)
    try:
        closes = [c for c in js["chart"]["result"][0]["indicators"]["quote"][0]["close"] if c is not None]
        if len(closes) >= 2:
            return closes[-1], (closes[-1] - closes[-2]) / closes[-2] * 100
        if closes:
            return closes[-1], None
    except Exception:
        pass
    return None, None




def get_markets():
    """Last close + day change. Rows that look wrong are dropped, not shown."""
    try:
        with open(MKT_PATH) as fh:
            hist = json.load(fh)
    except Exception:
        hist = {}
    rows, problems = [], []
    for ex, idx, sym in EXCHANGES:
        v, ch = get_index(sym)
        bad = None
        if v is None:
            bad = "no data"
        elif ch is not None and abs(ch) > 8:
            bad = f"day change {ch:.1f}% looks wrong"
        elif sym in hist and abs(v - hist[sym]) / hist[sym] > 0.15:
            bad = f"value {v:,.0f} is >15% away from last stored {hist[sym]:,.0f}"
        if bad:
            problems.append(f"{ex}: {bad}")
            v, ch = None, None
        else:
            hist[sym] = v
        rows.append(dict(exchange=ex, index=idx, value=v, change=ch))
        time.sleep(0.4)
    ok = sum(r["value"] is not None for r in rows)
    log(f"markets: {ok}/10 indices")
    if ok >= 7:
        os.makedirs(os.path.dirname(MKT_PATH), exist_ok=True)
        with open(MKT_PATH, "w") as fh:
            json.dump(hist, fh, indent=0)
        return rows, problems
    return [], problems + [f"only {ok}/10 indices OK, markets slide skipped"]




# ---------------------------------------------------------------- Nifty 50 (no AI, zero credits)
# Backup list only (current as of 30 Sep 2026: Wipro out, BSE in). The live list is fetched from NSE daily.
NIFTY50_BACKUP = """ADANIENT ADANIPORTS APOLLOHOSP ASIANPAINT AXISBANK BAJAJ-AUTO BAJFINANCE BAJAJFINSV BEL BHARTIARTL
CIPLA COALINDIA DRREDDY EICHERMOT ETERNAL GRASIM HCLTECH HDFCBANK HDFCLIFE HINDALCO HINDUNILVR ICICIBANK INDIGO
INFY ITC JIOFIN JSWSTEEL KOTAKBANK LT M&M MARUTI MAXHEALTH NESTLEIND NTPC ONGC POWERGRID RELIANCE SBILIFE
SHRIRAMFIN SBIN SUNPHARMA TCS TATACONSUM TMPV TATASTEEL TECHM TITAN TRENT ULTRACEMCO BSE""".split()
NIFTY_POST = os.environ.get("NIFTY_POST", "1") != "0"


def nifty_constituents():
    """Official list from NSE (CSV). Falls back to the built-in list."""
    for url in ("https://www.niftyindices.com/IndexConstituent/ind_nifty50list.csv",
                "https://nsearchives.nseindia.com/content/indices/ind_nifty50list.csv",
                "https://archives.nseindia.com/content/indices/ind_nifty50list.csv"):
        code, raw = http("GET", url, raw=True, timeout=20)
        if code == 200 and isinstance(raw, (bytes, bytearray)) and raw:
            rows = [r.split(",") for r in raw.decode("utf-8", "ignore").splitlines()[1:] if r.strip()]
            syms = [r[2].strip() for r in rows if len(r) > 2 and r[2].strip()]
            if 45 <= len(syms) <= 55:
                return syms, "NSE official list"
    return NIFTY50_BACKUP, "built-in list (NSE list unreachable)"


def yahoo_history(symbol):
    """Daily closes for ~2 years [(date, close)], plus the most recent price Yahoo has (live during market hours)."""
    url = (f"https://query1.finance.yahoo.com/v8/finance/chart/{urllib.parse.quote(symbol)}"
           "?range=2y&interval=1d&includePrePost=false")
    code, js = http("GET", url, timeout=25)
    try:
        r = js["chart"]["result"][0]
        hist = [(datetime.fromtimestamp(t, IST).strftime("%Y-%m-%d"), c)
                for t, c in zip(r["timestamp"], r["indicators"]["quote"][0]["close"]) if c]
        meta = r.get("meta") or {}
        latest = None
        if meta.get("regularMarketPrice") and meta.get("regularMarketTime"):
            t = datetime.fromtimestamp(meta["regularMarketTime"], IST)
            latest = (t.strftime("%Y-%m-%d"), float(meta["regularMarketPrice"]), t)
        return hist, latest
    except Exception:
        return [], None


def market_open(t):
    return t.weekday() < 5 and (9, 15) <= (t.hour, t.minute) <= (15, 30)


def changes(hist, latest=None):
    """Most recent price vs 1 day, 1 week, 1 month, 1 year earlier (closest earlier trading day)."""
    hist = list(hist)
    live, when = False, ""
    if latest:
        ld_, lp, lt = latest
        if hist and ld_ > hist[-1][0]:
            hist.append((ld_, lp))             # today's live/close price newer than the last candle
        elif hist and ld_ == hist[-1][0]:
            hist[-1] = (ld_, lp)               # same day: use the most recent price
        now = datetime.now(IST)
        live = market_open(now) and ld_ == now.strftime("%Y-%m-%d") and (now - lt).total_seconds() < 3600
        when = lt.strftime("%H:%M")
    if len(hist) < 2:
        return None
    last_d, last = hist[-1]
    ld = datetime.strptime(last_d, "%Y-%m-%d")

    def base(days):
        target = (ld - timedelta(days=days)).strftime("%Y-%m-%d")
        older = [c for d, c in hist[:-1] if d <= target]
        return older[-1] if older else None

    def pct(b):
        return None if not b else (last - b) / b * 100
    return {"date": last_d, "close": last, "prev": hist[-2][1], "d1": pct(hist[-2][1]),
            "w1": pct(base(7)), "m1": pct(base(30)), "y1": pct(base(365)), "live": live, "time": when}


def get_nifty():
    """Index + all 50 stocks. Rows that fail checks are left out and reported."""
    problems = []
    idx = changes(*yahoo_history("^NSEI"))
    if not idx or not (5000 < idx["close"] < 100000) or abs(idx["d1"] or 0) > 10:
        return None, ["Nifty index data missing or implausible; Nifty post skipped"]
    syms, list_src = nifty_constituents()
    if "built-in" in list_src:
        problems.append("Nifty list: " + list_src)
    rows = []
    for sym in syms:
        ch = changes(*yahoo_history(sym + ".NS"))
        time.sleep(0.25)
        if not ch or ch["d1"] is None:
            problems.append(f"{sym}: no data")
            continue
        if ch["date"] != idx["date"]:
            problems.append(f"{sym}: stale data ({ch['date']})")
            continue
        if abs(ch["d1"]) > 20:  # beyond circuit limits: treat as bad data
            problems.append(f"{sym}: implausible 1-day move {ch['d1']:.1f}%")
            continue
        rows.append({"sym": sym, **ch})
    if len(rows) < 45:
        return None, problems + [f"only {len(rows)}/50 stocks verified; Nifty post skipped"]
    rows.sort(key=lambda r: -r["d1"])
    log(f"nifty: index {idx['close']:.2f} ({idx['d1']:+.2f}%), {len(rows)} stocks, {list_src}")
    return {"index": idx, "rows": rows, "list_src": list_src}, problems


# ---------------------------------------------------------------- news
def fetch_feed(name, section, url, limit=25):
    code, xml_bytes = http("GET", url, raw=True)
    if code != 200 or not xml_bytes:
        log(f"feed {name}: failed ({code})")
        return []
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        log(f"feed {name}: unreadable")
        return []
    out = []
    for it in root.iter("item"):
        title = html.unescape(it.findtext("title") or "").strip()
        src = it.find("source")
        outlet = (src.text or "").strip() if src is not None else ""
        if outlet and title.endswith(" - " + outlet):
            title = title[: -len(outlet) - 3].strip()
        if not title or not outlet:
            continue
        desc = html.unescape(it.findtext("description") or "")
        also = sorted({r.strip() for r in re.findall(r'<font color="#6f6f6f">([^<]+)</font>', desc)} - {outlet})
        try:
            pub = parsedate_to_datetime(it.findtext("pubDate") or "").astimezone(IST)
        except Exception:
            pub = None
        if pub and (datetime.now(IST) - pub).days > 7:
            continue
        out.append({"id": hashlib.sha1(title.lower().encode()).hexdigest()[:10], "feed": name, "section": section,
                    "title": title, "outlet": outlet, "also": also[:4], "link": it.findtext("link") or "",
                    "date": pub.strftime("%Y-%m-%d") if pub else ""})
        if len(out) >= limit:
            break
    log(f"feed {name}: {len(out)}")
    return out


def load_seen():
    try:
        with open(SEEN_PATH) as fh:
            data = json.load(fh)
    except Exception:
        data = {}
    cutoff = (datetime.now(IST) - timedelta(days=4)).isoformat()
    return {k: v for k, v in data.items() if v >= cutoff}


def save_seen(seen):
    os.makedirs(os.path.dirname(SEEN_PATH), exist_ok=True)
    with open(SEEN_PATH, "w") as fh:
        json.dump(seen, fh, indent=0, sort_keys=True)


def words(t):
    return set(re.findall(r"[a-z]{4,}", (t or "").lower()))


def similar(a, b):
    wa, wb = words(a), words(b)
    common = len(wa & wb)
    return bool(wa and wb) and common >= 3 and common / min(len(wa), len(wb)) >= 0.6


TELUGU_RE = re.compile(r"[\u0C00-\u0C7F]")  # images use English fonts only
INDIA_RE = re.compile(r"\bIndia(n|ns|'s)?\b|భారత", re.I)


def nums(t):
    return {n.replace(",", "") for n in re.findall(r"(?<![A-Za-z])\d[\d,]*(?:\.\d+)?", t or "")
            if not re.fullmatch(r"(19|20)\d\d", n.replace(",", ""))}


# ---------------------------------------------------------------- Claude (one call)
EDITOR_PROMPT = """You are the editor of "Around Us", a casual Instagram page for people in and around Giddalur, Andhra Pradesh.
Rewrite headlines into very simple, short, plain English a 14-year-old understands. No jargon, no hype, no emoji.
Some headlines are in Telugu: translate them into simple English. Item text must be ENGLISH ONLY (no Telugu script),
because the images cannot show Telugu letters. Captions may include one Telugu line.

Make FOUR posts. For each, pick headlines from the list below (use their [id]) and write ONE item per headline:
a clear, slightly detailed sentence of 100-160 characters (it should fill about 2 full lines on the image):
what happened, who, the key number, and why it matters. Use ONLY facts in the headline, never invent details.
- "world": {world} items about INDIA'S ROLE IN THE WORLD: what India or Indians did, won, signed, ranked, exported,
  contributed or achieved abroad, or a global decision that directly affects India. EVERY item MUST contain the word
  "India" or "Indian". Do NOT include world news that has no India link (e.g. a Nobel Prize won by non-Indians).
- "india": {india} items (100-160 characters each): most important or interesting national news. Mix money and prices, Sensex/Nifty, EV, solar,
  movies and box office, cricket and sports, ISRO and tech, weather, big decisions.
- "south": {south} items from Tamil Nadu, Karnataka, Kerala, Telangana. "tag" = state name.
- "andhra": {andhra} items: Andhra Pradesh (government, projects, jobs, Telugu cinema, weather, sports).

Rules: a story goes in only ONE post. Prefer stories with high "cov" (covered by many outlets) and with numbers.
Skip crime naming private people, communal/caste stories, political mud-slinging, gossip, health rumours.
Allegations stay allegations ("police say", "X alleges").

Also write "captions": one Instagram caption per post (keys world, india, south, andhra): 2 short friendly
lines about that post, then one simple Telugu line, then max 3 hashtags including #AroundUs. Max 500 characters each.

TODAY: {today}

HEADLINES ([id] (post) cov=N date title | outlet):
"""

ITEM = {"type": "object", "properties": {"id": {"type": "string"}, "text": {"type": "string"}, "tag": {"type": "string"}},
        "required": ["id", "text"]}
DRAFT_TOOL = {"name": "submit_posts", "description": "Submit today's posts.",
              "input_schema": {"type": "object", "properties": {
                  **{k: {"type": "array", "items": ITEM} for k in SECTIONS},
                  "captions": {"type": "object", "properties": {k: {"type": "string"} for k in SECTIONS}}},
                  "required": list(SECTIONS) + ["captions"]}}


def claude_call(body):
    code, js = 0, {}
    for attempt in range(3):
        code, js = http("POST", "https://api.anthropic.com/v1/messages",
                        {"x-api-key": ANTHROPIC_KEY, "anthropic-version": "2023-06-01"}, body, timeout=300)
        if code == 200:
            return code, js
        log(f"Claude error {code}: {str(js)[:200]}")
        if code in (400, 401, 403, 404):
            break
        time.sleep(10 * (attempt + 1))
    return code, js


def pick_model():
    if MODEL:
        return MODEL
    code, js = http("GET", "https://api.anthropic.com/v1/models?limit=50",
                    {"x-api-key": ANTHROPIC_KEY, "anthropic-version": "2023-06-01"})
    ids = [m.get("id", "") for m in js.get("data", [])] if code == 200 else []
    for pref in ("sonnet", "opus", "haiku"):
        for mid in ids:
            if pref in mid:
                return mid
    return ids[0] if ids else "claude-sonnet-4-5"


def parse_json(text, key):
    dec, best = json.JSONDecoder(), {}
    for m in re.finditer(r"\{", text or ""):
        try:
            obj, _ = dec.raw_decode(text[m.start():])
        except ValueError:
            continue
        if isinstance(obj, dict) and key in obj:
            best = obj
    return best


def texts(js):
    return "".join(b.get("text", "") for b in js.get("content", []) if b.get("type") == "text")


def draft(prompt, model):
    """One call. Tool offered (never forced). Falls back to JSON text. Returns {} if everything fails."""
    code, js = claude_call({"model": model, "max_tokens": 12000, "tools": [DRAFT_TOOL],
                            "messages": [{"role": "user", "content": prompt + "\nSubmit with the submit_posts tool."}]})
    if code == 200:
        for b in js.get("content", []):
            if b.get("type") == "tool_use" and b.get("name") == "submit_posts":
                return b.get("input") or {}
        out = parse_json(texts(js), "india")
        if out:
            return out
    # second (and last) try: plain JSON, no tools
    code, js = claude_call({"model": model, "max_tokens": 12000, "messages": [{"role": "user", "content":
                            prompt + "\nReply with ONE JSON object only, with keys world, india, south, andhra "
                            "(lists of {id, text, tag}) and captions. Escape quotes inside strings."}]})
    return parse_json(texts(js), "india") if code == 200 else {}


# ---------------------------------------------------------------- build posts (code guarantees 5-10)
def build(result, items):
    by_id = {it["id"]: it for it in items}
    used_ids, used_text, posts, notes = set(), [], {}, []
    order = ("andhra", "south", "india", "world")  # most local first, so it keeps its stories
    for sec in order:
        lines = []
        for x in (result.get(sec) or []):
            if not isinstance(x, dict):
                continue
            h = by_id.get(str(x.get("id", "")).strip("[] "))
            text = (x.get("text") or "").strip()
            if not h or h["id"] in used_ids or not text:
                continue
            if any(similar(text, t) for t in used_text) or any(similar(h["title"], t) for t in used_text):
                continue
            if TELUGU_RE.search(text):
                continue  # Telugu letters cannot be shown on the image
            if not nums(text) <= nums(h["title"]):  # a number not in the headline: use the headline itself
                text = h["title"]
                if TELUGU_RE.search(text):
                    continue
            if sec == "world" and not (INDIA_RE.search(text) and INDIA_RE.search(h["title"])):
                continue  # India in the world: must be about India
            lines.append({"text": text[:200], "tag": (x.get("tag") or "")[:20], "src": h["outlet"], "date": h["date"]})
            used_ids.add(h["id"])
            used_text += [text, h["title"]]
            if len(lines) >= MAX_LINES:
                break
        posts[sec] = lines
    # fill any post below the minimum with real headlines from its own feeds (best covered first)
    for sec in order:
        need = (10 if sec == "india" else MIN_LINES) - len(posts[sec])
        if need <= 0:
            continue
        pool = sorted((it for it in items if it["section"] == sec and it["id"] not in used_ids),
                      key=lambda it: (it["cov"], it["date"] or ""), reverse=True)
        added = 0
        for h in pool:
            if added >= need:
                break
            if any(similar(h["title"], t) for t in used_text) or len(h["title"]) > 200:
                continue
            if sec == "world" and not INDIA_RE.search(h["title"]):
                continue
            if TELUGU_RE.search(h["title"]):
                continue  # raw Telugu headline can't go on an English image
            tag = ""
            if sec == "south":
                tag = {"TAMIL_NADU": "Tamil Nadu", "KARNATAKA": "Karnataka", "KERALA": "Kerala",
                       "TELANGANA": "Telangana"}.get(h["feed"], "")
            posts[sec].append({"text": h["title"], "tag": tag, "src": h["outlet"], "date": h["date"]})
            used_ids.add(h["id"])
            used_text.append(h["title"])
            added += 1
        if added:
            notes.append(f"{sec}: +{added} filled from headlines")
        if len(posts[sec]) < MIN_LINES:
            notes.append(f"{sec}: only {len(posts[sec])} real headlines available today")
    return posts, used_ids, notes


DEFAULT_CAPTIONS = {
    "world": "India in the world today, in one quick read.\nప్రపంచంలో భారత్ ఈరోజు.\n#AroundUs #India",
    "india": "Today's top stories from across India, in simple words.\nఈరోజు దేశంలో ముఖ్య వార్తలు.\n#AroundUs #India",
    "south": "What's happening across South India today.\nదక్షిణ భారతంలో ఈరోజు.\n#AroundUs #SouthIndia",
    "andhra": "Andhra Pradesh today, in one quick read.\nఆంధ్రప్రదేశ్ ఈరోజు.\n#AroundUs #AndhraPradesh",
    "rupee": "How many rupees for 1 dollar, euro, pound, yen, yuan, Canadian & Singapore dollar and dirham today.\nఈరోజు రూపాయి విలువ.\n#AroundUs #Rupee",
    "nifty": "Nifty 50 at close, with all 50 stocks ranked by their 1-day move. Also how each did over 1 week, 1 month and 1 year. For information only, not investment advice.\nనిఫ్టీ 50 ఈరోజు.\n#AroundUs #Nifty50 #StockMarket",
    "markets": "How the world's 10 biggest stock exchanges closed. For information only, not investment advice.\nమార్కెట్లు ఎలా ముగిశాయి.\n#AroundUs #Sensex",
}


# ---------------------------------------------------------------- Telegram
def tg(method, **params):
    return http("POST", f"https://api.telegram.org/bot{TG_TOKEN}/{method}", data=params)


def tg_photo(path, caption, buttons=None):
    boundary = "----AroundUs" + hashlib.md5(path.encode()).hexdigest()
    with open(path, "rb") as fh:
        img = fh.read()
    markup = ""
    if buttons:
        markup = (f'--{boundary}\r\nContent-Disposition: form-data; name="reply_markup"\r\n\r\n'
                  f'{json.dumps({"inline_keyboard": [buttons]})}\r\n')
    body = (f'--{boundary}\r\nContent-Disposition: form-data; name="chat_id"\r\n\r\n{TG_CHAT}\r\n'
            f'--{boundary}\r\nContent-Disposition: form-data; name="caption"\r\n\r\n{caption[:1024]}\r\n'
            + markup +
            f'--{boundary}\r\nContent-Disposition: form-data; name="photo"; filename="post.jpg"\r\n'
            f"Content-Type: image/jpeg\r\n\r\n").encode() + img + f"\r\n--{boundary}--\r\n".encode()
    return http("POST", f"https://api.telegram.org/bot{TG_TOKEN}/sendPhoto",
                {"Content-Type": f"multipart/form-data; boundary={boundary}"}, body, timeout=60)


def prune_old_posts(today, keep_days=7):
    """Instagram copies the image when it publishes, so old images can go."""
    import shutil
    if not os.path.isdir(POSTS_DIR):
        return
    cutoff = (datetime.strptime(today, "%Y-%m-%d") - timedelta(days=keep_days)).strftime("%Y-%m-%d")
    for d in os.listdir(POSTS_DIR):
        if re.fullmatch(r"\d{4}-\d\d-\d\d", d) and d < cutoff:
            shutil.rmtree(os.path.join(POSTS_DIR, d), ignore_errors=True)


def ig_handle():
    if not IG_TOKEN:
        return None
    q = urllib.parse.urlencode({"fields": "username", "access_token": IG_TOKEN})
    code, js = http("GET", f"https://graph.instagram.com/v23.0/me?{q}")
    return "@" + js["username"] if code == 200 and isinstance(js, dict) and js.get("username") else None


# ---------------------------------------------------------------- main
def main():
    log("Around Us agent", VERSION)
    for k, v in {"ANTHROPIC_API_KEY": ANTHROPIC_KEY, "TELEGRAM_BOT_TOKEN": TG_TOKEN,
                 "TELEGRAM_ADMIN_CHAT_ID": TG_CHAT}.items():
        if not v:
            raise SystemExit(f"{k} missing")
    now = datetime.now(IST)
    handle = ig_handle()
    if handle:
        slides.HANDLE = handle

    # 1. headlines
    seen = load_seen()
    items, keys = [], set()
    for name, (sec, url) in FEEDS.items():
        for it in fetch_feed(name, sec, url):
            key = re.sub(r"\W+", " ", it["title"].lower())[:70]
            if it["id"] in seen or key in keys:
                continue
            keys.add(key)
            items.append(it)
    for it in items:
        it["cov"] = 1 + len(it["also"])
    for i, a in enumerate(items):
        for b in items[i + 1:]:
            if similar(a["title"], b["title"]):
                a["cov"] += 1
                b["cov"] += 1
    items.sort(key=lambda x: -x["cov"])
    log(f"{len(items)} new headlines")

    # 2. numbers
    fx, fx_note, fx_problems = get_fx()
    log(f"fx: {len(fx)} currencies", fx_problems)
    mkts, mkt_problems = get_markets() if (MARKETS_POST and now.weekday() < 5) else ([], [])
    nifty, nifty_problems = None, []
    if NIFTY_POST and now.weekday() < 5:
        try:
            nifty, nifty_problems = get_nifty()
        except Exception as e:  # never let the Nifty post stop the others
            nifty, nifty_problems = None, [f"Nifty post skipped: {str(e)[:120]}"]
    mkt_problems = mkt_problems + nifty_problems[:6]

    # 3. one Claude call
    result, problem = {}, ""
    try:
        model = pick_model()
        log("model:", model)
        per_sec = {s: [it for it in items if it["section"] == s][:70] for s in SECTIONS}
        listing = "\n".join(f'[{it["id"]}] ({it["section"]}) cov={it["cov"]} {it["date"]} {it["title"]} | {it["outlet"]}'
                            for s in SECTIONS for it in per_sec[s])
        prompt = EDITOR_PROMPT.format(today=now.strftime("%A %d %B %Y"), **TARGET) + listing
        result = draft(prompt, model)
        log("claude:", {s: len(result.get(s) or []) for s in SECTIONS})
    except Exception as e:
        problem = f"Claude step failed ({str(e)[:120]}); posts built from headlines only"
        log(problem)
    if not result:
        problem = problem or "Claude gave no usable answer; posts built from headlines only"

    # 4. posts (code enforces 5-10 lines with source + date)
    posts, used_ids, notes = build(result, items)
    log("final:", {s: len(posts[s]) for s in SECTIONS}, notes)
    captions = {**DEFAULT_CAPTIONS, **{k: v for k, v in (result.get("captions") or {}).items()
                                       if isinstance(v, str) and v.strip()}}

    # 5. render: one image per post
    day = now.strftime("%Y-%m-%d")
    OUT_DIR = os.path.join(POSTS_DIR, day)
    os.makedirs(OUT_DIR, exist_ok=True)
    prune_old_posts(day)
    plan = []
    if posts["world"]:
        plan.append(("world", lambda p: slides.digest("WORLD", "India in the world", "world", posts["world"], p)))
    if fx:
        plan.append(("rupee", lambda p: slides.rupee(fx, p, note=fx_note)))
    if mkts:
        plan.append(("markets", lambda p: slides.markets(mkts, p)))
    if nifty:
        plan.append(("nifty", lambda p: slides.nifty(nifty, p)))
    if posts["india"]:
        n = len(posts["india"])
        plan.append(("india", lambda p: slides.digest("INDIA", f"Top {n} in India", "India", posts["india"], p)))
    if posts["south"]:
        plan.append(("south", lambda p: slides.digest("SOUTH INDIA", "Across the South", "South", posts["south"], p)))
    if posts["andhra"]:
        plan.append(("andhra", lambda p: slides.digest("ANDHRA PRADESH", "Andhra today", "Andhra", posts["andhra"], p)))
    made = []
    for i, (name, fn) in enumerate(plan, 1):
        path = os.path.join(OUT_DIR, f"{i:02d}-{name}.jpg")
        try:
            fn(path)
            made.append((name, path))
        except Exception as e:
            log(f"render {name} failed: {e}")
    log(f"rendered {len(made)} posts")

    # 6. Save the queue. Telegram is sent by agent/send.py AFTER the images are uploaded to GitHub,
    #    so a ✅ tap always has an image online behind it.
    counts = " · ".join(f"{s} {len(posts[s])}" for s in SECTIONS)
    issues = ([problem] if problem else []) + notes + fx_problems + mkt_problems
    summary = (f"☕ Around Us · {now.strftime('%A, %d %b')}\n\n{len(made)} posts ready · {counts}\n"
               f"💱 rupee: {fx_note if fx else 'not shown (sources did not agree)'}\n"
               f"📈 markets: {'yes' if mkts else 'no'} · Nifty 50: {'yes' if nifty else 'no'}\n"
               + ("\nNotes:\n" + "\n".join("• " + x for x in issues[:10]) + "\n" if issues else "")
               + "\nTap ✅ Post under any post to publish it on Instagram (live in ~5-15 min), or ❌ Skip.")
    queue = {}
    for name, path in made:
        cap = captions.get(name, "")
        srcs = sorted({x["src"] for x in posts.get(name, []) if x.get("src")})
        if srcs:
            cap = cap.rstrip() + "\n\nSources: " + ", ".join(srcs[:8])
        queue[f"{day}/{os.path.basename(path)}"] = {"name": name, "caption": cap[:2200], "status": "waiting"}
    qpath = os.path.join(OUT_DIR, "queue.json")
    try:  # merge with today's existing queue (e.g. the 4 PM movers post, or posts already published)
        with open(qpath) as fh:
            old = json.load(fh)
    except Exception:
        old = {}
    for k, v in old.items():
        if k not in queue or v.get("status") in ("posted", "skipped"):
            queue[k] = v
    with open(qpath, "w") as fh:
        json.dump(queue, fh, ensure_ascii=False, indent=1)
    with open(os.path.join(OUT_DIR, "summary.txt"), "w") as fh:
        fh.write(summary)
    if os.environ.get("SEND_NOW") == "1":  # only for local testing; the workflow sends after upload
        import send
        send.send_day(day)

    stamp = now.isoformat()
    for x in used_ids:
        seen[x] = stamp
    save_seen(seen)
    log("done")


if __name__ == "__main__":
    try:
        main()
    except Exception as e:
        if TG_TOKEN and TG_CHAT:
            tg("sendMessage", chat_id=TG_CHAT, text=f"⚠️ Around Us agent failed: {str(e)[:300]}")
        raise
