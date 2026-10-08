"""Around Us - Friday releases post: new Telugu / Tamil / Hindi films and series this week.

ONE Instagram post (1-3 slides):  In cinemas this Friday  ·  New on OTT this week (Netflix, Prime Video,
JioHotstar, ZEE5, SonyLIV, Aha, Sun NXT, ETV Win, Apple TV+, Lionsgate Play, MX Player).

Cost: ONE Claude call a week (with up to 5 web searches). Accuracy rules, in order:
  1. Claude only COLLECTS candidates from this week's release round-ups and must give the URL of the page
     each item came from (two URLs for theatre releases). It is told to copy, not to guess.
  2. The code opens every cited page and keeps an item only if the title really appears on that page.
  3. Each title is looked up in a film database: OMDb (IMDb data, free key, OMDB_API_KEY) and/or TMDB
     (free key, TMDB_API_KEY; the site is often unreachable from India, so it is optional). The title must
     exist there as a current Telugu/Tamil/Hindi release (original or dubbed). The database also gives the
     genre, runtime and rating, and TMDB confirms the platform / theatrical date when it has them.
  4. An item is published only if it is confirmed twice: two pages, or one page + a database match.
     Theatre releases need two pages, or one page + a matching TMDB India theatrical date.
  5. Ratings: IMDb (OMDb) else TMDB (20+ votes) else "NEW". Never invented.
With no database key at all the post still works, with the stricter rule: two pages for every item, no ratings.
Everything dropped, and why, is listed in the Telegram summary.
"""
import json
import os
import re
import sys
import time
import urllib.parse
from datetime import datetime, timedelta

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import daily  # noqa: E402
import slides  # noqa: E402

VERSION = "releases v1 (Friday OTT + theatres)"
TMDB_KEY = os.environ.get("TMDB_API_KEY", "").strip()
OMDB_KEY = os.environ.get("OMDB_API_KEY", "").strip()
PLATFORMS = ["Netflix", "Prime Video", "JioHotstar", "ZEE5", "SonyLIV", "Aha", "Sun NXT", "ETV Win",
             "Apple TV+", "Lionsgate Play", "MX Player"]
ALIASES = [("netflix", "Netflix"), ("prime video", "Prime Video"), ("amazon prime", "Prime Video"),
           ("primevideo", "Prime Video"), ("jiohotstar", "JioHotstar"), ("jio hotstar", "JioHotstar"),
           ("hotstar", "JioHotstar"), ("zee5", "ZEE5"), ("zee 5", "ZEE5"), ("sonyliv", "SonyLIV"),
           ("sony liv", "SonyLIV"), ("aha", "Aha"), ("sun nxt", "Sun NXT"), ("sunnxt", "Sun NXT"),
           ("etv win", "ETV Win"), ("etvwin", "ETV Win"), ("apple tv", "Apple TV+"),
           ("lionsgate", "Lionsgate Play"), ("mx player", "MX Player"), ("theatre", "Theatres"),
           ("theater", "Theatres"), ("cinema", "Theatres")]
LANGS = {"te": "Telugu", "ta": "Tamil", "hi": "Hindi"}
BROWSER = {"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
                         "(KHTML, like Gecko) Chrome/126.0 Safari/537.36",
           "Accept": "text/html,application/xhtml+xml", "Accept-Language": "en-IN,en;q=0.9"}
MAX_ROWS = 8          # per slide
MAX_SLIDES = 3


# ---------------------------------------------------------------- helpers
def norm(s):
    return re.sub(r"[^a-z0-9]+", "", (s or "").lower())


def platform_of(text):
    t = (text or "").lower()
    for key, name in ALIASES:
        if key in t:
            return name
    return ""


def week_bounds(now):
    """Monday..Sunday of the current week, and this Friday (the run day)."""
    mon = (now - timedelta(days=now.weekday())).date()
    return mon, mon + timedelta(days=6), mon + timedelta(days=4)


