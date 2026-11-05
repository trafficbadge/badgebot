# Badgebot: Seattle traffic badge pipeline (feasibility prototype)

Watches WSDOT for an epic Seattle traffic event, turns it into a print-ready badge sticker and
a draft Shopify listing, and emails you. Safe badges publish right away and the email carries an
**Unpublish** link that works whenever you next see it. Sensitive ones wait for your **Approve**.

```
WSDOT travel times + alerts ─▶ detect ─▶ hook + title ─▶ safety gate ─▶ badge ─▶ listing ─▶ email you
                                                          │
                              BLOCK: logged only          PASS: live now, email has [Unpublish]
                              (deaths, conflict,          HOLD: waits for [Approve] / [Reject]
                               officeholders,             (injuries, celebrities, brands; expires in 3 days)
                               injected words)            HOLD + next morning: civic gatherings
```

## Event categories
| Category | Examples | Tier | Release |
| --- | --- | --- | --- |
| harm | deaths, serious injuries | BLOCK | never |
| conflict | riots, clashes, arrests, looting, property damage | BLOCK | never |
| officeholder | politicians, candidates, dignitaries, motorcades, summits | BLOCK | never |
| gathering | march, rally, strike, vigil, parade, public celebration | HOLD | after your Approve, no earlier than 9am the next morning |
| incident | spills, weather, bridges, closures | PASS (or HOLD for injuries, celebrities, brands) | immediately |

Gathering badges name only the act ("MARCH ON I-5"), never the cause, a slogan, a group or a
person, even when the alert text names them; the picture is a crowd holding blank signs.

## Try it with no accounts at all

```bash
pip install -r requirements.txt
python -m playwright install chromium      # renders the badge artwork
python -m pytest -q                         # 54 acceptance tests, about a minute
python -m badgebot replay replays/blueberry_405_2018.json
python -m badgebot status
```
Without SMTP settings, emails land in `data/outbox/` as .eml files; badges and run logs land in `data/runs/`.
The files in `replays/` are **synthetic reconstructions** for testing, not real WSDOT records.

## Going live

1. **WSDOT**: free access code at https://wsdot.wa.gov/traffic/api/.
2. **A dedicated sending email account** (iCloud, Fastmail, Yahoo or Gmail) with an
   **app password** created in that account's security settings. It only ever emails you.
3. **Anthropic API key** (optional): Claude-written titles and AI-drawn icons.
4. **Fonts** are bundled in `badgebot/fonts` (Archivo Black for the banner, Archivo Condensed
   Bold and Medium for patches and the URL line; Open Font License, see OFL.txt). Nothing to do.
5. **A small always-on server** with a public HTTPS address, so the email links work.
6. Set the environment and run:
   ```bash
   export WSDOT_ACCESS_CODE=...
   export SMTP_HOST=smtp.mail.me.com SMTP_PORT=587          # your provider's SMTP server
   export SMTP_USER=alerts@... SMTP_PASSWORD=<app password> OWNER_EMAIL=you@...
   export PUBLIC_BASE_URL=https://your.host
   export ANTHROPIC_API_KEY=...      # optional
   python -m badgebot serve --port 8080 --with-watch
   ```

## Store, posts and mailing list (all automatic)

When a badge is cleared to publish (on its own, or after your Approve):
1. **Printify** uploads `pod.png`, creates a 2 × 2 in kiss-cut sticker and publishes it to Shopify.
2. The app **waits until the store page actually loads** (checked every tick). Nothing is
   announced before then. After `live_wait_min` (45) minutes you get a "Not live yet" email.
3. **Bluesky** and **Threads** get a post. The wording is a fixed template with only the title,
   the year and the store link. The picture is `social.jpg`, served publicly at `/s/<key>.jpg`
   only while the badge is live.
4. **Mailchimp**: the list email is drafted right away and sent `list_delay_min` (120) minutes later.
5. You get a "Published" email with links to the store page and each post, the list-email time,
   anything that did not work, and the Unpublish button.

**Unpublish** deletes the posts, deletes the unsent list email, and removes the Printify product.
Anything it can't undo is listed for you to do by hand. A list email already sent cannot be recalled.

Instagram is built but switched off (`INSTAGRAM_ENABLED=1` turns it on).
Instagram and Threads tokens last 60 days. The app refreshes them weekly and emails you if a
refresh fails.

Each service runs in **practice mode** until its settings are present. It writes the exact
requests it would have sent to `data/outbox/outlets.jsonl`.

| Service | Settings |
| --- | --- |
| Store | `STORE_URL` (e.g. https://seattletrafficbadges.com) |
| Printify | `PRINTIFY_TOKEN`, then run `python -m badgebot printify-setup` to print `PRINTIFY_SHOP_ID`, `PRINTIFY_BLUEPRINT_ID`, `PRINTIFY_PROVIDER_ID`, `PRINTIFY_VARIANT_ID` |
| Bluesky | `BLUESKY_HANDLE`, `BLUESKY_APP_PASSWORD` (Settings → Privacy and security → App passwords) |
| Threads | `THREADS_USER_ID`, `THREADS_TOKEN` (long-lived token from a Meta developer app with the Threads API) |
| Mailchimp | `MAILCHIMP_API_KEY`, `MAILCHIMP_LIST_ID` (Audience ID), `LIST_REPLY_TO` |

**To confirm on the first real run:**
- Whether deleting a product in Printify also removes it from Shopify. If not, Unpublish
  will list "hide the product in Shopify" as a by-hand step.
- The exact endpoint versions for Threads and Mailchimp.

Email links open a confirm page first and only act when you press its button, because mail apps
and link scanners open links on their own. Each run has its own secret token in its links.

## Buzz: WSDOT posts people react to (asks you first)
Every 15 minutes the watcher reads WSDOT's public Bluesky feed. A post scoring 30 or more
(likes + 2 x reposts + replies) within 48 hours becomes a **held draft**: you get "Needs your OK"
with Approve / Reject. It goes through the same safety checks as everything else, and it never publishes
on its own. If no safe title can be made (e.g. a post about the fall equinox), you just get
"Popular WSDOT post: worth a badge?". From Aug to Nov 2026 the bar was crossed about once a week.

Bridge, drawbridge, boat, tunnel and ferry are no longer hook words: they are place names in
routine posts ("all lanes closed due to boat traffic").

## Deploying on Railway
`Dockerfile` and `railway.json` are included. Attach a volume at `/data`, set the keys as
Railway Variables, and point a custom domain (e.g. bot.badtraffic206.com) at the service; then set
`PUBLIC_BASE_URL` to it. Social posts and the mailing list stay in practice mode until Printify is
configured, so a post can never carry a made-up store link.

## Tuning

Everything lives in `badgebot/config.py` (threshold, corridors, hold expiry, patch size,
palette, price) and `badgebot/vocab.py` (hook words, blocked and held word lists).

## The patch design
Locked from the Badge Style Explorations canvas: a 1.9 × 1.42 in wide oval with a thin white
rim at the cut line, a black "road" ring with a dashed white center line, the white title
arched across the top (shrinks to fit, condenses up to 18% as a last resort, otherwise the
badge is blocked), the white year at the bottom, and an orange center with a black picture
of exactly what the title says.

## Files a print vendor needs
Each run folder has `print.png` (300 dpi, 3 mm white bleed), `cutline.svg` (oval die line),
`badge.svg` (master, font embedded), `preview.png` (listing photo) and `pod.png`
(1800 × 1800 transparent, for a Printify 2 × 2 in kiss-cut sticker).

The base sticker: `python -m badgebot.basesticker out/` writes the 15 × 3.75 in file at
4500 × 1125 px.
