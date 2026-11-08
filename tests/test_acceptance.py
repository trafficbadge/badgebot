"""Acceptance tests: one or more per line of the spec. Run: python -m pytest -q"""
import csv
import json
import os
import time
from datetime import datetime, timedelta, timezone

import pytest

from badgebot.config import Config
from badgebot.detect import detect
from badgebot.hook import Hook
from badgebot.icons import LIBRARY, sanitize
from badgebot.pipeline import Pipeline
from badgebot.safety import check
from badgebot.sources import load_replay

HERE = os.path.dirname(__file__)
R = lambda name: load_replay(os.path.join(HERE, "..", "replays", f"{name}.json"))


class Clock:
    def __init__(self, t):
        self.t = t

    def __call__(self):
        return self.t

    def advance(self, minutes):
        self.t += timedelta(minutes=minutes)


def make(tmp_path, snap, lag_min=2, proposer=None, **over):
    cfg = Config(data_dir=str(tmp_path), anthropic_api_key=None, smtp_host=None, **over)
    clock = Clock(snap.taken_at + timedelta(minutes=lag_min))   # polling lag before we see it
    return cfg, clock, Pipeline(cfg, clock=clock, proposer=proposer)


def outbox(cfg):
    p = os.path.join(cfg.data_dir, "outbox.jsonl")
    return [json.loads(l) for l in open(p)] if os.path.exists(p) else []


def published(cfg):
    p = os.path.join(cfg.data_dir, "published.csv")
    return list(csv.DictReader(open(p))) if os.path.exists(p) else []


def hijack(title):
    return lambda cand, year, base: Hook(title, year, "x", "cone", "hijacked")


# ---- 1. Detection --------------------------------------------------------------------------
def test_blueberry_detected_and_drafted_fast(tmp_path):
    snap = R("blueberry_405_2018")
    cfg, clock, p = make(tmp_path, snap)
    t = time.time()
    [run] = p.process(snap)
    compute_s = time.time() - t
    assert run["detect_reason"] == "delay+hook"
    assert run["status"] == "published"
    assert compute_s < 60, f"pipeline compute took {compute_s:.1f}s"
    assert run["seconds_data_to_live"] <= 5 * 60   # data seen -> live (incl. polling lag)


def test_delay_threshold_edges():
    cfg = Config(anthropic_api_key=None)
    snap = R("near_delay_119")
    assert detect(snap, cfg) == []                         # 119 min, medium-priority hook: nothing
    snap.travel_times[0]["CurrentTime"] += 1                # exactly 120 min over average
    assert len(detect(snap, cfg)) == 1


def test_same_event_makes_one_badge(tmp_path):
    snap = R("blueberry_405_2018")
    cfg, clock, p = make(tmp_path, snap)
    p.process(snap); clock.advance(2); p.process(snap)
    assert len(p.all_runs()) == 1 and len(outbox(cfg)) == 1


# ---- 2. Hook and title ---------------------------------------------------------------------
def test_blueberry_title(tmp_path):
    snap = R("blueberry_405_2018")
    cfg, clock, p = make(tmp_path, snap)
    [run] = p.process(snap)
    assert run["title"] == "BLUEBERRY TRUCK ON 405" and run["year"] == 2018
    assert len(run["title"]) <= cfg.title_max_chars


def test_snow_title(tmp_path):
    snap = R("snowpocalypse_2019")
    cfg, clock, p = make(tmp_path, snap)
    [run] = p.process(snap)
    assert run["title"] == "SNOWPOCALYPSE" and run["status"] == "published"


def test_delay_without_hook_makes_no_badge(tmp_path):
    snap = R("near_delay_no_hook")
    cfg, clock, p = make(tmp_path, snap)
    [run] = p.process(snap)
    assert run["status"] == "blocked" and "no sticker-worthy hook" in run["reasons"][0]
    assert outbox(cfg) == []


# ---- 3. Safety -----------------------------------------------------------------------------
def test_fatal_crash_never_drafted(tmp_path):
    snap = R("fatal_crash")
    cfg, clock, p = make(tmp_path, snap)
    [run] = p.process(snap)
    assert run["status"] == "blocked"
    assert not os.path.exists(os.path.join(p.runs_dir, run["key"], "preview.png"))
    assert outbox(cfg) == []


def test_social_injection_never_reaches_title(tmp_path):
    snap = R("injection_obama")
    cfg, clock, p = make(tmp_path, snap)
    [run] = p.process(snap)
    assert run["title"] == "LOG TRUCK ON 520"
    assert "OBAMA" not in json.dumps(outbox(cfg)).upper()
    assert outbox(cfg)[0]["subject"].startswith("Published: LOG TRUCK ON 520")


@pytest.mark.parametrize("title", ["I SURVIVED THE OBAMA PRESIDENCY", "OBAMA ON 520",
                                   "MAGA TRUCK ON 520", "LOG TRUCK ON 520 LOL"])
def test_hijacked_proposer_is_blocked(tmp_path, title):
    snap = R("injection_obama")
    cfg, clock, p = make(tmp_path, snap, proposer=hijack(title))
    [run] = p.process(snap)
    assert run["status"] == "blocked", run["reasons"]
    assert outbox(cfg) == []


def test_title_length_near_miss():
    cfg = Config(anthropic_api_key=None)
    [cand] = detect(R("blueberry_405_2018"), cfg)
    ok = check(cand, Hook("BLUEBERRY TRUCK ON 405", 2018, "", "", "t"), cfg)        # 22 chars
    bad = check(cand, Hook("BLUEBERRY SEMI ON I-405", 2018, "", "", "t"), cfg)      # 23 chars
    assert ok.tier == "PASS"
    assert bad.tier == "BLOCK" and any("23 chars" in r for r in bad.reasons)


