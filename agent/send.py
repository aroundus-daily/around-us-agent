"""Around Us - publish or preview today's posts (runs AFTER the images are uploaded to GitHub).

AUTO_PUBLISH=1 (default in the workflows): every new post is published to Instagram straight away,
  and Telegram gets each image with its Instagram link. If a post fails, Telegram gets it with
  ✅ Post / ❌ Skip buttons so you can retry with one tap.
AUTO_PUBLISH=0: nothing is published; Telegram gets each image with ✅ Post / ❌ Skip buttons.
Either way, each image is checked to be really online first (Instagram fetches it from GitHub).
"""
import json
import os
import sys
import time
import urllib.request
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import daily  # noqa: E402  (re-uses its Telegram helpers and settings)
import approve  # noqa: E402  (Instagram publishing)

AUTO = os.environ.get("AUTO_PUBLISH", "1").strip() != "0"
REPO = os.environ.get("GITHUB_REPOSITORY", "aroundus-daily/around-us-agent")
BRANCH = os.environ.get("GITHUB_REF_NAME", "main")


def online(key, tries=12):
    url = f"https://raw.githubusercontent.com/{REPO}/{BRANCH}/posts/{key}"
    for _ in range(tries):
        try:
            req = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "AroundUsBot"})
            with urllib.request.urlopen(req, timeout=20) as r:
                if r.status == 200:
                    return True
        except Exception:
            pass
        time.sleep(10)
    return False


EOD_NAMES = ("rupee", "nifty", "movers", "gold", "silver", "weekly")  # sent by their own later runs, not the morning one


def tg_album(paths, caption):
    """Telegram preview of a carousel: all slides as one album (albums can't carry buttons)."""
    boundary = "----AroundUsAlbum" + str(int(time.time()))
    media = [{"type": "photo", "media": f"attach://p{i}", **({"caption": caption[:1024]} if i == 0 else {})}
             for i in range(len(paths))]
    parts = [f'--{boundary}\r\nContent-Disposition: form-data; name="chat_id"\r\n\r\n{daily.TG_CHAT}\r\n',
             f'--{boundary}\r\nContent-Disposition: form-data; name="media"\r\n\r\n{json.dumps(media)}\r\n']
    body = "".join(parts).encode()
    for i, p in enumerate(paths):
        with open(p, "rb") as fh:
            body += (f'--{boundary}\r\nContent-Disposition: form-data; name="p{i}"; filename="slide{i}.jpg"\r\n'
                     f"Content-Type: image/jpeg\r\n\r\n").encode() + fh.read() + b"\r\n"
    body += f"--{boundary}--\r\n".encode()
    return daily.http("POST", f"https://api.telegram.org/bot{daily.TG_TOKEN}/sendMediaGroup",
                      {"Content-Type": f"multipart/form-data; boundary={boundary}"}, body, timeout=90)


def tg_video(path, caption, buttons=None):
    """Telegram preview of a reel (sendVideo, multipart)."""
    boundary = "----AroundUsVideo" + str(int(time.time()))
    with open(path, "rb") as fh:
        vid = fh.read()
    parts = f'--{boundary}\r\nContent-Disposition: form-data; name="chat_id"\r\n\r\n{daily.TG_CHAT}\r\n'
    parts += f'--{boundary}\r\nContent-Disposition: form-data; name="caption"\r\n\r\n{caption[:1024]}\r\n'
    parts += f'--{boundary}\r\nContent-Disposition: form-data; name="supports_streaming"\r\n\r\ntrue\r\n'
    if buttons:
        parts += (f'--{boundary}\r\nContent-Disposition: form-data; name="reply_markup"\r\n\r\n'
                  f'{json.dumps({"inline_keyboard": [buttons]})}\r\n')
    body = (parts + f'--{boundary}\r\nContent-Disposition: form-data; name="video"; filename="reel.mp4"\r\n'
            "Content-Type: video/mp4\r\n\r\n").encode() + vid + f"\r\n--{boundary}--\r\n".encode()
    return daily.http("POST", f"https://api.telegram.org/bot{daily.TG_TOKEN}/sendVideo",
                      {"Content-Type": f"multipart/form-data; boundary={boundary}"}, body, timeout=120)