# ---------------------------------------------------------------- 1. candidates (one Claude call)
PROMPT = """Today is {today} (India). You are collecting THIS WEEK's new releases for an Indian audience.

Find, from release round-up articles published this week:
  A. Films releasing IN THEATRES in India on Friday {friday} (and Thursday/Saturday if a round-up says so)
     in Telugu, Tamil or Hindi. Only films that a round-up or release-calendar article confirms for that date.
  B. New films and series arriving on OTT between {mon} and {sun} in Telugu, Tamil or Hindi (including
     Telugu/Tamil/Hindi dubbed releases of other-language films), on: {platforms}.

Rules (important):
- COPY from the pages, do not add anything from memory. If a page does not state the platform and date, skip it.
- Every item needs "source": the exact URL of the page you read it on. Add "source2" whenever a second page
  (another round-up, the platform's own page, a release calendar) also lists it; theatre items MUST have one.
- Skip re-releases and anything whose original release was more than 60 days ago. Skip trailers/announcements.
- At most 24 items. Use "note" for up to 8 words: genre and the lead actor, from the page.
- Use at most 5 searches.

Reply with ONE JSON object only (no commentary), like:
{{"week": "{mon} to {sun}", "items": [
  {{"title": "Exact Title", "type": "film", "language": "Telugu", "platform": "Netflix",
    "release_date": "YYYY-MM-DD", "note": "romantic drama, Lead Actor", "source": "https://...", "source2": ""}}
]}}
"platform" is one of: {platforms}, or "Theatres". "type" is "film" or "series". "language" is Telugu, Tamil or Hindi."""


def collect(now, model):
    mon, sun, fri = week_bounds(now)
    prompt = PROMPT.format(today=now.strftime("%A %d %B %Y"), friday=fri.strftime("%d %B %Y"),
                           mon=mon.isoformat(), sun=sun.isoformat(), platforms=", ".join(PLATFORMS))
    body = {"model": model, "max_tokens": 6000,
            "tools": [{"type": "web_search_20250305", "name": "web_search", "max_uses": 5}],
            "messages": [{"role": "user", "content": prompt}]}
    code, js = daily.claude_call(body)
    if code != 200:
        return [], f"Claude call failed ({code}): {str(js)[:160]}"
    out = daily.parse_json(daily.texts(js), "items")
    items = [i for i in out.get("items", []) if isinstance(i, dict) and i.get("title")]
    searches = sum(1 for b in js.get("content", []) if b.get("type") == "server_tool_use")
    return items[:24], f"Claude: {len(items)} candidates, {searches} searches"


# ---------------------------------------------------------------- 2. the cited pages
_pages = {}


def page_text(url):
    if url in _pages:
        return _pages[url]
    text = ""
    if url and url.startswith("http"):
        code, raw = daily.http("GET", url, headers=BROWSER, timeout=30, raw=True)
        if code == 200 and raw:
            t = raw.decode("utf-8", "ignore")
            t = re.sub(r"(?is)<(script|style|noscript)\b.*?</\1>", " ", t)
            text = re.sub(r"<[^>]+>", " ", t)
    _pages[url] = norm(text)
    return _pages[url]


def on_page(title, url):
    nt = norm(title)
    return len(nt) >= 3 and nt in page_text(url)


# ---------------------------------------------------------------- 3. TMDB
def tmdb(path, **params):
    q = urllib.parse.urlencode({**params, "api_key": TMDB_KEY})
    code, js = daily.http("GET", f"https://api.themoviedb.org/3/{path}?{q}", timeout=30)
    return js if code == 200 and isinstance(js, dict) else {}