def test_minor_injury_is_held_not_auto_published(tmp_path):
    snap = R("near_minor_injury")
    cfg, clock, p = make(tmp_path, snap)
    [run] = p.process(snap)
    assert run["status"] == "pending_hold"
    mail = outbox(cfg)[0]
    assert mail["subject"].startswith("Needs your OK") and "NOT published" in mail["text"]
    clock.advance(60 * 24); p.tick()
    assert p.load(run["key"])["status"] == "pending_hold" and published(cfg) == []
    ok, msg = p.act(run["key"], "reject", run["token"])
    assert ok and p.load(run["key"])["status"] == "rejected" and published(cfg) == []


def test_held_draft_expires(tmp_path):
    snap = R("near_minor_injury")
    cfg, clock, p = make(tmp_path, snap)
    [run] = p.process(snap)
    clock.advance(cfg.hold_expiry_min); p.tick()
    assert p.load(run["key"])["status"] == "expired" and published(cfg) == []


def test_officeholder_visit_is_blocked(tmp_path):
    snap = R("hillary_motorcade")
    cfg, clock, p = make(tmp_path, snap)
    [run] = p.process(snap)
    assert run["status"] == "blocked" and any("officeholder" in r for r in run["reasons"])
    assert outbox(cfg) == []


def test_politician_names_blocked_even_if_official(tmp_path):
    cfg = Config(anthropic_api_key=None)
    [cand] = detect(R("hillary_motorcade"), cfg)
    assert check(cand, Hook("HILLARY ON I-5", 2016, "", "", "t"), cfg).tier == "BLOCK"
    assert check(cand, Hook("OBAMA ON I-5", 2016, "", "", "t"), cfg).tier == "BLOCK"


# ---- 3b. Gatherings: celebrate the people, never the cause; release the next morning --------
def test_peaceful_march_is_held_and_titled_by_the_act(tmp_path):
    snap = R("peaceful_march")
    cfg, clock, p = make(tmp_path, snap)
    [run] = p.process(snap)
    assert run["category"] == "gathering" and run["status"] == "pending_hold"
    assert run["title"] == "MARCH ON I-5"                       # not "CLIMATE MARCH"
    assert "CLIMATE" not in json.dumps(outbox(cfg)).upper().split("OFFICIAL TEXT")[0]
    assert "publishes no earlier than" in outbox(cfg)[0]["text"]


def test_approved_march_waits_for_next_morning(tmp_path):
    from datetime import datetime
    from badgebot.pipeline import SEATTLE
    snap = R("peaceful_march")          # 11:30am Seattle time
    cfg, clock, p = make(tmp_path, snap)
    [run] = p.process(snap)
    ok, msg = p.act(run["key"], "approve", run["token"])
    assert ok and msg.startswith("Approved.") and p.load(run["key"])["status"] == "approved_waiting"
    assert published(cfg) == []
    release = datetime.fromisoformat(p.load(run["key"])["not_before"]).astimezone(SEATTLE)
    assert release.hour == 9 and release.date() > snap.taken_at.astimezone(SEATTLE).date()
    clock.t = datetime.fromisoformat(run["not_before"]) - timedelta(minutes=1); p.tick()
    assert published(cfg) == []
    clock.advance(1); p.tick()
    assert p.load(run["key"])["status"] == "published" and len(published(cfg)) == 1


def test_approved_march_can_still_be_cancelled(tmp_path):
    snap = R("peaceful_march")
    cfg, clock, p = make(tmp_path, snap)
    [run] = p.process(snap)
    p.act(run["key"], "approve", run["token"])
    ok, _ = p.act(run["key"], "reject", run["token"])
    clock.advance(60 * 30); p.tick()
    assert ok and p.load(run["key"])["status"] == "rejected" and published(cfg) == []


def test_march_that_turns_violent_is_blocked(tmp_path):
    snap = R("march_turns_violent")
    cfg, clock, p = make(tmp_path, snap)
    [run] = p.process(snap)
    assert run["status"] == "blocked" and any("conflict" in r for r in run["reasons"])
    assert outbox(cfg) == []


@pytest.mark.parametrize("title", ["CLIMATE MARCH ON I-5", "MARCH FOR CLIMATE", "THOUSANDS MARCH"])
def test_gathering_titles_never_name_the_cause(tmp_path, title):
    snap = R("peaceful_march")
    cfg, clock, p = make(tmp_path, snap, proposer=hijack(title))
    [run] = p.process(snap)
    if title == "THOUSANDS MARCH":
        assert run["status"] == "pending_hold"                   # neutral act words are fine
    else:
        assert run["status"] == "blocked" and any("only the act" in r for r in run["reasons"])


def test_death_rumor_in_social_is_held(tmp_path):
    snap = R("social_death_rumor")
    cfg, clock, p = make(tmp_path, snap)
    [run] = p.process(snap)
    assert run["status"] == "pending_hold"


# ---- 4. Badge template ---------------------------------------------------------------------
@pytest.mark.parametrize("replay", ["blueberry_405_2018", "snowpocalypse_2019", "peaceful_march",
                                    "injection_obama", "near_minor_injury"])
