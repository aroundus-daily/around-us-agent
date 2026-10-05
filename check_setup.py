"""Around Us - setup check.

Tests every secret and sends a green/red report to your Telegram.
Uses only the Python standard library (nothing to install).
Secret values are never printed.
"""
import json
import os
import re
import urllib.error
import urllib.parse
import urllib.request

ENV = {k: os.environ.get(k, "").strip() for k in [
    "ANTHROPIC_API_KEY", "TELEGRAM_BOT_TOKEN", "TELEGRAM_ADMIN_CHAT_ID",
    "IG_USER_ID", "IG_ACCESS_TOKEN", "IG_APP_SECRET",
]}


def http(method, url, headers=None, data=None, timeout=20):
    body = json.dumps(data).encode() if data is not None else None
    h = {"Content-Type": "application/json", **(headers or {})}
    req = urllib.request.Request(url, data=body, headers=h, method=method)
    try:
        with urllib.request.urlopen(req, timeout=timeout) as r:
            return r.status, json.loads(r.read().decode() or "{}")
    except urllib.error.HTTPError as e:
        try:
            return e.code, json.loads(e.read().decode() or "{}")
        except Exception:
            return e.code, {}
    except Exception as e:  # network errors
        return 0, {"error": str(e)}


def missing(name):
    return None if ENV[name] else f"{name} is missing - add it in GitHub secrets"


def check_anthropic():
    if (m := missing("ANTHROPIC_API_KEY")):
        return False, m
    code, js = http("GET", "https://api.anthropic.com/v1/models",
                    {"x-api-key": ENV["ANTHROPIC_API_KEY"], "anthropic-version": "2023-06-01"})
    if code == 200:
        n = len(js.get("data", []))
        return True, f"key works ({n} models available)"
    if code == 401:
        return False, "key rejected - re-copy ANTHROPIC_API_KEY"
    return False, f"unexpected response ({code}) - check billing/credit"


def check_telegram_bot():
    if (m := missing("TELEGRAM_BOT_TOKEN")):
        return False, m
    code, js = http("GET", f"https://api.telegram.org/bot{ENV['TELEGRAM_BOT_TOKEN']}/getMe")
    if code == 200 and js.get("ok"):
        return True, "bot @" + js["result"].get("username", "?")
    return False, "token rejected - re-copy TELEGRAM_BOT_TOKEN (without the word 'bot')"


def check_instagram():
    if (m := missing("IG_ACCESS_TOKEN") or missing("IG_USER_ID")):
        return False, m
    q = urllib.parse.urlencode({"fields": "user_id,username,account_type",
                                "access_token": ENV["IG_ACCESS_TOKEN"]})
    code, js = http("GET", f"https://graph.instagram.com/v23.0/me?{q}")
    if code != 200:
        msg = js.get("error", {}).get("message", "")[:120]
        return False, f"token rejected ({code}) {msg}".strip()
    uname = js.get("username", "?")
    ids = {str(js.get("user_id", "")), str(js.get("id", ""))}
    if ENV["IG_USER_ID"] not in ids:
        return False, f"token is for @{uname}, but IG_USER_ID doesn't match it"
    acct = js.get("account_type", "")
    note = f" ({acct.lower()})" if acct else ""
    return True, f"connected as @{uname}{note}"


def check_app_secret():
    if (m := missing("IG_APP_SECRET")):
        return False, m
    if re.fullmatch(r"[0-9a-f]{32}", ENV["IG_APP_SECRET"]):
        return True, "format looks right"
    return False, "doesn't look like an app secret (expected 32 characters, 0-9 a-f)"


def check_chat_id():
    if (m := missing("TELEGRAM_ADMIN_CHAT_ID")):
        return False, m
    if re.fullmatch(r"-?\d{5,15}", ENV["TELEGRAM_ADMIN_CHAT_ID"]):
        return True, "format looks right"
    return False, "should be digits only (e.g. 512345678)"


def main():
    results = [
        ("Claude (Anthropic)", *check_anthropic()),
        ("Telegram bot", *check_telegram_bot()),
        ("Telegram chat ID", *check_chat_id()),
        ("Instagram", *check_instagram()),
        ("Instagram app secret", *check_app_secret()),
    ]
    lines = [f"{'🟢' if ok else '🔴'} {name}: {detail}" for name, ok, detail in results]
    all_ok = all(ok for _, ok, _ in results)
    header = "✅ Around Us setup: all good" if all_ok else "⚠️ Around Us setup: needs attention"
    report = header + "\n\n" + "\n".join(lines)
    print(report)

    sent = False
    if ENV["TELEGRAM_BOT_TOKEN"] and ENV["TELEGRAM_ADMIN_CHAT_ID"]:
        code, js = http("POST", f"https://api.telegram.org/bot{ENV['TELEGRAM_BOT_TOKEN']}/sendMessage",
                        data={"chat_id": ENV["TELEGRAM_ADMIN_CHAT_ID"], "text": report})
        sent = code == 200 and js.get("ok")
        if not sent:
            print("\nCould not send to Telegram - check TELEGRAM_ADMIN_CHAT_ID, "
                  "and that you pressed Start in the bot chat.")
    if not all_ok:
        raise SystemExit(1)


if __name__ == "__main__":
    main()