def send_day(day, check_online=True, only=None):
    folder = os.path.join(daily.POSTS_DIR, day)
    with open(os.path.join(folder, "queue.json")) as fh:
        queue = json.load(fh)
    if only is None:
        with open(os.path.join(folder, "summary.txt")) as fh:
            summary = fh.read()
        daily.tg("sendMessage", chat_id=daily.TG_CHAT, text=summary)
    for key, item in queue.items():
        if only is not None and key not in only:
            continue
        if only is None and item.get("name") in EOD_NAMES:
            continue
        if item.get("status") in ("posted", "skipped"):
            continue   # never re-send (or re-post) something already handled
        path = os.path.join(daily.POSTS_DIR, key)
        files = [f"{day}/{f}" for f in item.get("files", [])] or [key]
        kind = item.get("kind", "image")
        cover = f"{day}/{item['cover']}" if item.get("cover") else None
        if check_online and not all(online(k) for k in files + ([cover] if cover else [])):
            daily.tg("sendMessage", chat_id=daily.TG_CHAT,
                     text=f"⚠️ {item['name']}: image did not appear online, so no ✅ button. Re-run its workflow in GitHub Actions.")
            continue
        buttons = [{"text": "✅ Post", "callback_data": f"post|{key}"[:64]},
                   {"text": "❌ Skip", "callback_data": f"skip|{key}"[:64]}]
        caption = item["caption"]
        if AUTO and item.get("status") == "waiting":
            ok, info = approve.publish(files, caption, kind=kind, cover=cover)
            if ok:
                item["status"], item["permalink"] = "posted", info
                item["posted_at"] = datetime.now(daily.IST).isoformat()
                buttons = None
                caption = f"✅ Live on Instagram: {info}\n\n" + caption
                daily.log(f"auto-posted {key}: {info}")
            else:
                item["error"] = info
                caption = f"⚠️ Auto-post failed: {info}\nTap ✅ Post to retry.\n\n" + caption
                daily.log(f"auto-post failed {key}: {info}")
            with open(os.path.join(folder, "queue.json"), "w") as fh:
                json.dump(queue, fh, ensure_ascii=False, indent=1)
            time.sleep(10)   # a short pause between posts
        if kind == "reel":
            code, js = tg_video(path, caption, buttons)
        elif len(files) > 1:
            code, js = tg_album([os.path.join(daily.POSTS_DIR, k) for k in files], caption)
            if code == 200 and buttons:
                code, js = daily.tg("sendMessage", chat_id=daily.TG_CHAT,
                                    text=f"👆 {item['name']}: {len(files)} slides, NOT posted yet. "
                                         "Tap ✅ Post to publish them together as one Instagram post.",
                                    reply_markup={"inline_keyboard": [buttons]})
        else:
            code, js = daily.tg_photo(path, caption, buttons)
        if code != 200:
            daily.log(f"telegram {key} failed: {str(js)[:150]}")
        else:
            daily.log(f"sent {key}")


if __name__ == "__main__":
    day = datetime.now(daily.IST).strftime("%Y-%m-%d")
    if len(sys.argv) > 1 and sys.argv[1] in ("--eod", "--gold", "--silver", "--weekly"):
        prefix = sys.argv[1][2:]
        folder = os.path.join(daily.POSTS_DIR, day)
        marker = os.path.join(folder, f"{prefix}_pending.txt")
        if os.path.exists(marker):
            summary = os.path.join(folder, f"{prefix}_summary.txt")
            text = open(summary).read().strip() if os.path.exists(summary) else ""
            if text:
                daily.tg("sendMessage", chat_id=daily.TG_CHAT, text=text)
            keys = [k for k in open(marker).read().split() if k]
            if keys:
                send_day(day, only=keys)
    else:
        send_day(sys.argv[1] if len(sys.argv) > 1 else day)