def test_patches_print_ready(tmp_path, replay):
    snap = R(replay)
    cfg, clock, p = make(tmp_path, snap)
    [run] = p.process(snap)
    c = run["badge_checks"]
    assert run["badge_failures"] == []
    assert c["shape"] == "patch_oval" and c["print_dpi"] == 300 and c["bleed_mm"] >= 3
    assert c["road_band_mm"] >= 3                      # cut tolerance: picture never near the edge
    assert c["contrast_text_vs_ring"] >= 4.5 and c["contrast_icon_vs_field"] >= cfg.min_icon_contrast
    assert c["title_cap_height_mm"] >= cfg.min_cap_height_mm
    assert c["title_width_units"] <= c["title_room_units"]   # title fits the arc, clear of the road dashes
    for f in run["badge_files"].values():
        assert os.path.getsize(f) > 0


def test_longest_allowed_title_still_fits(tmp_path):
    from badgebot.badge import make_badge
    from badgebot.hook import Hook
    from badgebot.icons import LIBRARY
    cfg = Config(data_dir=str(tmp_path), anthropic_api_key=None)
    r = make_badge(Hook("BLUEBERRY TRUCK ON 405", 2018, "", "", "t"), LIBRARY["blueberry_truck"], cfg, str(tmp_path / "b"))
    assert r.passed, r.failures
    assert r.checks["title_font_units"] < 22 or r.checks["title_squeeze"] < 1   # it had to shrink, and did
    with pytest.raises(ValueError):
        make_badge(Hook("WWWWWWWWWWWWWWWWWWWWWW", 2018, "", "", "t"), LIBRARY["cone"], cfg, str(tmp_path / "c"))


@pytest.mark.parametrize("bad", [
    '<svg><text>HI</text></svg>', '<svg><script>alert(1)</script></svg>',
    '<svg><circle r="5" fill="#FF0000"/></svg>', '<svg><image href="http://x"/></svg>',
    '<svg><rect width="5" fill="url(#g)"/></svg>'])
def test_icon_sanitizer_rejects(bad):
    with pytest.raises(Exception):
        sanitize(bad)


def test_icon_sanitizer_accepts_house_style():
    assert "circle" in sanitize('<svg viewBox="0 0 200 200"><circle cx="1" cy="1" r="5" fill="accent"/></svg>')
    for v in LIBRARY.values():
        sanitize(f'<svg viewBox="0 0 200 200">{v}</svg>')   # our own icons obey the rules too


# ---- 5. Email: publish-then-undo for safe badges, approve for held ones ------------------
def test_safe_badge_publishes_and_unpublish_works_later(tmp_path):
    snap = R("blueberry_405_2018")
    cfg, clock, p = make(tmp_path, snap)
    [run] = p.process(snap)
    mail = outbox(cfg)[0]
    assert mail["subject"] == "Published: BLUEBERRY TRUCK ON 405 (2018)"
    assert f"/a/{run['key']}/unpublish?t={run['token']}" in mail["text"]
    assert [x["Handle"] for x in published(cfg)] == ["blueberry-truck-on-405-2018"]
    clock.advance(60 * 5)                      # five hours later, back on Wi-Fi
    ok, msg = p.act(run["key"], "unpublish", run["token"])
    assert ok and p.load(run["key"])["status"] == "unpublished"
    assert published(cfg) == []                # removed from the live store file
    ok, msg = p.act(run["key"], "unpublish", run["token"])
    assert not ok and "already unpublished" in msg


def test_email_has_image_and_buttons(tmp_path):
    import email, glob
    snap = R("near_minor_injury")
    cfg, clock, p = make(tmp_path, snap)
    [run] = p.process(snap)
    [eml] = glob.glob(os.path.join(cfg.data_dir, "outbox", "*.eml"))
    msg = email.message_from_bytes(open(eml, "rb").read())
    parts = [part.get_content_type() for part in msg.walk()]
    assert "image/png" in parts and "text/html" in parts and "text/plain" in parts
    html = next(part for part in msg.walk() if part.get_content_type() == "text/html").get_payload(decode=True).decode()
    assert ">Approve<" in html and ">Reject<" in html and "cid:" in html


def test_approve_publishes_held_badge(tmp_path):
    snap = R("near_minor_injury")
    cfg, clock, p = make(tmp_path, snap)
    [run] = p.process(snap)
    assert published(cfg) == []
    ok, msg = p.act(run["key"], "approve", run["token"])
    assert ok and p.load(run["key"])["published_how"] == "owner approved"
    assert len(published(cfg)) == 1


def test_wrong_or_missing_token_does_nothing(tmp_path):
    snap = R("near_minor_injury")
    cfg, clock, p = make(tmp_path, snap)
    [run] = p.process(snap)
    for t in ("", "guess", run["token"][:-1] + ("y" if run["token"].endswith("x") else "x")):
        ok, msg = p.act(run["key"], "approve", t)
        assert not ok and msg == "That link is not valid."
    assert p.load(run["key"])["status"] == "pending_hold"
    assert p.act("../etc", "approve", run["token"])[0] is False


def test_web_links_get_is_harmless_post_acts(tmp_path):
    from badgebot.server import make_app
    snap = R("blueberry_405_2018")
    cfg, clock, p = make(tmp_path, snap, public_base_url="https://example.test")
    [run] = p.process(snap)
    app = make_app(p, cfg).test_client()
    url = f"/a/{run['key']}/unpublish"
    r = app.get(url, query_string={"t": run["token"]})          # mail scanners do this
    assert r.status_code == 200 and b"Unpublish" in r.data
    assert p.load(run["key"])["status"] == "published"          # GET changed nothing
    assert app.get(url, query_string={"t": "nope"}).status_code == 404
    assert app.post(url, data={"t": "nope"}).status_code == 400
    assert app.get(f"/media/{run['key']}/preview.png").status_code == 404   # no token, no image
    r = app.post(url, data={"t": run["token"]})
    assert r.status_code == 200 and p.load(run["key"])["status"] == "unpublished"


