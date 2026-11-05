"""Stage 1: decide whether anything in a snapshot is a candidate event."""
import hashlib
from dataclasses import dataclass, field

from .sources import _parse_wsdot_date
from .vocab import HOOK_WORDS, find_hook_words


@dataclass
class Candidate:
    key: str                     # stable id so one event makes one badge
    reason: str                  # "delay", "hook", or "delay+hook"
    road: str | None
    max_delay_min: int
    official_text: str           # all trusted WSDOT text about the event
    alerts: list = field(default_factory=list)
    routes: list = field(default_factory=list)
    social: list = field(default_factory=list)
    started_at: object = None
    hook_words: list = field(default_factory=list)


def _road_of(alert):
    loc = alert.get("StartRoadwayLocation") or {}
    rn = (loc.get("RoadName") or "").strip()
    return rn.lstrip("0") or None


def _alert_text(a):
    loc = a.get("StartRoadwayLocation") or {}
    parts = [a.get("EventCategory"), a.get("HeadlineDescription"), a.get("ExtendedDescription"),
             loc.get("Description"), loc.get("RoadName")]
    return " ".join(p for p in parts if p)


def detect(snapshot, cfg):
    """Return a list of Candidates (usually 0 or 1)."""
    slow = []
    for r in snapshot.travel_times:
        name = f'{r.get("RouteName") or ""} {r.get("Description") or ""}'
        if not any(c in name for c in cfg.corridors):
            continue
        cur, avg = r.get("CurrentTime"), r.get("AverageTime")
        if cur is None or avg is None or cur <= 0:
            continue  # WSDOT reports 0 when a sensor has no data
        delay = cur - avg
        if delay >= cfg.delay_threshold_min:
            slow.append({**r, "_delay": delay})

    regional = [a for a in snapshot.alerts
                if not cfg.regions or (a.get("Region") or "") in cfg.regions]

    # Alerts that carry a hook (blueberries, snow, motorcade...)
    hooked = []
    for a in regional:
        words = find_hook_words(_alert_text(a))
        if words:
            hooked.append((a, words))

    candidates = []
    if slow or any(a.get("Priority") in cfg.hook_only_priorities for a, _ in hooked):
        alerts = [a for a, _ in hooked] or regional
        hook_words = sorted({w for _, ws in hooked for w in ws})
        reason = "+".join(x for x, on in (("delay", bool(slow)), ("hook", bool(hooked))) if on)
        road = next((_road_of(a) for a in alerts if _road_of(a)), None)
        if road is None and slow:
            road = slow[0].get("RouteName", "").split()[0]
        ids = sorted(str(a.get("AlertID")) for a in alerts) or sorted(r.get("RouteName", "") for r in slow)
        day = snapshot.taken_at.date().isoformat()
        key = hashlib.sha1(f"{day}|{'|'.join(ids)}".encode()).hexdigest()[:10]
        starts = [_parse_wsdot_date(a.get("StartTime")) for a in alerts if a.get("StartTime")]
        candidates.append(Candidate(
            key=key, reason=reason, road=road,
            max_delay_min=int(max((r["_delay"] for r in slow), default=0)),
            official_text=" ".join(_alert_text(a) for a in alerts),
            alerts=alerts, routes=slow, social=list(snapshot.social),
            started_at=min(starts) if starts else snapshot.taken_at,
            hook_words=hook_words,
        ))
    return candidates
