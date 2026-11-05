"""Public data sources. Live mode calls WSDOT; replay mode reads a recorded snapshot.

WSDOT Traveler Information API (free access code: https://wsdot.wa.gov/traffic/api/):
  TravelTimes:    .../TravelTimes/TravelTimesREST.svc/GetTravelTimesAsJson?AccessCode=...
  HighwayAlerts:  .../HighwayAlerts/HighwayAlertsREST.svc/GetAlertsAsJson?AccessCode=...

Social/news text is UNTRUSTED. It is used only as a hint that something is going on;
no word from it can reach a badge unless the same word is in official WSDOT text or
the controlled vocabulary (see safety.py).
"""
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone

import requests

WSDOT = "https://wsdot.wa.gov/Traffic/api"


@dataclass
class Snapshot:
    taken_at: datetime
    travel_times: list = field(default_factory=list)   # dicts with RouteName, CurrentTime, AverageTime
    alerts: list = field(default_factory=list)          # dicts with AlertID, HeadlineDescription, ...
    social: list = field(default_factory=list)          # untrusted strings


def _parse_wsdot_date(v):
    """WSDOT returns '/Date(1539010800000-0700)/'. Accept ISO strings too (replays)."""
    if v is None:
        return None
    if isinstance(v, str):
        m = re.match(r"/Date\((\d+)([+-]\d{4})?\)/", v)
        if m:
            return datetime.fromtimestamp(int(m.group(1)) / 1000, tz=timezone.utc)
        return datetime.fromisoformat(v.replace("Z", "+00:00"))
    return v


def fetch_live(cfg) -> Snapshot:
    if not cfg.wsdot_access_code:
        raise RuntimeError("Set WSDOT_ACCESS_CODE (free from https://wsdot.wa.gov/traffic/api/)")
    p = {"AccessCode": cfg.wsdot_access_code}
    tt = requests.get(f"{WSDOT}/TravelTimes/TravelTimesREST.svc/GetTravelTimesAsJson", params=p, timeout=20)
    al = requests.get(f"{WSDOT}/HighwayAlerts/HighwayAlertsREST.svc/GetAlertsAsJson", params=p, timeout=20)
    tt.raise_for_status(); al.raise_for_status()
    return Snapshot(taken_at=datetime.now(timezone.utc), travel_times=tt.json(), alerts=al.json())


def load_replay(path) -> Snapshot:
    with open(path, encoding="utf-8") as f:
        d = json.load(f)
    return Snapshot(
        taken_at=_parse_wsdot_date(d["taken_at"]),
        travel_times=d.get("travel_times", []),
        alerts=d.get("alerts", []),
        social=d.get("social", []),
    )


BSKY_PUBLIC = "https://public.api.bsky.app/xrpc"


def fetch_wsdot_bluesky(cfg, http=None, limit=100):
    """WSDOT's recent Bluesky posts with their like/repost/reply counts (public, no login)."""
    http = http or requests
    r = http.get(f"{BSKY_PUBLIC}/app.bsky.feed.getAuthorFeed", timeout=20,
                 params={"actor": cfg.wsdot_bluesky, "limit": limit, "filter": "posts_no_replies"})
    r.raise_for_status()
    out = []
    for item in r.json().get("feed", []):
        if item.get("reason"):   # a repost of someone else's post
            continue
        post = item["post"]
        rkey = post["uri"].rsplit("/", 1)[-1]
        out.append({"uri": post["uri"], "text": post["record"].get("text", ""),
                    "created": post["record"].get("createdAt"),
                    "url": f"https://bsky.app/profile/{cfg.wsdot_bluesky}/post/{rkey}",
                    "likes": post.get("likeCount", 0), "reposts": post.get("repostCount", 0),
                    "replies": post.get("replyCount", 0)})
    return out