# ---- 6. Listing + 7. Log -------------------------------------------------------------------
def test_listing_fields_and_run_log(tmp_path):
    snap = R("blueberry_405_2018")
    cfg, clock, p = make(tmp_path, snap)
    [run] = p.process(snap)
    L = run["listing"]
    assert L["Title"] and L["Body (HTML)"] and L["Variant Price"] == cfg.badge_price
    assert os.path.exists(L["Image Src"])
    log = [json.loads(l) for l in open(os.path.join(cfg.data_dir, "runs.log.jsonl"))]
    last = log[-1]
    for k in ("data_at", "emailed_at", "published_at", "cost_usd", "seconds_data_to_live"):
        assert last[k] is not None, k


# ---- 8. Going live: store page first, then posts; the list email waits; Unpublish undoes it all
def outlet_log(cfg):
    p = os.path.join(cfg.data_dir, "outbox", "outlets.jsonl")
    return [json.loads(l) for l in open(p)] if os.path.exists(p) else []


def test_safe_badge_goes_to_store_then_bluesky_threads_and_list(tmp_path):
    snap = R("blueberry_405_2018")
    cfg, clock, p = make(tmp_path, snap, store_url="https://seattletrafficbadges.com")
    [run] = p.process(snap)
    run = p.load(run["key"])
    assert run["status"] == "published"
    assert run["product_url"] == "https://seattletrafficbadges.com/products/blueberry-truck-on-405-2018"
    assert [x["platform"] for x in run["posts"]] == ["bluesky", "threads"]     # Instagram is off
    log = outlet_log(cfg)
    assert [(x["outlet"], x["method"]) for x in log][:3] == [("printify", "POST")] * 3
    bsky = next(x for x in log if x["outlet"] == "bluesky")["body"]
    assert bsky["text"] == ("I SURVIVED BLUEBERRY TRUCK ON 405 · 2018\n\nNew Seattle traffic badge for your "
                            "bumper: https://seattletrafficbadges.com/products/blueberry-truck-on-405-2018")
    assert not any(x["outlet"] == "instagram" for x in log)
    assert any(x["outlet"] == "mailchimp" and x["url"].endswith("/campaigns") for x in log)
    mail = outbox(cfg)[0]
    assert mail["subject"] == "Published: BLUEBERRY TRUCK ON 405 (2018)"
    assert "Store page: https://seattletrafficbadges.com/products/" in mail["text"]
    assert "Your mailing list gets the email at" in mail["text"]
    assert os.path.exists(os.path.join(cfg.data_dir, "runs", run["key"], "social.jpg"))


def test_list_email_waits_two_hours_then_sends_once(tmp_path):
    snap = R("blueberry_405_2018")
    cfg, clock, p = make(tmp_path, snap)
    [run] = p.process(snap)
    sends = lambda: [x for x in outlet_log(cfg) if x["url"].endswith("/actions/send")]
    clock.advance(cfg.list_delay_min - 1); p.tick()
    assert sends() == []
    clock.advance(1); p.tick(); clock.advance(10); p.tick()
    assert len(sends()) == 1 and p.load(run["key"])["list_email"]["sent_at"]


def test_unpublish_takes_down_store_posts_and_unsent_email(tmp_path):
    snap = R("blueberry_405_2018")
    cfg, clock, p = make(tmp_path, snap)
    [run] = p.process(snap)
    clock.advance(30)
    ok, msg = p.act(run["key"], "unpublish", run["token"])
    assert ok and "Still to do by hand" not in msg
    log = outlet_log(cfg)
    assert any(x["outlet"] == "printify" and x["method"] == "DELETE" for x in log)
    assert any(x["outlet"] == "bluesky" and "deleteRecord" in x["url"] for x in log)
    assert any(x["outlet"] == "threads" and x["method"] == "DELETE" for x in log)
    assert any(x["outlet"] == "mailchimp" and x["method"] == "DELETE" for x in log)
    clock.advance(cfg.list_delay_min); p.tick()
    assert not any(x["url"].endswith("/actions/send") for x in outlet_log(cfg))   # never sent


def test_held_badge_posts_nothing_until_approved(tmp_path):
    snap = R("near_minor_injury")
    cfg, clock, p = make(tmp_path, snap)
    [run] = p.process(snap)
    assert outlet_log(cfg) == []
    p.act(run["key"], "approve", run["token"])
    assert [x["platform"] for x in p.load(run["key"])["posts"]] == ["bluesky", "threads"]
    assert outbox(cfg)[-1]["subject"].startswith("Published:")
    assert "as you approved" in outbox(cfg)[-1]["text"]


@pytest.mark.parametrize("title,url", [
    ("OBAMA <script>", "https://seattletrafficbadges.com/products/x"),
    ("BLUEBERRY TRUCK", "https://evil.example/login?next=x"),
    ("BLUEBERRY TRUCK", "http://seattletrafficbadges.com/products/x"),
])
def test_post_text_refuses_anything_but_title_year_and_our_link(title, url):
    from badgebot.outlets import OutletError, post_text
    with pytest.raises(OutletError):
        post_text("bluesky", title, 2018, url)