def tmdb_match(item, now):
    """Find the title on TMDB. Returns details dict or None."""
    title = item["title"]
    res = tmdb("search/multi", query=title, include_adult="false", language="en-US", page=1).get("results", [])
    want = norm(title)
    best = None
    for r in res:
        if r.get("media_type") not in ("movie", "tv"):
            continue
        names = [r.get("title"), r.get("original_title"), r.get("name"), r.get("original_name")]
        if not any(norm(n) == want or (len(want) >= 6 and norm(n).startswith(want)) for n in names if n):
            continue
        date = r.get("release_date") or r.get("first_air_date") or ""
        try:
            age = (now.date() - datetime.strptime(date, "%Y-%m-%d").date()).days
        except ValueError:
            age = None
        if age is not None and not (-120 <= age <= 400):
            continue
        best = r
        break
    if not best:
        return None
    kind = best["media_type"]
    extra = "release_dates,watch/providers,external_ids" if kind == "movie" else "watch/providers,external_ids"
    d = tmdb(f"{kind}/{best['id']}", append_to_response=extra, language="en-US")
    if not d:
        return None
    spoken = {s.get("iso_639_1") for s in d.get("spoken_languages", [])}
    providers = [p.get("provider_name", "") for p in
                 ((d.get("watch/providers") or {}).get("results") or {}).get("IN", {}).get("flatrate", [])]
    in_dates = []
    for c in (d.get("release_dates") or {}).get("results", []):
        if c.get("iso_3166_1") == "IN":
            in_dates = [(x.get("release_date", "")[:10], x.get("type")) for x in c.get("release_dates", [])]
    return {"id": best["id"], "kind": "film" if kind == "movie" else "series",
            "title": d.get("title") or d.get("name"), "orig_lang": d.get("original_language"),
            "spoken": spoken, "genres": [g["name"] for g in d.get("genres", [])][:2],
            "runtime": d.get("runtime") or (d.get("episode_run_time") or [None])[0],
            "vote": d.get("vote_average"), "votes": d.get("vote_count") or 0,
            "imdb": (d.get("external_ids") or {}).get("imdb_id"), "providers": providers, "in_dates": in_dates,
            "date": d.get("release_date") or d.get("first_air_date") or ""}


def omdb_match(title, lang, now):
    """OMDb (IMDb data) by title: current Telugu/Tamil/Hindi film or series, with rating, genre, runtime."""
    if not OMDB_KEY:
        return None
    for params in ({"t": title, "y": now.year}, {"t": title}):
        code, js = daily.http("GET", "https://www.omdbapi.com/?" + urllib.parse.urlencode({**params, "apikey": OMDB_KEY}),
                              timeout=20)
        if code != 200 or not isinstance(js, dict) or js.get("Response") != "True":
            continue
        if norm(js.get("Title")) != norm(title) and not norm(js.get("Title")).startswith(norm(title)):
            continue
        year = re.search(r"\d{4}", js.get("Year", "") or "")
        if not year or not (now.year - 1 <= int(year.group()) <= now.year):
            continue
        langs = [x.strip() for x in (js.get("Language") or "").split(",")]
        if lang not in langs and not any(l in langs for l in LANGS.values()):
            return {"bad_lang": js.get("Language")}
        try:
            rating = float(js.get("imdbRating"))
            rating = rating if 0 < rating <= 10 else None
        except (TypeError, ValueError):
            rating = None
        rt = re.search(r"\d+", js.get("Runtime", "") or "")
        return {"kind": "series" if js.get("Type") == "series" else "film", "rating": rating,
                "genres": [g.strip() for g in (js.get("Genre") or "").split(",") if g.strip() and g != "N/A"][:2],
                "runtime": int(rt.group()) if rt else None, "langs": langs}
    return None


def imdb_rating(imdb_id):
    if not (OMDB_KEY and imdb_id):
        return None
    code, js = daily.http("GET", f"https://www.omdbapi.com/?i={imdb_id}&apikey={OMDB_KEY}", timeout=20)
    try:
        v = float(js.get("imdbRating"))
        return v if 0 < v <= 10 else None
    except (TypeError, ValueError, AttributeError):
        return None


