"""Around Us - daily agent (dry run: drafts go to Telegram only).

Every morning it builds one carousel post:
  1. WORLD    India in the world (3-4 items) + rupee vs USD, CNY, EUR, JPY, GBP
  2. MARKETS  top 10 stock exchanges, last close (weekdays only)
  3. INDIA    top 10 India stories, one line each
  4. SOUTH    Tamil Nadu, Karnataka, Kerala, Telangana, Puducherry
  5. ANDHRA   big Andhra Pradesh stories
  6. NEAR YOU Giddalur and surrounding mandals (only if there is real news)
No story appears on more than one slide.
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

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import slides  # noqa: E402

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SEEN_PATH = os.path.join(ROOT, "data", "seen.json")
OUT_DIR = os.path.join(ROOT, "out")
IST = timezone(timedelta(hours=5, minutes=30))

ANTHROPIC_KEY = os.environ.get("ANTHROPIC_API_KEY", "").strip()
TG_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
TG_CHAT = os.environ.get("TELEGRAM_ADMIN_CHAT_ID", "").strip()
IG_TOKEN = os.environ.get("IG_ACCESS_TOKEN", "").strip()
MODEL = os.environ.get("CLAUDE_MODEL", "").strip()


def gn(q, days=1, lang="en"):
    hl, ceid = ("te", "IN:te") if lang == "te" else ("en-IN", "IN:en")
    return (f"https://news.google.com/rss/search?q={urllib.parse.quote(q + f' when:{days}d')}"
            f"&hl={hl}&gl=IN&ceid={ceid}")


def topic(t):
    return f"https://news.google.com/rss/headlines/section/topic/{t}?hl=en-IN&gl=IN&ceid=IN:en"


# feed name -> (section hint, url)
FEEDS = {
    "WORLD":       ("world", topic("WORLD")),
    "INDIA_ABROAD": ("world", gn('India (US OR China OR EU OR Russia OR UN OR Pakistan OR trade OR visa OR summit)')),
    "NATION":      ("india", topic("NATION")),
    "BUSINESS":    ("india", topic("BUSINESS")),
    "SCI_TECH":    ("india", topic("SCIENCE")),
    "SPORTS":      ("india", topic("SPORTS")),
    "TAMIL_NADU":  ("south", gn("Tamil Nadu OR Chennai")),
    "KARNATAKA":   ("south", gn("Karnataka OR Bengaluru")),
    "KERALA":      ("south", gn("Kerala OR Kochi OR Thiruvananthapuram")),
    "TELANGANA":   ("south", gn("Telangana OR Hyderabad")),
    "ANDHRA":      ("andhra", gn('"Andhra Pradesh"')),
    "ANDHRA_CITIES": ("andhra", gn("Amaravati OR Vijayawada OR Visakhapatnam OR Tirupati OR Guntur OR Nellore")),
    "ANDHRA_TE":   ("andhra", gn("ఆంధ్రప్రదేశ్", lang="te")),
    "LOCAL":       ("local", gn("Giddalur OR Giddaluru OR Markapuram OR Markapur OR Prakasam OR Cumbum OR Komarolu OR Racherla OR Bestavaripeta OR Ardhaveedu", days=7)),
    "LOCAL_TE":    ("local", gn("గిద్దలూరు OR మార్కాపురం OR ప్రకాశం OR కంభం OR బేస్తవారిపేట", days=7, lang="te")),
}

FX = [("USD", "US dollar"), ("EUR", "Euro"), ("GBP", "British pound"), ("JPY", "Japanese yen · 100"),
      ("CNY", "Chinese yuan"), ("CAD", "Canadian dollar"), ("SGD", "Singapore dollar"), ("AED", "UAE dirham")]
EXCHANGES = [  # roughly the 10 largest exchanges by market value
    ("NYSE", "NYSE Composite", "^NYA"), ("Nasdaq", "Nasdaq Composite", "^IXIC"),
    ("Shanghai", "SSE Composite", "000001.SS"), ("Japan", "Nikkei 225", "^N225"),
    ("Euronext", "Euronext 100", "^N100"), ("Shenzhen", "SZSE Component", "399001.SZ"),
    ("Hong Kong", "Hang Seng", "^HSI"), ("NSE India", "Nifty 50", "^NSEI"),
    ("BSE India", "Sensex", "^BSESN"), ("London", "FTSE 100", "^FTSE"),
]

EDITOR_PROMPT = """You are the editor of "Around Us", a casual Instagram page for people in and around Giddalur, Andhra Pradesh.
Write for an ordinary person: very simple, short, plain English a 14-year-old understands. No jargon, no hype, no emoji.