def test_social_picture_is_public_only_while_live(tmp_path):
    from badgebot.server import make_app
    snap = R("blueberry_405_2018")
    cfg, clock, p = make(tmp_path, snap)
    [run] = p.process(snap)
    app = make_app(p, cfg).test_client()
    r = app.get(f"/s/{run['key']}.jpg")
    assert r.status_code == 200 and r.mimetype == "image/jpeg"
    p.act(run["key"], "unpublish", run["token"])
    assert app.get(f"/s/{run['key']}.jpg").status_code == 404


# ---- real-mode requests, against a fake internet ------------------------------------------
class FakeResp:
    def __init__(self, status=200, data=None, url=""):
        self.status_code, self._data, self.url = status, data if data is not None else {}, url
        self.content = json.dumps(self._data).encode()
        self.text = self.content.decode()

    def json(self):
        return self._data


class FakeNet:
    """Answers like Printify, Shopify, Bluesky, Threads and Mailchimp; records every call."""

    def __init__(self):
        self.calls, self.store_live, self.fail_publish_once = [], False, False

    def request(self, method, url, **kw):
        self.calls.append((method, url, kw))
        if "api.printify.com" in url:
            if url.endswith("/uploads/images.json"):
                return FakeResp(data={"id": "img1"})
            if url.endswith("/products.json"):
                return FakeResp(data={"id": "prod1"})
            if url.endswith("/publish.json"):
                if self.fail_publish_once:
                    self.fail_publish_once = False
                    return FakeResp(500, {"error": "busy"})
                return FakeResp(data={})
            if method == "GET":
                return FakeResp(data={"external": {"handle": "https://x.myshopify.com/products/blueberry-truck-on-405-2018"}})
            return FakeResp(data={})
        if "seattletrafficbadges.com/products/" in url:
            return FakeResp(200, url=url) if self.store_live else FakeResp(200, url="https://seattletrafficbadges.com/password")
        if "bsky.social" in url:
            if url.endswith("createSession"):
                return FakeResp(data={"accessJwt": "jwt", "did": "did:plc:abc"})
            if url.endswith("uploadBlob"):
                return FakeResp(data={"blob": {"$type": "blob", "size": 1}})
            if url.endswith("createRecord"):
                return FakeResp(data={"uri": "at://did:plc:abc/app.bsky.feed.post/3kxyz"})
            return FakeResp(data={})
        if url.endswith("/refresh_access_token"):
            return FakeResp(data={"access_token": "fresh-token", "expires_in": 5184000})
        if "graph.threads.net" in url:
            if url.endswith("/threads"):
                return FakeResp(data={"id": "c1"})
            if url.endswith("/threads_publish"):
                return FakeResp(data={"id": "t1"})
            if url.endswith("/c1"):
                return FakeResp(data={"status": "FINISHED"})
            return FakeResp(data={"permalink": "https://www.threads.net/@stb/post/t1"})
        if "api.mailchimp.com" in url:
            return FakeResp(data={"id": "camp1"})
        raise AssertionError(f"unexpected call {method} {url}")

    def get(self, url, **kw):
        return self.request("GET", url, **kw)

    def post(self, url, **kw):
        return self.request("POST", url, **kw)

    def delete(self, url, **kw):
        return self.request("DELETE", url, **kw)


REAL = dict(store_url="https://seattletrafficbadges.com", public_base_url="https://bot.example",
            printify_token="pt", printify_shop_id="9", printify_blueprint_id="400",
            printify_provider_id="1", printify_variant_id="45750",
            bluesky_handle="seattletrafficbadges.com", bluesky_app_password="app-pw",
            threads_user_id="777", threads_token="tt",
            mailchimp_api_key="abc-us21", mailchimp_list_id="L1", list_reply_to="hi@example.com")


def test_real_mode_waits_for_the_store_page_then_posts(tmp_path):
    snap = R("blueberry_405_2018")
    net = FakeNet()
    cfg = Config(data_dir=str(tmp_path), anthropic_api_key=None, smtp_host=None, **REAL)
    clock = Clock(snap.taken_at + timedelta(minutes=2))
    p = Pipeline(cfg, clock=clock, http=net, sleep=lambda s: None)
    net.fail_publish_once = True
    [run] = p.process(snap)
    assert p.load(run["key"])["status"] == "going_live"
    assert not any("bsky" in u or "threads" in u for _, u, _ in net.calls)    # nothing announced yet
    clock.advance(2); p.tick()                       # publish retried; store still password-protected
    creates = [u for m, u, _ in net.calls if u.endswith("/products.json")]
    assert len(creates) == 1                         # the retry did not make a second product
    assert p.load(run["key"])["status"] == "going_live"
    net.store_live = True
    clock.advance(2); p.tick()
    run = p.load(run["key"])
    assert run["status"] == "published"
    assert run["product_url"] == "https://seattletrafficbadges.com/products/blueberry-truck-on-405-2018"
    rec = next(kw["json"]["record"] for m, u, kw in net.calls if u.endswith("createRecord"))
    f = rec["facets"][0]["index"]
    assert rec["text"].encode()[f["byteStart"]:f["byteEnd"]].decode() == run["product_url"]
    thr = next(kw["params"] for m, u, kw in net.calls if u.endswith("/777/threads"))
    assert thr["image_url"] == f"https://bot.example/s/{run['key']}.jpg" and "#SeattleTraffic" in thr["text"]
    prod = next(kw["json"] for m, u, kw in net.calls if u.endswith("/products.json"))
    assert prod["variants"] == [{"id": 45750, "price": 400, "is_enabled": True}]
    assert prod["print_areas"][0]["placeholders"][0]["images"][0]["id"] == "img1"
    assert [x["url"] for x in run["posts"]] == ["https://bsky.app/profile/seattletrafficbadges.com/post/3kxyz",
                                                 "https://www.threads.net/@stb/post/t1"]
    assert run["list_email"]["id"] == "camp1" and "sent_at" not in run["list_email"]


