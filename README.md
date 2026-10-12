# Around Us — Instagram agent

Automated posts for [@around_us.daily](https://www.instagram.com/around_us.daily/): world and India news, South India and
Andhra Pradesh, gold and silver rates, the rupee, Nifty 50 and NSE indices, a weekly markets Reel and Friday film
releases. Python on GitHub Actions. Images are drawn with Pillow, the Reel with Pillow + ffmpeg, and Instagram fetches
them straight from this public repo. One Claude call a day for the news posts, one a week for releases; every
number post is built from data sources with no AI.

## What runs when (IST)

| Workflow | When | Makes | Claude |
|---|---|---|---|
| **Daily stories** (`daily.yml` → `agent/daily.py`, `send.py`) | 6:47 AM, every day | India in the world · World markets (Mon–Fri) · Top 10 in India · Across the South · Andhra today | 1 call |
| **Gold and silver rates** (`gold.yml` → `gold.py`, `silver.py`, `send.py --gold` / `--silver`) | 10:17 AM daily, retry 1:17 PM | Gold rate AP + Telangana (2-slide carousel) · Silver rate AP + Telangana (2-slide carousel) | none |
| **Friday releases** (`ott.yml` → `ott.py`, `send.py --ott`) | 9:17 AM Friday | New Telugu / Tamil / Hindi films and series in cinemas and on OTT, 1–3 slides | 1 call + up to 5 web searches |
| **End of day movers** (`eod.yml` → `eod.py`, `send.py --eod`) | 4:07 PM, Mon–Fri | Rupee today · Nifty 50, all 50 stocks · Nifty 50 movers · Nifty 50 last 15 sessions · Nifty indices at the close (Nifty posts skipped on market holidays) | none |
| **Weekly markets reel** (`weekly.yml` → `weekly.py`, `reel.py`, `music.py`, `send.py --weekly`) | 8:17 AM Saturday | 20-second Reel: the Nifty's week, top 10 weekly gainers and losers, the rupee's week | none |
| **Publish approved posts** (`approve.yml` → `approve.py`) | every 2 hours | Handles ✅ / ❌ taps from Telegram, auto-retries anything still waiting (max 3 tries), checks the Instagram token daily | none |
| **Check setup** (`check-setup.yml` → `check_setup.py`) | manual | Tests the six secrets and reports to Telegram | none |

That is 12 posts on a weekday, 7 on Saturday plus the Reel, 6 on Sunday, and one more on Fridays.

Every posting workflow does the same four steps: **make** the images → **push** them to `posts/<date>/` → **publish** to
Instagram (or send Telegram buttons when `AUTO_PUBLISH` is `0`) → **save** the status and Instagram links to
`posts/<date>/queue.json`.

## How accuracy is enforced

- **News** (Claude, one call): every line comes from a real headline; the outlet and date are taken from that headline
  by code, not by the model. A line whose numbers don't match its headline is replaced by the headline. Every line in
  "India in the world" must name India. No Telugu script on images (Telugu goes in the caption).
- **Rupee**: 3 sources (ECB via Frankfurter, open.er-api, fawazahmed0); published only when 2 agree within 0.6%.
- **Markets, Nifty 50, indices, weekly reel**: NSE data via Yahoo Finance; stale or implausible values are dropped,
  the Nifty post needs at least 45 of 50 stocks, the indices post at least 12 indices with today's close, and
  weekly moves are Friday close vs the previous Friday close. Yahoo throttling is retried with back-off.
- **Gold and silver**: GoodReturns city pages (AP: Vijayawada, Visakhapatnam, Tirupati, Guntur, Nellore; Telangana:
  Hyderabad, Warangal), cross-checked against BankBazaar's state pages within 0.5%. A city whose sources disagree is
  dropped; the slide shows the rate the state's cities share. Only today's rate is posted, never twice a day.
- **Friday releases**: Claude only *collects* candidates and must cite the page each one came from. The code opens
  every cited page and drops titles that aren't on it, then checks each title in a film database (OMDb / IMDb and/or
  TMDB, both optional) for language, currency and rating. A title is published only with two confirmations (two
  pages, or one page + the database); cinema releases need two pages. Fewer than 3 titles → no post.
- **Instagram**: images are served from this repo (raw GitHub, jsDelivr as fallback; jsDelivr first for video).
  Carousels and Reels are supported. "Application request limit reached" → wait 2 minutes and retry; anything still
  waiting is retried by the 2-hourly run.

Everything that was dropped, and why, is listed in the Telegram summary for that run.

## Setup

Secrets (repo → Settings → Secrets and variables → Actions → Secrets):

| Secret | From |
|---|---|
| `ANTHROPIC_API_KEY` | console.anthropic.com → API keys |
| `TELEGRAM_BOT_TOKEN` | @BotFather |
| `TELEGRAM_ADMIN_CHAT_ID` | `getUpdates` → `chat.id` (only this chat's taps are accepted) |
| `IG_USER_ID`, `IG_ACCESS_TOKEN` | Meta app → Instagram → API setup with Instagram login → Generate token (lasts 60 days; the agent reminds you in Telegram at 45) |
| `IG_APP_SECRET` | Meta app → App settings → Basic |
| `OMDB_API_KEY` (optional) | omdbapi.com → free key; IMDb ratings and an extra check for the releases post |
| `TMDB_API_KEY` (optional) | themoviedb.org → Settings → API (often unreachable from India; OMDb is enough) |

Variables (same page → Variables): `AUTO_PUBLISH` — unset or `1` publishes automatically; `0` sends every post to
Telegram with ✅ Post / ❌ Skip buttons instead.

Optional: drop a track you have the rights to at `assets/music.mp3` (or `.m4a` / `.wav`) and the Reel uses it instead of
the generated background music.

Run any workflow by hand from the **Actions** tab → choose the workflow → **Run workflow**.

## Layout

```
agent/
  daily.py     morning news posts (feeds → one Claude call → checks → images)
  gold.py      gold carousel        silver.py   silver carousel
  eod.py       rupee, Nifty 50, movers, 15 sessions, indices
  weekly.py    weekly reel data     reel.py     reel renderer    music.py  background music
  ott.py       Friday releases
  slides.py    every image layout (Pillow)
  send.py      publish or send to Telegram      approve.py   Telegram taps → Instagram
fonts/         Inter, Bricolage Grotesque, Instrument Serif
posts/<date>/  images, videos, queue.json (status + Instagram links), run summaries — kept 7 days
data/          seen headlines, market/gold/silver history, Telegram offset, token dates
```

For information only; nothing here is investment advice. Gold and silver rates exclude GST and making charges.
