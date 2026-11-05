"""Command line.

  python -m badgebot replay replays/blueberry_405_2018.json   one recorded event through the pipeline
  python -m badgebot watch --every 2                          live: poll WSDOT every 2 min + tick
  python -m badgebot serve --port 8080                        web server for the email links
  python -m badgebot tick                                     expire held badges nobody approved
  python -m badgebot act <key> approve|reject|unpublish       act from the command line
  python -m badgebot status                                   list runs and their state
  python -m badgebot printify-setup                           find your shop, kiss-cut and 2x2 IDs
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
    elif a.cmd == "printify-setup":
        printify_setup(cfg)
    elif a.cmd == "serve":
        if a.with_watch:
            threading.Thread(target=watch, args=(p, cfg, 2.0), daemon=True).start()
        from .server import make_app
        make_app(p, cfg).run(host="0.0.0.0", port=a.port, threaded=True)


def printify_setup(cfg):
    """Prints the numbers for PRINTIFY_SHOP_ID / _BLUEPRINT_ID / _PROVIDER_ID / _VARIANT_ID."""
    import requests
    if not cfg.printify_token:
        raise SystemExit("Set PRINTIFY_TOKEN first.")
    base, h = "https://api.printify.com/v1", {"Authorization": f"Bearer {cfg.printify_token}",
                                              "User-Agent": "badgebot/1.0"}
    get = lambda path: requests.get(base + path, headers=h, timeout=30).json()
    for shop in get("/shops.json"):
        print(f"PRINTIFY_SHOP_ID={shop['id']}   ({shop.get('title')}, {shop.get('sales_channel')})")
    for bp in get("/catalog/blueprints.json"):
        if "kiss" in bp["title"].lower() and "sticker" in bp["title"].lower():
            print(f"\nPRINTIFY_BLUEPRINT_ID={bp['id']}   {bp['title']}")
            for pp in get(f"/catalog/blueprints/{bp['id']}/print_providers.json"):
                sizes = [v for v in get(f"/catalog/blueprints/{bp['id']}/print_providers/{pp['id']}/variants.json")
                         .get("variants", []) if v["title"].replace(" ", "").startswith('2"x2"')]
                for v in sizes:
                    print(f"   PRINTIFY_PROVIDER_ID={pp['id']} ({pp['title']})   PRINTIFY_VARIANT_ID={v['id']} ({v['title']})")
    print("\nPick the provider that also makes your 15x3.75 bumper sticker (same provider = one shipment).")


def watch(p, cfg, every_min):
    from .sources import fetch_wsdot_bluesky
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
        time.sleep(every_min * 60)


if __name__ == "__main__":
    main()
