"""Around Us - one-tap publisher.

Runs every few minutes. Reads your taps on the Telegram buttons:
  ✅ Post  -> publishes that image + caption to Instagram (official Instagram API)
  ❌ Skip  -> marks it skipped
Only taps from TELEGRAM_ADMIN_CHAT_ID are accepted.
Images are fetched by Instagram from this (public) repo.
"""
import json
import os
import time
import urllib.error
import urllib.parse
import urllib.request
from datetime import datetime, timedelta, timezone

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
POSTS_DIR = os.path.join(ROOT, "posts")
STATE = os.path.join(ROOT, "data", "telegram_offset.json")
IST = timezone(timedelta(hours=5, minutes=30))

TG_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "").strip()
TG_CHAT = os.environ.get("TELEGRAM_ADMIN_CHAT_ID", "").strip()
IG_USER = os.environ.get("IG_USER_ID", "").strip()
IG_TOKEN = os.environ.get("IG_ACCESS_TOKEN", "").strip()
REPO = os.environ.get("GITHUB_REPOSITORY", "aroundus-daily/around-us-agent")
BRANCH = os.environ.get("GITHUB_REF_NAME", "main")
GRAPH = "https://graph.instagram.com/v23.0"


def log(*a):
    print(datetime.now(IST).strftime("%H:%M:%S"), *a, flush=True)


def http(method, url, data=None, timeout=40):
    body, headers = None, {"User-Agent": "AroundUsBot"}
    if isinstance(data, dict) and method == "POST":
        body = json.dumps(data).encode()
        headers["Content-Type"] = "application/json"
    req = urllib.request.Request(url, data=body, method=method, headers=headers)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode() or "{}")
        except Exception:
            return e.code, {}
    except Exception as e:
        return 0, {"error": {"message": str(e)}}


def tg(method, **params):
    return http("POST", f"https://api.telegram.org/bot{TG_TOKEN}/{method}", params)


def ig_error(js):
    return ((js or {}).get("error") or {}).get("message", str(js))[:200]


def image_urls(key):
    # raw GitHub first; jsDelivr CDN as a fallback (both serve image/jpeg for public repos)
    return [f"https://raw.githubusercontent.com/{REPO}/{BRANCH}/posts/{key}",
            f"https://cdn.jsdelivr.net/gh/{REPO}@{BRANCH}/posts/{key}"]


def publish(key, caption):
    """Instagram API: create container -> wait until ready -> publish. Returns (ok, message)."""
    last = ""
    for url in image_urls(key):
        q = urllib.parse.urlencode({"image_url": url, "caption": caption, "access_token": IG_TOKEN})
        code, js = http("POST", f"{GRAPH}/{IG_USER}/media?{q}")
        if code != 200 or "id" not in js:
            last = f"create failed ({code}): {ig_error(js)}"
            log(last, "| url:", url)
            continue
        cid = js["id"]
        for _ in range(12):  # up to ~1 minute
            c2, st = http("GET", f"{GRAPH}/{cid}?fields=status_code&access_token={IG_TOKEN}")
            status = st.get("status_code")
            if status == "FINISHED":
                break
            if status == "ERROR":
                last = "Instagram could not process the image"
                break
            time.sleep(5)
        if last == "Instagram could not process the image":
            continue
        code, pub = http("POST", f"{GRAPH}/{IG_USER}/media_publish?" +
                         urllib.parse.urlencode({"creation_id": cid, "access_token": IG_TOKEN}))
        if code == 200 and "id" in pub:
            c3, info = http("GET", f"{GRAPH}/{pub['id']}?fields=permalink&access_token={IG_TOKEN}")
            return True, info.get("permalink", "posted")
        last = f"publish failed ({code}): {ig_error(pub)}"
        log(last)
    return False, last


def load_queue(day):
    p = os.path.join(POSTS_DIR, day, "queue.json")
    try:
        with open(p) as fh:
            return p, json.load(fh)
    except Exception:
        return p, None


def save(path, obj):
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w") as fh:
        json.dump(obj, fh, ensure_ascii=False, indent=1)