def test_real_mode_stuck_store_emails_you_once_and_posts_nothing(tmp_path):
    snap = R("blueberry_405_2018")
    net = FakeNet()
    cfg = Config(data_dir=str(tmp_path), anthropic_api_key=None, smtp_host=None, **REAL)
    clock = Clock(snap.taken_at + timedelta(minutes=2))
    p = Pipeline(cfg, clock=clock, http=net, sleep=lambda s: None)
    [run] = p.process(snap)
    for _ in range(30):
        clock.advance(2); p.tick()
    subjects = [m["subject"] for m in outbox(cfg)]
    assert subjects == ["Not live yet: BLUEBERRY TRUCK ON 405 (2018)"]
    assert not any("bsky" in u for _, u, _ in net.calls)


def test_tokens_refresh_weekly_and_failures_email_once_a_day(tmp_path):
    snap = R("blueberry_405_2018")
    net = FakeNet()
    cfg = Config(data_dir=str(tmp_path), anthropic_api_key=None, smtp_host=None, threads_user_id="777",
                 threads_token="old")
    clock = Clock(snap.taken_at)
    p = Pipeline(cfg, clock=clock, http=net, sleep=lambda s: None)
    p.tick()
    assert p.tokens.get("threads") == "fresh-token"
    assert oct(os.stat(os.path.join(cfg.data_dir, "tokens.json")).st_mode & 0o777) == "0o600"
    refreshes = lambda: sum(u.endswith("refresh_access_token") for _, u, _ in net.calls)
    clock.advance(60 * 24); p.tick()
    assert refreshes() == 1                       # not again until a week has passed
    net.request = lambda m, u, **kw: FakeResp(400, {"error": "expired"})
    clock.t = datetime.now(timezone.utc) + timedelta(days=8)
    for _ in range(5):
        p.tick(); clock.advance(30)
    assert [m["subject"] for m in outbox(cfg)] == ["Social account needs attention"]


def test_email_failure_is_shown_not_swallowed(tmp_path, capsys):
    snap = R("blueberry_405_2018")
    cfg = Config(data_dir=str(tmp_path), anthropic_api_key=None, smtp_host="127.0.0.1", smtp_port="1",
                 smtp_user="u", smtp_password="pw", owner_email="o@example.com")
    p = Pipeline(cfg, clock=Clock(snap.taken_at + timedelta(minutes=2)))
    [run] = p.process(snap)
    run = p.load(run["key"])
    assert run["status"] == "published" and run.get("go_live_error") is None
    assert "Connection" in run["email_error"] or "refused" in run["email_error"].lower()
    assert "Email to you FAILED" in capsys.readouterr().out


def test_real_social_keys_stay_in_practice_until_the_store_is_real(tmp_path):
    snap = R("blueberry_405_2018")
    net = FakeNet()
    keys = {k: v for k, v in REAL.items() if not k.startswith("printify")}
    cfg = Config(data_dir=str(tmp_path), anthropic_api_key=None, smtp_host=None, **keys)
    p = Pipeline(cfg, clock=Clock(snap.taken_at + timedelta(minutes=2)), http=net, sleep=lambda s: None)
    [run] = p.process(snap)
    assert all(x.get("practice") for x in p.load(run["key"])["posts"])
    assert not any("bsky" in u or "threads" in u or "mailchimp" in u for _, u, _ in net.calls)


# ---- 9. Buzz: WSDOT posts people react to become drafts that wait for your OK ---------------
def bsky_post(text, likes=40, reposts=5, replies=3, hours_ago=2, now=None, n=1):
    created = (now - timedelta(hours=hours_ago)).isoformat().replace("+00:00", "Z")
    return {"uri": f"at://did:plc:wsdot/app.bsky.feed.post/{n}", "text": text, "created": created,
            "url": f"https://bsky.app/profile/traffic.wsdot.wa.gov/post/{n}",
            "likes": likes, "reposts": reposts, "replies": replies}


def buzz_pipeline(tmp_path):
    now = datetime(2026, 11, 2, 18, 0, tzinfo=timezone.utc)
    cfg = Config(data_dir=str(tmp_path), anthropic_api_key=None, smtp_host=None)
    return cfg, now, Pipeline(cfg, clock=Clock(now))


def test_buzzing_closure_post_becomes_a_held_draft(tmp_path):
    cfg, now, p = buzz_pipeline(tmp_path)
    post = bsky_post("IT'S A HALLOWEEN WEEKEND FULL CLOSURE OF NB I-5 IN SEATTLE. NB I-5 will close 11pm Fri.", now=now)
    [run] = p.process_buzz([post])
    assert run["status"] == "pending_hold" and run["title"] == "I-5 CLOSURE"
    mail = outbox(cfg)[0]
    assert mail["subject"] == "Needs your OK: I-5 CLOSURE (2026)"
    assert "unusual attention" in mail["text"] and post["url"] in mail["text"]
    assert p.process_buzz([post]) == []                       # one post, one draft
    assert outlet_log(cfg) == []                              # nothing went anywhere