Fill these sections from the HEADLINES below. Each item is ONE line, max 90 characters, a full simple sentence with the key fact (who/what + number if any).
Pick INTERESTING, TRENDING stories people will talk about today. Prefer stories with a concrete number
(amount, %, count, date) and stories covered by many outlets (higher "cov" = more outlets = trending).
- "world": 5-6 items about INDIA IN THE WORLD (India's deals, visits, trade, visas, Indians abroad, global events that directly affect India).
- "india": exactly 10 of the most important or useful national stories (policy, money, prices, weather, science, sports, big court rulings). Order by importance.
- "south": 6 items (at least 5) from Tamil Nadu, Karnataka, Kerala, Telangana, Puducherry. Each has "tag" = state name.
- "andhra": 6 items (at least 5) big Andhra Pradesh stories.
- "local": up to 5 items about Giddalur, Markapuram district, Prakasam or nearby mandals (Komarolu, Racherla, Cumbum, Bestavaripeta, Ardhaveedu). Each has "tag" = town name. Empty list if nothing real.

STRICT RULES
1. NO REPEATS: a story may appear in only ONE section. If a story fits two, put it in the more local one (local > andhra > south > india > world).
2. Only facts in the headlines. Never invent numbers, names, dates or quotes. If unsure of a detail, leave it out.
3. Allegations are not facts: "police say...", "X alleges...", "according to...".
4. Skip: crimes or accidents naming private people, communal/caste stories, party mud-slinging, graphic violence, gossip, health rumours.
5. "check": true if only ONE outlet reports it (no "also reported by"), else false. Official sources (govt, RBI, ISRO, IMD, police, court) count as confirmed.
6. "ids": the headline ids you used for that item.

Also write "caption": the Instagram caption for the whole carousel. Format:
line 1: a short friendly hook about today
then one line per slide, e.g. "1 · India in the world: ..." (only slides that exist; slide 2 is markets on weekdays)
then one simple Telugu line
then "Swipe through →"
then at most 3 hashtags, always #AroundUs. Max 900 characters.

Return ONLY JSON:
{"world":[{"text":"","ids":[],"check":false}],
 "india":[{"text":"","ids":[],"check":false}],
 "south":[{"tag":"","text":"","ids":[],"check":false}],
 "andhra":[{"text":"","ids":[],"check":false}],
 "local":[{"tag":"","text":"","ids":[],"check":false}],
 "caption":""}

TODAY: {today}. MARKETS SLIDE TODAY: {markets}.

HEADLINES ([id] (feed) cov=N title | outlet | also reported by), most covered first:
"""


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


# ---------------------------------------------------------------- news
def fetch_feed(name, url, limit=20):
    code, xml_bytes = http("GET", url, raw=True)
    if code != 200 or not xml_bytes:
        log(f"feed {name}: failed ({code})")
        return []
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return []
    items = []
    for it in root.iter("item"):
        title = html.unescape(it.findtext("title") or "").strip()
        src = it.find("source")
        outlet = (src.text or "").strip() if src is not None else ""
        if outlet and title.endswith(" - " + outlet):
            title = title[: -len(outlet) - 3].strip()
        desc = html.unescape(it.findtext("description") or "")
        also = sorted({r.strip() for r in re.findall(r'<font color="#6f6f6f">([^<]+)</font>', desc)} - {outlet})
        items.append({"id": hashlib.sha1(title.lower().encode()).hexdigest()[:10], "feed": name,
                      "title": title, "outlet": outlet, "also": also[:4], "link": it.findtext("link") or ""})
        if len(items) >= limit:
            break
    log(f"feed {name}: {len(items)}")
    return items


def load_seen():
    try:
        with open(SEEN_PATH) as fh:
            data = json.load(fh)
    except Exception:
        data = {}
    cutoff = (datetime.now(IST) - timedelta(days=10)).isoformat()
    return {k: v for k, v in data.items() if v >= cutoff}


def save_seen(seen):
    os.makedirs(os.path.dirname(SEEN_PATH), exist_ok=True)
    with open(SEEN_PATH, "w") as fh:
        json.dump(seen, fh, indent=0, sort_keys=True)


# ---------------------------------------------------------------- numbers
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


MKT_PATH = os.path.join(ROOT, "data", "markets.json")


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


# ---------------------------------------------------------------- Claude
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


def ask_claude(prompt, model, max_tokens=4000):
    for attempt in range(3):
        code, js = http("POST", "https://api.anthropic.com/v1/messages",
                        {"x-api-key": ANTHROPIC_KEY, "anthropic-version": "2023-06-01"},
                        {"model": model, "max_tokens": max_tokens,
                         "messages": [{"role": "user", "content": prompt}]}, timeout=180)
        if code == 200:
            return "".join(b.get("text", "") for b in js.get("content", []))
        log(f"Claude error {code}: {str(js)[:200]}")
        time.sleep(6 * (attempt + 1))
    raise RuntimeError("Claude request failed")


VERIFY_PROMPT = """You are the fact-checker for "Around Us", a news page whose credibility depends on being right.
Below are today's draft items for the "{section}" slide, each with the EVIDENCE: the headlines and outlets it is based on.

For each item:
1. CONFIRMED without searching if the evidence shows 2+ different credible outlets, or an official source
   (government, PIB, RBI, SEBI, ISRO, IMD, Election Commission, courts, police). Just check the wording matches the evidence.
2. Otherwise use web search to confirm it with a credible source from the last 3 days: official sites or established outlets
   (The Hindu, Indian Express, Times of India, Hindustan Times, NDTV, Mint, Economic Times, Business Standard, PTI, ANI,
   Reuters, BBC, AP, Deccan Chronicle, Deccan Herald, Eenadu, Sakshi, Andhra Jyothy, The New Indian Express). No blogs or social posts.
3. Fix any wrong number, date or name. Where a solid sourced number makes it more useful, add it (keep under 90 characters, simple words).
4. REMOVE an item only if it is false, misleading, or you cannot confirm it anywhere credible.
5. Keep allegations as allegations. Do not add new stories.
Set "src" to the best confirming outlet (short name). Set "status": "confirmed" or "corrected".

Return ONLY JSON:
{{"items":[{{"text":"","tag":"","src":"","ids":[],"status":"confirmed"}}],
 "removed":[{{"text":"","reason":""}}]}}

ITEMS WITH EVIDENCE:
{payload}
"""


def verify_section(section, items, evidence, model, max_searches):
    """Fact-check one slide. Returns ((items, removed), note) or (None, note) on failure."""
    payload = []
    for it in items:
        ev = [evidence[i] for i in it.get("ids", []) if i in evidence]
        payload.append({"text": it["text"], "tag": it.get("tag", ""), "ids": it.get("ids", []),
                        "evidence": [f'{e["title"]} | {e["outlet"]}' + (f' | also: {", ".join(e["also"])}' if e["also"] else "")
                                     for e in ev]})
    prompt = VERIFY_PROMPT.format(section=section, payload=json.dumps(payload, ensure_ascii=False, indent=1))
    msgs = [{"role": "user", "content": prompt}]
    tools = [{"type": "web_search_20250305", "name": "web_search", "max_uses": max_searches}]
    text = ""
    for _ in range(4):  # long tool turns can pause; continue them
        code, js = http("POST", "https://api.anthropic.com/v1/messages",
                        {"x-api-key": ANTHROPIC_KEY, "anthropic-version": "2023-06-01"},
                        {"model": model, "max_tokens": 4000, "messages": msgs, "tools": tools}, timeout=300)
        if code != 200:
            err = (js.get("error") or {}).get("message", "") if isinstance(js, dict) else ""
            return None, f"{code} {err[:100]}"
        text += "".join(b.get("text", "") for b in js.get("content", []) if b.get("type") == "text")
        if js.get("stop_reason") != "pause_turn":
            break
        msgs = msgs + [{"role": "assistant", "content": js["content"]}]
    out = parse_json(text, key="items")
    if "items" not in out:
        return None, "unreadable result"
    return (out.get("items") or [], out.get("removed") or []), "ok"


def verify_all(draft, items, model, per_section):
    evidence = {it["id"]: it for it in items}
    res, removed, notes = {"caption": draft.get("caption", "")}, [], []
    for sec in ("world", "india", "south", "andhra", "local"):
        d_items = draft.get(sec, [])
        if not d_items:
            res[sec] = []
            continue
        got, note = verify_section(sec, d_items, evidence, model, per_section)
        if got is None:
            # could not check: keep only items with 2+ outlets, drop the rest
            res[sec] = [i for i in d_items if not i.get("check")]
            removed += [{"text": i["text"], "reason": "single source; fact-check failed"} for i in d_items if i.get("check")]
            notes.append(f"{sec}: check failed ({note})")
        else:
            res[sec], rem = got
            removed += rem
        log(f"verify {sec}: {len(d_items)} drafted -> {len(res[sec])} kept")
    return res, removed, notes


def parse_json(text, key=None):
    """Return the last JSON object in text (optionally one containing `key`)."""
    dec = json.JSONDecoder()
    best = None
    for m in re.finditer(r"\{", text):
        try:
            obj, _ = dec.raw_decode(text[m.start():])
        except ValueError:
            continue
        if isinstance(obj, dict) and (key is None or key in obj):
            best = obj
            if key is None:
                break
    return best or {}


def no_repeats(result):
    """Enforce: a headline id is used on one slide only (local wins, then andhra, south, india, world)."""
    used, clean = set(), {}
    for sec in ("local", "andhra", "south", "india", "world"):
        keep = []
        for it in result.get(sec, []) or []:
            ids = set(it.get("ids", []))
            text = (it.get("text") or "").strip()
            if not text or (ids and ids & used):
                continue
            used |= ids
            keep.append(it)
        clean[sec] = keep
    clean["caption"] = result.get("caption", "")
    return clean


# ---------------------------------------------------------------- Telegram
def tg(method, **params):
    return http("POST", f"https://api.telegram.org/bot{TG_TOKEN}/{method}", data=params)


def tg_album(paths, caption):
    boundary = "----AroundUs" + hashlib.md5("".join(paths).encode()).hexdigest()
    media = [{"type": "photo", "media": f"attach://p{i}"} for i in range(len(paths))]
    media[0]["caption"] = caption[:1024]
    parts = [f'--{boundary}\r\nContent-Disposition: form-data; name="chat_id"\r\n\r\n{TG_CHAT}\r\n'.encode(),
             f'--{boundary}\r\nContent-Disposition: form-data; name="media"\r\n\r\n{json.dumps(media)}\r\n'.encode()]
    for i, p in enumerate(paths):
        with open(p, "rb") as fh:
            parts.append(f'--{boundary}\r\nContent-Disposition: form-data; name="p{i}"; filename="s{i}.jpg"\r\n'
                         f"Content-Type: image/jpeg\r\n\r\n".encode() + fh.read() + b"\r\n")
    parts.append(f"--{boundary}--\r\n".encode())
    return http("POST", f"https://api.telegram.org/bot{TG_TOKEN}/sendMediaGroup",
                {"Content-Type": f"multipart/form-data; boundary={boundary}"}, b"".join(parts), timeout=90)


def ig_handle():
    if not IG_TOKEN:
        return None
    q = urllib.parse.urlencode({"fields": "username", "access_token": IG_TOKEN})
    code, js = http("GET", f"https://graph.instagram.com/v23.0/me?{q}")
    return "@" + js["username"] if code == 200 and js.get("username") else None


# ---------------------------------------------------------------- main
def main():
    for k, v in {"ANTHROPIC_API_KEY": ANTHROPIC_KEY, "TELEGRAM_BOT_TOKEN": TG_TOKEN,
                 "TELEGRAM_ADMIN_CHAT_ID": TG_CHAT}.items():
        if not v:
            raise SystemExit(f"{k} missing")
    now = datetime.now(IST)
    weekday = now.weekday() < 5
    if (h := ig_handle()):
        slides.HANDLE = h

    seen = load_seen()
    items, titles = [], set()
    for name, (_, url) in FEEDS.items():
        for it in fetch_feed(name, url):
            key = re.sub(r"\W+", " ", it["title"].lower())[:70]
            if it["id"] in seen or key in titles:
                continue
            titles.add(key)
            items.append(it)
    log(f"{len(items)} new headlines")

    fx, fx_note, fx_problems = get_fx()
    log(f"fx: {len(fx)} currencies", fx_problems)
    mkts, mkt_problems = get_markets() if weekday else ([], [])

    # coverage = how many outlets carry roughly the same headline (trending signal)
    def words(t):
        return {w for w in re.findall(r"[a-z]{4,}", t.lower())}
    for it in items:
        it["cov"] = 1 + len(it["also"])
    for i, a in enumerate(items):
        wa = words(a["title"])
        for b in items[i + 1:]:
            wb = words(b["title"])
            if wa and wb and len(wa & wb) / min(len(wa), len(wb)) >= 0.6:
                a["cov"] += 1
                b["cov"] += 1
    items.sort(key=lambda x: -x["cov"])
    listing = "\n".join(
        f'[{it["id"]}] ({it["feed"]}) cov={it["cov"]} {it["title"]} | {it["outlet"]}'
        + (f' | also: {", ".join(it["also"])}' if it["also"] else "") for it in items[:320])
    prompt = EDITOR_PROMPT.replace("{today}", now.strftime("%A %d %B %Y")).replace(
        "{markets}", "yes" if mkts else "no") + listing
    model = pick_model()
    log("model:", model)
    draft = no_repeats(parse_json(ask_claude(prompt, model, max_tokens=6000), key="india"))
    log("draft:", {k: len(v) for k, v in draft.items() if isinstance(v, list)})
    checked, removed, vnotes = verify_all(draft, items, model, int(os.environ.get("SEARCHES_PER_SLIDE", "5")))
    res = no_repeats(checked)
    res["removed"] = removed
    vnote = "web-checked" + (" · " + "; ".join(vnotes) if vnotes else "")
    checked = not vnotes
    log("verification:", vnote)

    # ---- render slides
    os.makedirs(OUT_DIR, exist_ok=True)
    plan = []
    for sec in ("world", "india", "south", "andhra", "local"):
        res[sec] = res.get(sec) or []
    if res["world"]:
        plan.append(("world", lambda p, pg: slides.digest("WORLD", "India in the world", "world", res["world"][:7], p, pg)))
    if fx:
        plan.append(("rupee", lambda p, pg: slides.rupee(fx, p, pg, note=fx_note)))
    if mkts:
        plan.append(("markets", lambda p, pg: slides.markets(mkts, p, pg)))
    if res["india"]:
        plan.append(("india", lambda p, pg: slides.digest("INDIA", "Top 10 in India", "India", res["india"][:10], p, pg)))
    if res["south"]:
        plan.append(("south", lambda p, pg: slides.digest("SOUTH INDIA", "Across the South", "South", res["south"][:7], p, pg)))
    if res["andhra"]:
        plan.append(("andhra", lambda p, pg: slides.digest("ANDHRA PRADESH", "Andhra today", "Andhra", res["andhra"][:7], p, pg)))
    if res["local"]:
        plan.append(("local", lambda p, pg: slides.digest("NEAR YOU", "Around Giddalur", "Giddalur", res["local"][:5], p, pg,
                                                           note="Problem on your street? DM us. We never share who sent it.")))
    paths = []
    for i, (name, fn) in enumerate(plan, 1):
        p = os.path.join(OUT_DIR, f"{i:02d}-{name}.jpg")
        fn(p, f"{i}/{len(plan)}")
        paths.append(p)
    log(f"rendered {len(paths)} slides")

    # ---- send to Telegram
    counts = " · ".join(f"{k} {len(res[k])}" for k in ("world", "india", "south", "andhra", "local"))
    corrected = [it for sec in ("world", "india", "south", "andhra", "local") for it in res[sec]
                 if it.get("status") == "corrected"]
    problems = fx_problems + mkt_problems
    tg("sendMessage", chat_id=TG_CHAT,
       text=f"☕ Around Us · {now.strftime('%A, %d %b')}\n\n"
            f"{len(items)} headlines scanned → {len(paths)} slides\n{counts}\n\n"
            f"Fact-check: {'✅ ' + vnote if checked else '⚠️ ' + vnote}\n"
            f"✏️ corrected: {len(corrected)} · 🗑 removed: {len(res.get('removed', []))}\n"
            f"💱 rupee: {fx_note if fx else 'NOT shown (sources did not agree)'}\n"
            f"📈 markets: {'shown' if mkts else 'not shown today'}\n"
            + (f"\n⚠️ Data issues:\n" + "\n".join("• " + p for p in problems[:8]) + "\n" if problems else "")
            + "\nDry-run mode: nothing is posted to Instagram yet.")
    if paths:
        code, js = tg_album(paths, res.get("caption", ""))
        if code != 200:
            log("album failed:", str(js)[:200])
    if res.get("removed"):
        tg("sendMessage", chat_id=TG_CHAT,
           text="🗑 Removed by fact-check:\n\n" + "\n".join(
               f"• {r.get('text', '')}\n  ↳ {r.get('reason', '')}" for r in res["removed"])[:3800])
    stamp = now.isoformat()
    for sec in ("world", "india", "south", "andhra", "local"):
        for it in res[sec]:
            for x in it.get("ids", []):
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