# ---------------------------------------------------------------- 4. verify
def verify(items, now):
    mon, sun, fri = week_bounds(now)
    keep, notes = [], []
    seen = set()
    for it in items:
        title = str(it.get("title", "")).strip()
        if not title or norm(title) in seen:
            continue
        seen.add(norm(title))
        plat = platform_of(it.get("platform", "")) or ("Theatres" if "theat" in str(it.get("platform", "")).lower() else "")
        lang = str(it.get("language", "")).strip().title()
        if plat not in PLATFORMS + ["Theatres"] or lang not in LANGS.values():
            notes.append(f"{title}: dropped (platform '{it.get('platform')}' / language '{it.get('language')}' not in scope)")
            continue
        try:
            rdate = datetime.strptime(str(it.get("release_date", ""))[:10], "%Y-%m-%d").date()
        except ValueError:
            notes.append(f"{title}: dropped (no release date)")
            continue
        if plat == "Theatres":
            if not (fri - timedelta(days=1) <= rdate <= fri + timedelta(days=1)):
                notes.append(f"{title}: dropped (theatre date {rdate} is not this Friday)")
                continue
        elif not (mon - timedelta(days=1) <= rdate <= sun):
            notes.append(f"{title}: dropped (OTT date {rdate} is not this week)")
            continue
        srcs = [u for u in (it.get("source"), it.get("source2")) if u]
        pages_ok = [u for u in srcs if on_page(title, u)]
        tm = tmdb_match(it, now) if TMDB_KEY else None
        om = omdb_match(title, lang, now)
        time.sleep(0.3)
        if om and om.get("bad_lang"):
            notes.append(f"{title}: dropped (IMDb lists its languages as '{om['bad_lang']}', not {lang})")
            continue
        if tm:
            ok_lang = tm["orig_lang"] in LANGS or any(LANGS.get(x) == lang for x in tm["spoken"])
            if not ok_lang:
                notes.append(f"{title}: dropped (TMDB says original language '{tm['orig_lang']}', not {lang})")
                continue
        kind = (tm or om or {}).get("kind") or str(it.get("type", "film")).lower()
        tmdb_date_ok = False
        if tm and plat == "Theatres":
            tmdb_date_ok = any(t == 3 and abs((datetime.strptime(d, "%Y-%m-%d").date() - rdate).days) <= 1
                               for d, t in tm["in_dates"] if d)
        plat_seen = bool(tm) and any(norm(plat)[:5] in norm(p) for p in tm["providers"])
        db = tm is not None or om is not None
        if plat == "Theatres":
            confirmed = len(pages_ok) >= 2 or (len(pages_ok) >= 1 and tmdb_date_ok)
        else:
            confirmed = len(pages_ok) >= 2 or (len(pages_ok) >= 1 and db)
        if not confirmed:
            why = "title not found on the cited page" if not pages_ok else \
                  ("not found in the film database" if (TMDB_KEY or OMDB_KEY) and not db and plat != "Theatres"
                   else "only one page confirms it")
            notes.append(f"{title}: dropped ({why})")
            continue
        rating, rsrc = (om["rating"], "IMDb") if om and om.get("rating") else (None, "")
        if rating is None and tm:
            rating = imdb_rating(tm["imdb"])
            rsrc = "IMDb" if rating else ""
            if rating is None and tm["votes"] >= 20 and tm["vote"]:
                rating, rsrc = round(float(tm["vote"]), 1), "TMDB"
        genres = (tm or {}).get("genres") or (om or {}).get("genres") or []
        runtime = (tm or {}).get("runtime") or (om or {}).get("runtime")
        keep.append({"title": title,     # as written on the source page
                     "type": kind, "language": lang, "platform": plat,
                     "date": rdate.isoformat(), "note": str(it.get("note", ""))[:60],
                     "genres": genres, "runtime": runtime, "rating": rating, "rating_src": rsrc,
                     "checks": f"{len(pages_ok)} page{'s' if len(pages_ok) != 1 else ''}"
                               + (" + IMDb" if om else "") + (" + TMDB" if tm else "")
                               + (" + platform" if plat_seen else "") + (" + IN date" if tmdb_date_ok else "")})
    return keep, notes


# ---------------------------------------------------------------- 5. post
def caption(rows, now):
    mon, sun, fri = week_bounds(now)
    th = [r for r in rows if r["platform"] == "Theatres"]
    ott = [r for r in rows if r["platform"] != "Theatres"]
    parts = [f"New this week ({mon.strftime('%-d %b')}–{sun.strftime('%-d %b')})."]
    if th:
        parts.append("In cinemas " + fri.strftime("%a %-d %b") + ": " +
                     ", ".join(f"{r['title']} ({r['language']})" for r in th) + ".")
    if ott:
        by = {}
        for r in ott:
            by.setdefault(r["platform"], []).append(f"{r['title']} ({r['language']})")
        parts.append("On OTT: " + " · ".join(f"{p}: {', '.join(v)}" for p, v in by.items()) + ".")
    txt = " ".join(parts)
    txt += ("\nఈ వారం థియేటర్లలో, OTTలో కొత్త సినిమాలు, సిరీస్‌లు.\n"
            "Ratings are IMDb/TMDB at the time of posting. Dates as announced; check your platform.\n"
            "#AroundUs #OTTReleases #NewReleases #TeluguMovies #TamilMovies #Bollywood")
    return txt[:2200]