def test_quiet_or_old_posts_are_ignored(tmp_path):
    cfg, now, p = buzz_pipeline(tmp_path)
    quiet = bsky_post("NB I-5 full closure tonight", likes=3, reposts=1, replies=0, now=now, n=1)
    old = bsky_post("NB I-5 full closure tonight", hours_ago=72, now=now, n=2)
    assert p.process_buzz([quiet, old]) == [] and outbox(cfg) == []


def test_buzz_never_bypasses_the_safety_gate(tmp_path):
    cfg, now, p = buzz_pipeline(tmp_path)
    [run] = p.process_buzz([bsky_post("Fatal collision closes NB I-5 near Mercer", now=now)])
    assert run["status"] == "blocked" and outbox(cfg) == []


def test_popular_post_with_no_safe_title_just_tells_you(tmp_path):
    cfg, now, p = buzz_pipeline(tmp_path)
    p.process_buzz([bsky_post("Today's Fall Equinox marks the start of astronomical fall!", likes=400, now=now)])
    [mail] = outbox(cfg)
    assert mail["subject"] == "Popular WSDOT post: worth a badge?" and "No badge was drafted" in mail["text"]


def test_drawbridge_openings_are_not_hooks():
    from badgebot.vocab import find_hook_words
    assert find_hook_words("On SR 99 at 1st Ave S Bridge all lanes will be closed due to boat traffic.") == []


# ---- 10. Railway: alerts through Resend; hooks only count on Seattle corridors -------------
def test_snow_on_a_mountain_highway_is_not_a_seattle_badge(tmp_path):
    snap = R("snowpocalypse_2019")
    for a in snap.alerts:
        a["StartRoadwayLocation"] = dict(a.get("StartRoadwayLocation") or {}, RoadName="020")
    snap.travel_times = []          # no Seattle jam either
    cfg, clock, p = make(tmp_path, snap)
    assert detect(snap, cfg) == []


def test_alert_email_goes_through_resend_with_linked_picture(tmp_path, monkeypatch):
    import badgebot.notify as notify
    sent = []
    monkeypatch.setattr(notify.requests, "post",
                        lambda url, **kw: sent.append((url, kw)) or FakeResp(200, {"id": "e1"}))
    snap = R("blueberry_405_2018")
    cfg = Config(data_dir=str(tmp_path), anthropic_api_key=None, smtp_host=None, resend_api_key="re_x",
                 owner_email="o@example.com", mail_from="info@badtraffic206.com",
                 public_base_url="https://bot.badtraffic206.com")
    p = Pipeline(cfg, clock=Clock(snap.taken_at + timedelta(minutes=2)))
    [run] = p.process(snap)
    [(url, kw)] = sent
    assert url == "https://api.resend.com/emails"
    assert kw["headers"]["Authorization"] == "Bearer re_x"
    body = kw["json"]
    assert body["to"] == ["o@example.com"] and body["subject"] == "Published: BLUEBERRY TRUCK ON 405 (2018)"
    assert f"https://bot.badtraffic206.com/media/{run['key']}/preview.png?t={run['token']}" in body["html"]
    assert f"https://bot.badtraffic206.com/a/{run['key']}/unpublish?t={run['token']}" in body["text"]


def test_home_page_says_running(tmp_path):
    from badgebot.server import make_app
    cfg = Config(data_dir=str(tmp_path))
    r = make_app(Pipeline(cfg), cfg).test_client().get("/")
    assert r.status_code == 200 and b"Badgebot is running" in r.data


def test_popup_store_links_are_used_as_given(tmp_path):
    from badgebot.outlets import post_text
    snap = R("blueberry_405_2018")
    net = FakeNet()
    popup = "https://badtraffic206.printify.me/product/34010437"
    orig = net.request
    def request(method, url, **kw):
        if "api.printify.com" in url and method == "GET" and url.endswith("prod1.json"):
            net.calls.append((method, url, kw))
            return FakeResp(data={"external": {"handle": popup}})
        if url == popup:
            net.calls.append((method, url, kw))
            return FakeResp(200, url=popup)
        return orig(method, url, **kw)
    net.request = request
    keys = dict(REAL, store_url=None)
    cfg = Config(data_dir=str(tmp_path), anthropic_api_key=None, smtp_host=None, **keys)
    p = Pipeline(cfg, clock=Clock(snap.taken_at + timedelta(minutes=2)), http=net, sleep=lambda s: None)
    [run] = p.process(snap)
    run = p.load(run["key"])
    assert run["status"] == "published" and run["product_url"] == popup
    assert popup in post_text("bluesky", run["title"], run["year"], popup)


