"""Stage 5: the draft listing, in Shopify's product-CSV shape so it imports as-is later."""
import csv
import os
import re

SHOPIFY_COLUMNS = ["Handle", "Title", "Body (HTML)", "Vendor", "Product Category", "Type", "Tags",
                   "Published", "Variant Price", "Variant Requires Shipping", "Image Src", "Status"]


def make_listing(hook, cand, cfg, image_path, event_date):
    title = f"{hook.title.title().replace('On ', 'on ').replace('I-', 'I-')} {hook.year} Badge"
    when = f"{event_date:%B} {event_date.day}, {event_date.year}"
    road = f" on {cand.road}" if cand.road and cand.road not in hook.title else ""
    body = (f"<p>You were there. {when}{road}: {hook.title.title()}.</p>"
            f"<p>A collectible badge sticker that fits any open slot on your "
            f"<em>I Survived Seattle Traffic</em> base sticker. Weatherproof vinyl, "
            f"{cfg.width_in}&quot; x {cfg.height_in}&quot;.</p>")
    handle = re.sub(r"[^a-z0-9]+", "-", f"{hook.title} {hook.year}".lower()).strip("-")
    return {
        "Handle": handle, "Title": title, "Body (HTML)": body, "Vendor": cfg.vendor,
        "Product Category": "Arts & Entertainment > Hobbies & Creative Arts > Collectibles",
        "Type": "Badge Sticker", "Tags": f"badge, {hook.year}, live-event",
        "Published": "FALSE", "Variant Price": cfg.badge_price, "Variant Requires Shipping": "TRUE",
        "Image Src": os.path.abspath(image_path), "Status": "draft",
    }


def append_csv(path, row):
    new = not os.path.exists(path)
    with open(path, "a", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=SHOPIFY_COLUMNS)
        if new:
            w.writeheader()
        w.writerow(row)
