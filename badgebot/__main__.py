"""Command line.

  python -m badgebot replay replays/blueberry_405_2018.json   one recorded event through the pipeline
  python -m badgebot watch --every 2                          live: poll WSDOT every 2 min + tick
  python -m badgebot serve --port 8080                        web server for the email links
  python -m badgebot tick                                     expire held badges nobody approved
  python -m badgebot act <key> approve|reject|unpublish       act from the command line
  python -m badgebot status                                   list runs and their state
  python -m badgebot printify-setup                           find your shop, kiss-cut and 2x2 IDs
  python -m badgebot printify-test <shop id>                  publish + delete a throwaway test sticker
"""
import argparse
import os
import threading
import time

try:   # check security certificates the way the computer itself does (Windows, Mac, Linux),
    import truststore   # which also fills in certificate links some mail servers leave out
    truststore.inject_into_ssl()
except ImportError:
    pass

from .config import Config
from .pipeline import Pipeline
from .sources import fetch_live, load_replay


def main():
    ap = argparse.ArgumentParser(prog="badgebot")
    sub = ap.add_subparsers(dest="cmd", required=True)
    r = sub.add_parser("replay"); r.add_argument("file")
    w = sub.add_parser("watch"); w.add_argument("--every", type=float, default=2.0)
    s = sub.add_parser("serve"); s.add_argument("--port", type=int, default=int(os.environ.get("PORT", 8080)))
    s.add_argument("--with-watch", action="store_true", help="also poll WSDOT in the same process")
    sub.add_parser("tick")
    ac = sub.add_parser("act"); ac.add_argument("key"); ac.add_argument("action")
    sub.add_parser("status")
    sub.add_parser("printify-setup")
    sub.add_parser("publish-history")
    sub.add_parser("refresh-history")
    sub.add_parser("announce-v2")
    pt = sub.add_parser("printify-test"); pt.add_argument("shop_id"); pt.add_argument("--keep", action="store_true")
    a = ap.parse_args()
    cfg = Config()
    p = Pipeline(cfg)

    if a.cmd == "replay":
        for run in p.process(load_replay(a.file)):
            print(f"{run['key']}  {run['status']:<13} {run['tier']:<5} {run.get('title')}  "
                  f"{'; '.join(run['reasons'])}")
    elif a.cmd == "watch":
        watch(p, cfg, a.every)
    elif a.cmd == "tick":
        for run in p.tick():
            print(run["key"], run["status"], run["title"])
    elif a.cmd == "act":
        run = p.load(a.key) or {}
        print(p.act(a.key, a.action, run.get("token", ""))[1])
    elif a.cmd == "status":
        for run in p.all_runs():
            print(f"{run['key']}  {run['status']:<13} {run.get('title')}")
    elif a.cmd == "publish-history":
        for run in p.publish_history():
            print(run["key"], run["status"], run["title"], run.get("product_url") or "")
    elif a.cmd == "refresh-history":
        for run in p.refresh_history():
            print(run["key"], "new art", run["title"], run.get("product_url") or "")
    elif a.cmd == "announce-v2":
        print(p.announce_v2() or "Not yet: some V2 badges are still going live (or it was already drafted).")
    elif a.cmd == "printify-setup":
        printify_setup(cfg)
    elif a.cmd == "printify-test":
        printify_test(cfg, a.shop_id, a.keep)
    elif a.cmd == "serve":
        if a.with_watch:
            threading.Thread(target=watch, args=(p, cfg, 2.0), daemon=True).start()
        from .server import make_app
        make_app(p, cfg).run(host="0.0.0.0", port=a.port, threaded=True)


TWO_BY_TWO = __import__("re").compile(r'^\s*2\s*(?:"|in|inch)?\s*[x\u00d7]\s*2\b', __import__("re").I)


def _printify(cfg):
    import requests
    if not cfg.printify_token:
        raise SystemExit("Set PRINTIFY_TOKEN first.")
    base, h = "https://api.printify.com/v1", {"Authorization": f"Bearer {cfg.printify_token}",
                                              "User-Agent": "badgebot/1.0"}
    def get(path):
        r = requests.get(base + path, headers=h, timeout=30)
        if r.status_code >= 300:
            hint = " (the token was not accepted: check it was pasted whole)" if r.status_code in (401, 403) else ""
            raise SystemExit(f"Printify said HTTP {r.status_code}{hint}: {r.text[:200]}")
        return r.json()
    return base, h, get


def _kiss_cut_choices(get):
    """[(provider_id, provider_title, variant_id, variant_title)] for 2x2 kiss-cut stickers."""
    out = []
    for pp in get("/catalog/blueprints/400/print_providers.json"):
        variants = get(f"/catalog/blueprints/400/print_providers/{pp['id']}/variants.json").get("variants", [])
        for v in variants:
            if TWO_BY_TWO.match(v["title"]):
                out.append((pp["id"], pp["title"], v["id"], v["title"]))
        if not any(c[0] == pp["id"] for c in out):
            print(f"   (provider {pp['id']} {pp['title']}: no 2x2 size; sizes: "
                  f"{', '.join(v['title'] for v in variants[:8])})")
    return out