# ---- 11. Limited edition of 100; year ranges for construction badges -----------------------
def test_limited_edition_counts_down_then_sells_out_but_stays_in_collection(tmp_path):
    from badgebot.server import make_app
    snap = R("blueberry_405_2018")
    cfg, clock, p = make(tmp_path, snap)
    [run] = p.process(snap)
    pid = p.load(run["key"])["printify"]["product_id"]
    sales = os.path.join(cfg.data_dir, "practice_sales.json")
    first = next(x for x in outlet_log(cfg) if x["url"].endswith("/products.json"))
    assert "Limited edition of 100.</b> 100 of 100 left" in first["body"]["description"]

    json.dump({pid: 37}, open(sales, "w")); clock.advance(15); p.tick()
    put = [x for x in outlet_log(cfg) if x["method"] == "PUT"][-1]
    assert "63 of 100 left" in put["body"]["description"]
    col = make_app(p, cfg).test_client().get("/collection.json").get_json()
    assert col[0]["left"] == 63 and col[0]["link"] and col[0]["status"] == "published"

    json.dump({pid: 101}, open(sales, "w")); clock.advance(15); p.tick()
    run = p.load(run["key"])
    assert run["status"] == "sold_out"
    assert any(x["method"] == "DELETE" and x["outlet"] == "printify" for x in outlet_log(cfg))
    assert outbox(cfg)[-1]["subject"] == "Sold out: BLUEBERRY TRUCK ON 405 (2018)"
    app = make_app(p, cfg).test_client()
    [item] = app.get("/collection.json").get_json()
    assert item["status"] == "sold_out" and item["left"] == 0 and item["link"] is None
    assert app.get(item["image"]).status_code == 200       # the picture stays for the stamped gallery


@pytest.mark.parametrize("year,ok", [("2021-2024", True), ("2021–2024", True), ("2018", True),
                                     ("2024-2021", False), ("20211-2024", False), ("2021-2024 VOTE", False)])
def test_post_text_accepts_year_ranges_only_in_order(year, ok):
    from badgebot.outlets import OutletError, post_text
    url = "https://badtraffic206.printify.me/product/1"
    if ok:
        assert post_text("bluesky", "MADISON MAYHEM", year, url)
    else:
        with pytest.raises(OutletError):
            post_text("bluesky", "MADISON MAYHEM", year, url)


def test_construction_badge_with_year_range_prints(tmp_path):
    from badgebot.badge import make_badge
    cfg = Config(data_dir=str(tmp_path))
    r = make_badge(Hook("MADISON MAYHEM", "2021-2024", "", "cone", "t"), LIBRARY["cone"], cfg, str(tmp_path / "m"))
    assert r.passed, r.failures
    assert "2021–2024" in open(r.files["svg"], encoding="utf-8").read()


# ---- 12. Nov 7 false alarms: titles must be backed by the text --------------------------------
def nov7_snapshot(text, category, mp, priority="High", road="005"):
    from badgebot.sources import Snapshot
    t = datetime(2026, 11, 8, 4, 22, tzinfo=timezone.utc)
    alert = {"AlertID": 991, "Region": "Northwest", "Priority": priority, "EventCategory": category,
             "HeadlineDescription": text, "ExtendedDescription": "",
             "StartRoadwayLocation": {"RoadName": road, "MilePost": mp, "Description": ""},
             "StartTime": "/Date(1794200000000-0800)/"}
    return Snapshot(taken_at=t, travel_times=[], alerts=[alert], social=[])


FISH_ALERT = ('Northbound and southbound I-5 will be reduced to one lane from 8 p.m. to 5 a.m. nightly Sunday, '
              'Nov. 8, through Tuesday morning, Nov. 10, north of the North Lake Samish exit (milepost 245-247) as '
              'work continues on <a href="https://wsdot.wa.gov/construction-planning/search-projects/'
              'i-5-tributaries-friday-lake-chuckanut-creeks-fish-passage">')


def test_nov7_fish_in_a_link_on_planned_work_near_bellingham_is_not_an_event(tmp_path):
    snap = nov7_snapshot(FISH_ALERT, "Construction", 245)
    cfg, clock, p = make(tmp_path, snap)
    assert detect(snap, cfg) == [] and p.process(snap) == []


def test_link_words_never_count_even_on_a_seattle_incident(tmp_path):
    snap = nov7_snapshot('Collision blocking the left lane. Details: <a href="https://x.example/fish-crab">', "Collision", 165)
    cfg, clock, p = make(tmp_path, snap)
    assert detect(snap, cfg) == []


def test_cargo_word_without_a_truck_or_spill_makes_no_truck_title(tmp_path):
    from badgebot.hook import rules_hook
    from badgebot.detect import Candidate
    c = Candidate(key="k", reason="hook", road="5", max_delay_min=0,
                  official_text="Downed trees blocking the right lane", hook_words=["trees"])
    h = rules_hook(c, 2026)
    assert h is None or "TRUCK" not in h.title
    c2 = Candidate(key="k", reason="hook", road="5", max_delay_min=0,
                   official_text="A semi lost its load of blueberries, blocking two lanes", hook_words=["blueberries"])
    assert rules_hook(c2, 2026).title == "BLUEBERRY TRUCK ON I-5"


def test_keyword_without_a_measured_jam_waits_for_your_ok(tmp_path):
    snap = nov7_snapshot("A semi overturned and spilled its load of crabs across all lanes", "Collision", 166, priority="Highest")
    cfg, clock, p = make(tmp_path, snap)
    [run] = p.process(snap)
    assert run["status"] == "pending_hold" and any("no traffic jam measured" in r for r in run["reasons"])


def test_nov7_tree_forecast_post_drafts_no_badge(tmp_path):
    cfg, now, p = buzz_pipeline(tmp_path)
    post = bsky_post("The National Weather Service says we could see lots of rain and gusty winds across our region "
                     "tonight. You might find downed trees and debris, darkened signals or power lines in the road. "
                     "Be prepared, stay alert and watch for road crews @nws.noaa.gov #wawx", likes=25, reposts=3, now=now)
    [run] = p.process_buzz([post])
    assert run["status"] == "blocked" and not run.get("title")
    assert outbox(cfg)[-1]["subject"] == "Popular WSDOT post: worth a badge?"
