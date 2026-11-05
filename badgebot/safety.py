"""Stage 3: safety gate with event categories.

Tiers
  BLOCK - never drafted, never emailed
  HOLD  - drafted and emailed, publishes ONLY when you press Approve
  PASS  - published right away; the email carries an Unpublish link

Event categories (checked in this order; the first that applies decides)
  harm         deaths or serious injuries in the official text            -> BLOCK
  conflict     riots, clashes, arrests, looting, property damage           -> BLOCK
  officeholder politician, candidate, dignitary, motorcade, summit, visit  -> BLOCK
  gathering    march, rally, strike, vigil, parade, public celebration     -> HOLD, and
               even when approved it publishes no earlier than the next morning, after
               the event is over. The title may name only the act ("MARCH ON I-5"),
               never the cause, a slogan, a group or a person.
  incident     everything else: spills, weather, bridges, closures         -> PASS unless
               something below holds it (injury, celebrity, brand, rumour of harm)
"""
import re
from dataclasses import dataclass, field

from .hook import SINGULAR, WEATHER_TITLES
from .vocab import (BRANDS, CELEBRITIES, CONFLICT, FATAL, GATHERING, GATHERING_TITLE_WORDS,
                    GENERIC, HOOK_WORDS, INJURY, OFFICEHOLDER, POLITICAL, POLITICIANS,
                    PROFANITY, tokens)

BLOCK, HOLD, PASS = "BLOCK", "HOLD", "PASS"
INCIDENT, GATHERING_CAT = "incident", "gathering"
RELEASE_NOW, RELEASE_NEXT_MORNING = "now", "next_morning"
ALLOWED_CHARS = re.compile(r"^[A-Z0-9 \-&*'.]+$")

TITLE_VOCAB = set(SINGULAR.values()) | {t for v in WEATHER_TITLES.values() for t in tokens(v)} \
    | {"gridlock", "jam"}


@dataclass
class Verdict:
    tier: str
    reasons: list = field(default_factory=list)
    category: str = INCIDENT
    release: str = RELEASE_NOW


def wrap_title(title, line_max):
    """Kept for older callers; the oval patch uses one arched line."""
    title = " ".join(title.split())
    if len(title) <= line_max:
        return [title]
    words = title.split()
    best = None
    for i in range(1, len(words)):
        a, b = " ".join(words[:i]), " ".join(words[i:])
        if len(a) <= line_max and len(b) <= line_max:
            if best is None or max(len(a), len(b)) < max(map(len, best)):
                best = [a, b]
    return best


def _hit(rx, text):
    m = rx.search(text)
    return m.group(0) if m else None


def check(cand, hook, cfg):
    block, hold = [], []
    official = cand.official_text or ""
    social = " ".join(cand.social or [])
    category, release = INCIDENT, RELEASE_NOW

    # 1. What kind of event is this?
    if _hit(FATAL, official):
        block.append(f"official text reports death or serious harm: '{_hit(FATAL, official)}'")
    if _hit(CONFLICT, official):
        block.append(f"conflict event: '{_hit(CONFLICT, official)}'")
    if _hit(OFFICEHOLDER, official) or _hit(POLITICIANS, official):
        block.append(f"officeholder or dignitary event: '{_hit(OFFICEHOLDER, official) or _hit(POLITICIANS, official)}'")
    if _hit(GATHERING, official):
        category, release = GATHERING_CAT, RELEASE_NEXT_MORNING
        hold.append(f"civic gathering ('{_hit(GATHERING, official)}'): needs your OK, "
                    "and publishes no earlier than the next morning")

    # 2. Things that hold an otherwise-safe badge for a person's judgement
    if not _hit(FATAL, official) and _hit(FATAL, social):
        hold.append(f"unconfirmed report of serious harm in social posts: '{_hit(FATAL, social)}'")
    if _hit(INJURY, official):
        hold.append(f"injury mentioned: '{_hit(INJURY, official)}'")
    if _hit(CELEBRITIES, official):
        hold.append(f"celebrity event: '{_hit(CELEBRITIES, official)}'")

    if hook is None:
        block.append("no sticker-worthy hook (nameable, drawable angle) found")
        return Verdict(BLOCK, block + hold, category, release)

    title = hook.title.strip()
    official_toks = set(tokens(official))

    # 3. Title content
    for rx, why in ((POLITICAL, "political"), (PROFANITY, "profanity"), (FATAL, "harm word"),
                    (CONFLICT, "conflict"), (OFFICEHOLDER, "officeholder"), (POLITICIANS, "politician")):
        if _hit(rx, title):
            block.append(f"title contains {why} term '{_hit(rx, title)}'")
    celeb = _hit(CELEBRITIES, title)
    if celeb:
        if celeb.lower() in official_toks or celeb.lower() in official.lower():
            hold.append(f"title names a celebrity '{celeb}' (present in official text)")
        else:
            block.append(f"title names a celebrity '{celeb}' not in official text (possible injection)")
    if _hit(BRANDS, title):
        hold.append(f"title names a brand '{_hit(BRANDS, title)}' (trademark check)")

    # 4. Provenance. Incidents: words from official text or the controlled vocabulary.
    #    Gatherings: the controlled vocabulary ONLY, so a cause or slogan in the alert
    #    ("climate march") can never reach the badge.
    if category == GATHERING_CAT:
        allowed = GENERIC | GATHERING_TITLE_WORDS | TITLE_VOCAB
        why = "gathering titles may name only the act, not the cause"
    else:
        allowed = official_toks | GENERIC | HOOK_WORDS | TITLE_VOCAB
        why = "words not found in official source"
    ungrounded = [t for t in tokens(title) if t not in allowed and not t.isdigit()]
    if ungrounded:
        block.append(f"{why}: {', '.join(ungrounded)}")

    # 5. Printability (whether it physically fits the arc is measured in badge.py)
    if not ALLOWED_CHARS.match(title):
        block.append("title has characters outside A-Z 0-9 - & * ' .")
    if len(title) > cfg.title_max_chars:
        block.append(f"title is {len(title)} chars, limit {cfg.title_max_chars}")

    if block:
        return Verdict(BLOCK, block + hold, category, release)
    if hold:
        return Verdict(HOLD, hold, category, release)
    return Verdict(PASS, [], category, release)