def main():
    for k in ("ANTHROPIC_API_KEY", "TELEGRAM_BOT_TOKEN", "TELEGRAM_ADMIN_CHAT_ID"):
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
    marker = os.path.join(folder, "ott_pending.txt")
    summary_path = os.path.join(folder, "ott_summary.txt")
    if any(v.get("name") == "releases" for v in queue.values()):
        daily.log("releases post already made today")
        open(marker, "w").close()
        open(summary_path, "w").close()
        return
    handle = daily.ig_handle()
    if handle:
        slides.HANDLE = handle
    notes, keys, rows = [], [], []
    if not (TMDB_KEY or OMDB_KEY):
        notes.append("No film-database key (OMDB_API_KEY / TMDB_API_KEY): every title needs two pages, and no ratings.")
    model = daily.pick_model()
    items, note = collect(now, model)
    notes.append(note)
    rows, vnotes = verify(items, now)
    notes += vnotes
    th = [r for r in rows if r["platform"] == "Theatres"]
    ott = sorted([r for r in rows if r["platform"] != "Theatres"], key=lambda r: (PLATFORMS.index(r["platform"]), r["date"]))
    if len(rows) >= 3:
        mon, sun, fri = week_bounds(now)
        sub = f"{mon.strftime('%-d %b')} – {sun.strftime('%-d %b %Y')}"
        sec_th = ("In cinemas · " + fri.strftime("%A %-d %B"), th)
        sec_ott = "On OTT · " + f"{mon.strftime('%-d %b')} – {sun.strftime('%-d %b')}"
        pages = []
        if len(th) + len(ott) <= MAX_ROWS:          # everything fits on one slide
            secs = ([sec_th] if th else []) + ([(sec_ott, ott)] if ott else [])
            pages.append(secs)
        else:
            if th:
                pages.append([(sec_th, th[:MAX_ROWS])])
            for i in range(0, len(ott), MAX_ROWS):
                pages.append([(sec_ott, ott[i:i + MAX_ROWS])])
        pages = pages[:MAX_SLIDES]
        files = []
        for i, secs in enumerate(pages):
            fn = f"14-releases-{i + 1}.jpg"
            hint = None
            if i < len(pages) - 1:
                hint = ("Swipe for OTT", "next") if (i == 0 and th and len(pages) > 1) else ("More on the next slide", "next")
            slides.releases(secs, sub, os.path.join(folder, fn), hint=hint,
                            page=(i + 1, len(pages)) if len(pages) > 1 else None)
            files.append(fn)
        key = f"{day}/{files[0]}"
        queue[key] = {"name": "releases", "caption": caption(rows, now), "status": "waiting", "files": files}
        with open(qpath, "w") as fh:
            json.dump(queue, fh, ensure_ascii=False, indent=1)
        keys.append(key)
        lines = [f"🎬 Around Us · Friday releases · {now.strftime('%A, %d %b')}",
                 f"{len(th)} in cinemas + {len(ott)} on OTT, {len(files)} slide{'s' if len(files) > 1 else ''}", ""]
        lines += [f"• {r['title']} · {r['platform']} · {r['language']} · checks: {r['checks']}"
                  + (f" · {r['rating_src']} {r['rating']}" if r["rating"] else "") for r in th + ott]
    else:
        lines = [f"🎬 Around Us · Friday releases · {now.strftime('%A, %d %b')}", "",
                 f"No post: only {len(rows)} release{'s' if len(rows) != 1 else ''} could be verified (need 3)."]
    if notes:
        lines += ["", "Notes:"] + ["• " + n for n in notes[:14]]
    with open(summary_path, "w") as fh:
        fh.write("\n".join(lines))
    with open(marker, "w") as fh:
        fh.write("\n".join(keys))
    daily.log("releases saved", keys, notes[:5])


if __name__ == "__main__":
    main()
