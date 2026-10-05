"""Around Us - send today's posts to Telegram (runs AFTER the images are uploaded to GitHub).

Checks each image is really online before sending its ✅ Post button.
"""
import json
import os
import sys
import time
import urllib.request
from datetime import datetime

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import daily  # noqa: E402  (re-uses its Telegram helpers and settings)

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


def send_day(day, check_online=True, only=None):
    folder = os.path.join(daily.POSTS_DIR, day)
    with open(os.path.join(folder, "queue.json")) as fh:
        queue = json.load(fh)
    if only is None:
        with open(os.path.join(folder, "summary.txt")) as fh:
            summary = fh.read()
        daily.tg("sendMessage", chat_id=daily.TG_CHAT, text=summary)
    for key, item in queue.items():
        if only is not None and key != only:
            continue
        if only is None and item.get("name") == "movers":
            continue
        path = os.path.join(daily.POSTS_DIR, key)
        if check_online and not online(key):
            daily.tg("sendMessage", chat_id=daily.TG_CHAT,
                     text=f"⚠️ {item['name']}: image did not appear online, so no ✅ button. Re-run 'Daily stories'.")
            continue
        buttons = [{"text": "✅ Post", "callback_data": f"post|{key}"[:64]},
                   {"text": "❌ Skip", "callback_data": f"skip|{key}"[:64]}]
        code, js = daily.tg_photo(path, item["caption"], buttons)
        if code != 200:
            daily.log(f"telegram {key} failed: {str(js)[:150]}")
        else:
            daily.log(f"sent {key}")


if __name__ == "__main__":
    day = datetime.now(daily.IST).strftime("%Y-%m-%d")
    if len(sys.argv) > 1 and sys.argv[1] == "--eod":
        marker = os.path.join(daily.POSTS_DIR, day, "eod_pending.txt")
        if os.path.exists(marker):
            send_day(day, only=open(marker).read().strip())
    else:
        send_day(sys.argv[1] if len(sys.argv) > 1 else day)