def printify_setup(cfg):
    """Prints the numbers for PRINTIFY_SHOP_ID / _BLUEPRINT_ID / _PROVIDER_ID / _VARIANT_ID."""
    base, h, get = _printify(cfg)
    for shop in get("/shops.json"):
        print(f"PRINTIFY_SHOP_ID={shop['id']}   ({shop.get('title')}, {shop.get('sales_channel')})")
    print("\nPRINTIFY_BLUEPRINT_ID=400   Kiss-Cut Stickers, 2x2 sizes by provider:")
    for pid, ptitle, vid, vtitle in _kiss_cut_choices(get):
        print(f"   PRINTIFY_PROVIDER_ID={pid} ({ptitle})   PRINTIFY_VARIANT_ID={vid} ({vtitle})")
    print("\nPick the provider that also makes your 15x3.75 bumper sticker (same provider = one shipment).")


def printify_test(cfg, shop_id, keep=False):
    """Publish a throwaway 'TEST - delete me' sticker to one shop and report whether it went live."""
    import requests, base64, glob
    base, h, get = _printify(cfg)
    choices = _kiss_cut_choices(get)
    if not choices:
        raise SystemExit("No 2x2 kiss-cut size found; send Claude the lines above.")
    pid, ptitle, vid, vtitle = next((c for c in choices if str(c[0]) == str(cfg.printify_provider_id)), choices[0])
    print(f"Using provider {pid} ({ptitle}), size {vtitle}")
    art = os.path.join(os.path.dirname(__file__), "..", "sample_badges.png")
    with open(art, "rb") as f:
        img = requests.post(f"{base}/uploads/images.json", headers=h, timeout=60,
                            json={"file_name": "test.png", "contents": base64.b64encode(f.read()).decode()}).json()
    prod = requests.post(f"{base}/shops/{shop_id}/products.json", headers=h, timeout=60, json={
        "title": "TEST - delete me", "description": "Badgebot connection test.", "blueprint_id": 400,
        "print_provider_id": pid, "variants": [{"id": vid, "price": 400, "is_enabled": True}],
        "print_areas": [{"variant_ids": [vid], "placeholders": [{"position": "front",
                         "images": [{"id": img["id"], "x": 0.5, "y": 0.5, "scale": 1, "angle": 0}]}]}]})
    print("Create product:", prod.status_code, prod.text[:200] if prod.status_code >= 300 else "ok")
    if prod.status_code >= 300:
        return
    product_id = prod.json()["id"]
    pub = requests.post(f"{base}/shops/{shop_id}/products/{product_id}/publish.json", headers=h, timeout=60,
                        json={"title": True, "description": True, "images": True, "variants": True, "tags": True,
                              "keyFeatures": True, "shipping_template": True})
    print("Publish:", pub.status_code, pub.text[:300] if pub.status_code >= 300 else "ok")
    for _ in range(12):
        time.sleep(10)
        d = get(f"/shops/{shop_id}/products/{product_id}.json")
        ext = d.get("external") or {}
        print("  status:", "visible" if d.get("visible") else "not visible yet",
              "| store link:", ext.get("handle") or "(none yet)")
        if ext.get("handle"):
            break
    if not keep:
        r = requests.delete(f"{base}/shops/{shop_id}/products/{product_id}.json", headers=h, timeout=30)
        print("Test product deleted:", r.status_code < 300)


def watch(p, cfg, every_min):
    from .sources import fetch_wsdot_bluesky
    history = os.environ.get("PUBLISH_HISTORY") == "1"   # set in Railway: keeps the history set on sale
    if history:
        _history_step(p, startup=True)
    last_buzz = 0.0
    while True:
        try:
            for run in p.process(fetch_live(cfg)):
                print(time.strftime("%H:%M"), run["key"], run["status"], run.get("title"), flush=True)
        except Exception as e:   # keep watching through WSDOT hiccups
            print(time.strftime("%H:%M"), "error:", e, flush=True)
        if time.time() - last_buzz >= cfg.buzz_every_min * 60:
            last_buzz = time.time()
            try:
                for run in p.process_buzz(fetch_wsdot_bluesky(cfg)):
                    print(time.strftime("%H:%M"), "buzz", run["key"], run["status"], run.get("title"), flush=True)
            except Exception as e:
                print(time.strftime("%H:%M"), "buzz error:", e, flush=True)
        try:
            p.tick()
        except Exception as e:
            print(time.strftime("%H:%M"), "tick error:", e, flush=True)
        if history:
            _history_step(p)
        time.sleep(every_min * 60)


def _history_step(p, startup=False):
    """Art swaps for badges already on sale, new history badges, then (once) the V2 list draft."""
    steps = [("history art", p.refresh_history)] + ([("history", p.publish_history)] if startup else [])
    for name, step in steps:
        try:
            for run in step():
                print(time.strftime("%H:%M"), name, run["key"], run["status"], run["title"], flush=True)
        except Exception as e:
            print(time.strftime("%H:%M"), f"{name} error:", e, flush=True)
    try:
        if p.announce_v2():
            print(time.strftime("%H:%M"), "V2 list email drafted in Mailchimp (not sent)", flush=True)
    except Exception as e:
        print(time.strftime("%H:%M"), "V2 list email error:", e, flush=True)


if __name__ == "__main__":
    main()
