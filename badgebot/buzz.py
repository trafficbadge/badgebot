"""Rule #4: a WSDOT post that people are reacting to far more than usual is probably an event
worth remembering. It never publishes anything: it drafts a badge (or, if no title can be made
safely, just tells you about the post) and asks for your Approve.

WSDOT's own account is an official source, so its words count as official text for the
safety gate. Replies and quotes from other people are never read.
"""
import hashlib
import re
from dataclasses import dataclass
from datetime import datetime, timedelta

from .detect import Candidate
from .vocab import find_hook_words

ROAD = re.compile(r"\b(I-5|I-405|I-90|SR[ -]?520|SR[ -]?99)\b", re.I)


def score(post):
    return post["likes"] + 2 * post["reposts"] + post["replies"]


def _when(post):
    return datetime.fromisoformat(post["created"].replace("Z", "+00:00"))


def buzzing(posts, cfg, now):
    """Posts over the attention bar, recent enough to still matter."""
    return [p for p in posts
            if score(p) >= cfg.buzz_min_score and now - _when(p) <= timedelta(hours=cfg.buzz_max_age_h)]


def to_candidate(post):
    text = re.sub(r"\s+", " ", post["text"]).strip()
    m = ROAD.search(text)
    road = m.group(1).upper().replace("SR-", "SR ").replace("SR520", "SR 520").replace("SR99", "SR 99") if m else None
    return Candidate(
        key="bz" + hashlib.sha1(post["uri"].encode()).hexdigest()[:8], reason="buzz", road=road,
        max_delay_min=0, official_text=text, started_at=_when(post),
        hook_words=find_hook_words(text))


def plain_title(cand):
    """For a buzzing post with no quirky hook: the road plus a word WSDOT itself used."""
    from .hook import road_label
    road = road_label(cand.road)
    if not road:
        return None
    text = cand.official_text.lower()
    if re.search(r"\bclos(e|ed|es|ure|ures|ing)\b", text):
        return f"{road} CLOSURE"
    return None