def image_is_online(key):
    req = urllib.request.Request(image_urls(key)[0], method="HEAD", headers={"User-Agent": "AroundUsBot"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.status == 200
    except Exception:
        return False


def main():
    for k, v in {"TELEGRAM_BOT_TOKEN": TG_TOKEN, "TELEGRAM_ADMIN_CHAT_ID": TG_CHAT,
                 "IG_USER_ID": IG_USER, "IG_ACCESS_TOKEN": IG_TOKEN}.items():
        if not v:
            raise SystemExit(f"{k} missing")
    try:
        with open(STATE) as fh:
            offset = json.load(fh).get("offset", 0)
    except Exception:
        offset = 0
    code, js = http("GET", f"https://api.telegram.org/bot{TG_TOKEN}/getUpdates?offset={offset}"
                           f"&timeout=0&allowed_updates=%5B%22callback_query%22%5D")
    updates = js.get("result", []) if code == 200 else []
    log(f"{len(updates)} new taps")
    changed = False
    for u in updates:
        offset = max(offset, u["update_id"] + 1)
        changed = True
        cb = u.get("callback_query")
        if not cb:
            continue
        if str(cb.get("from", {}).get("id")) != TG_CHAT:
            tg("answerCallbackQuery", callback_query_id=cb["id"], text="Not allowed")
            continue
        action, _, key = (cb.get("data") or "").partition("|")
        day = key.split("/")[0]
        qpath, queue = load_queue(day)
        msg = cb.get("message", {})
        mid = msg.get("message_id")
        if not queue or key not in queue:
            recent = day >= (datetime.now(IST) - timedelta(days=1)).strftime("%Y-%m-%d")
            tg("answerCallbackQuery", callback_query_id=cb["id"], show_alert=recent,
               text="Images still uploading. Tap ✅ again in 2 minutes." if recent else "Post not found (older than 7 days)")
            continue
        item = queue[key]
        if item.get("status") in ("posted", "skipped"):
            tg("answerCallbackQuery", callback_query_id=cb["id"], text=f"Already {item['status']}")
            continue
        if action == "skip":
            item["status"] = "skipped"
            tg("answerCallbackQuery", callback_query_id=cb["id"], text="Skipped")
            tg("editMessageReplyMarkup", chat_id=TG_CHAT, message_id=mid,
               reply_markup={"inline_keyboard": [[{"text": "❌ Skipped", "callback_data": "noop|"}]]})
        elif action == "post":
            if not image_is_online(key):
                tg("answerCallbackQuery", callback_query_id=cb["id"],
                   text="Image still uploading. Tap ✅ again in 2 minutes.", show_alert=True)
                continue
            tg("answerCallbackQuery", callback_query_id=cb["id"], text="Posting to Instagram…")
            ok, info = publish(key, item["caption"])
            if ok:
                item["status"], item["permalink"] = "posted", info
                item["posted_at"] = datetime.now(IST).isoformat()
                tg("editMessageReplyMarkup", chat_id=TG_CHAT, message_id=mid,
                   reply_markup={"inline_keyboard": [[{"text": "✅ Live on Instagram", "url": info}]]}
                   if info.startswith("http") else {"inline_keyboard": []})
                tg("sendMessage", chat_id=TG_CHAT, reply_to_message_id=mid, text=f"✅ Posted: {info}")
            else:
                item["status"], item["error"] = "failed", info
                tg("sendMessage", chat_id=TG_CHAT, reply_to_message_id=mid,
                   text=f"⚠️ Could not post: {info}\nTap ✅ again to retry.")
                item["status"] = "waiting"
        else:
            tg("answerCallbackQuery", callback_query_id=cb["id"])
            continue
        save(qpath, queue)
    if changed:
        save(STATE, {"offset": offset})
    # keep the Instagram token alive (refresh at most once a day)
    refresh_token_daily()


def refresh_token_daily():
    marker = os.path.join(ROOT, "data", "token_refreshed.txt")
    today = datetime.now(IST).strftime("%Y-%m-%d")
    try:
        if open(marker).read().strip() == today:
            return
    except Exception:
        pass
    code, js = http("GET", "https://graph.instagram.com/refresh_access_token?grant_type=ig_refresh_token"
                           f"&access_token={IG_TOKEN}")
    if code == 200 and js.get("access_token"):
        days = int(js.get("expires_in", 0)) // 86400
        log(f"token refreshed, valid {days} more days")
        if js["access_token"] != IG_TOKEN:
            tg("sendMessage", chat_id=TG_CHAT,
               text="🔑 Instagram gave a NEW access token. Please update the GitHub secret IG_ACCESS_TOKEN "
                    "with the token below, then delete this message:\n\n" + js["access_token"])
    else:
        log("token refresh failed:", ig_error(js))
        if code != 0:
            tg("sendMessage", chat_id=TG_CHAT,
               text="⚠️ Instagram token problem: " + ig_error(js) +
                    "\nGenerate a new token in the Meta app and update the IG_ACCESS_TOKEN secret.")
    with open(marker, "w") as fh:
        fh.write(today)


if __name__ == "__main__":
    main()
