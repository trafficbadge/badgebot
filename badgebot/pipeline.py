"""The whole flow: snapshot -> detect -> hook -> safety -> badge -> listing -> email -> decide.

States of a run:
  blocked       safety said BLOCK; logged, nothing drafted, nothing emailed
  going_live    Printify is making the sticker and publishing it to Shopify; nothing is
                announced until the store page actually loads (checked again on every tick)
  published     the store page is live, posts are up, the list email is drafted and goes
                out list_delay_min later. PASS-tier badges get here on their own and the
                email carries an Unpublish link (the veto became an undo).
  pending_hold  HOLD tier: emailed with Approve / Reject links; never publishes on its own
  approved_waiting  approved, but its category's release time has not come yet
                (gatherings: no earlier than 9am the morning after); publishes on tick
  sold_out      the limited edition sold out: off the store, but still shown (stamped) in the
                collection feed the website reads
  unpublished   owner pressed Unpublish
  rejected      owner pressed Reject on a held badge
  expired       held badge never approved within hold_expiry_min
"""
import csv
import html
import json
import os
import secrets
import time
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo

from . import badge as badge_mod
from .detect import detect
from .hook import Hook, propose, road_label
from .icons import get_icon
from .listing import SHOPIFY_COLUMNS, make_listing
from .notify import Mailer
from .outlets import Mailchimp, Printify, Tokens, social_image, social_outlets
from .safety import BLOCK, HOLD, RELEASE_NEXT_MORNING, check

SEATTLE = ZoneInfo("America/Los_Angeles")
ACTIONS = {"published": ("unpublish",), "going_live": ("unpublish",), "pending_hold": ("approve", "reject"),
           "approved_waiting": ("reject",)}
RELEASE_HOUR = 9   # local Seattle time for "next morning" releases


def next_morning(t):
    """9am Seattle time on the calendar day after t."""
    local = t.astimezone(SEATTLE)
    day = (local + timedelta(days=1)).date()
    return datetime(day.year, day.month, day.day, RELEASE_HOUR, tzinfo=SEATTLE).astimezone(timezone.utc)


def fmt_local(iso):
    t = datetime.fromisoformat(iso).astimezone(SEATTLE)   # no %-d: Windows doesn't support it
    return f"{t:%a %b} {t.day}, {t.hour % 12 or 12}:{t:%M}{'am' if t.hour < 12 else 'pm'}"


def utcnow():
    return datetime.now(timezone.utc)


class Pipeline:
    def __init__(self, cfg, clock=utcnow, proposer=None, http=None, sleep=time.sleep):
        self.cfg, self.clock, self.proposer = cfg, clock, proposer
        self.mailer = Mailer(cfg)
        self.http = http
        self.printify = Printify(cfg, http)
        self.socials = social_outlets(cfg, http, sleep=sleep)
        self.mailchimp = Mailchimp(cfg, http)
        if self.printify.practice:   # no real store page yet: never announce a made-up link
            for outlet in self.socials + [self.mailchimp]:
                outlet.practice = True
        self.tokens = Tokens(cfg)
        self.runs_dir = os.path.join(cfg.data_dir, "runs")
        os.makedirs(self.runs_dir, exist_ok=True)

    # ---------- persistence ----------
    def _path(self, key):
        return os.path.join(self.runs_dir, key, "run.json")

    def load(self, key):
        p = self._path(key)
        return json.load(open(p, encoding="utf-8")) if os.path.exists(p) else None

    def save(self, run):
        os.makedirs(os.path.dirname(self._path(run["key"])), exist_ok=True)
        with open(self._path(run["key"]), "w", encoding="utf-8") as f:
            json.dump(run, f, indent=2, default=str)
        with open(os.path.join(self.cfg.data_dir, "runs.log.jsonl"), "a", encoding="utf-8") as f:
            f.write(json.dumps({k: run.get(k) for k in (
                "key", "status", "tier", "title", "data_at", "drafted_at", "emailed_at",
                "decided_at", "published_at", "seconds_data_to_live", "cost_usd")}, default=str) + "\n")

    def all_runs(self):
        out = []
        for k in sorted(os.listdir(self.runs_dir)):
            r = self.load(k)
            if r:
                out.append(r)
        return out

    # ---------- main entry ----------
    def process(self, snapshot):
        """Handle one snapshot. Returns list of runs created (existing events are skipped)."""
        created = []
        for cand in detect(snapshot, self.cfg):
            if self.load(cand.key):
                continue   # same event already handled: one event, one badge
            created.append(self._handle(cand, snapshot))
        return created

    def publish_history(self, only=None):
        """Put the history set on sale, quietly (no posts, no list email), then send you one
        summary. Safe to run again: badges already made are skipped."""
        import hashlib
        from .history import HISTORY, LAUNCH
        from .icons import LIBRARY, SCENES
        only = only or LAUNCH
        from .listing import make_listing
        made = []
        for title, year, story, (kind, key) in HISTORY:
            if only and title not in only:
                continue
            rkey = "h" + hashlib.sha1(f"{title}|{year}".encode()).hexdigest()[:9]
            if self.load(rkey):
                continue
            art = SCENES[key]["art"] if kind == "scene" else LIBRARY[key]
            hook = Hook(title, year, "", key, "history")
            out_dir = os.path.join(self.runs_dir, rkey)
            now = self.clock()
            b = badge_mod.make_badge(hook, art, self.cfg, out_dir)
            run = {"key": rkey, "tier": "history", "reasons": ["history set"], "title": title, "year": year,
                   "category": "history", "release": "now", "quiet": True,
                   "data_at": now.isoformat(), "detected_at": now.isoformat(), "drafted_at": now.isoformat(),
                   "badge_checks": b.checks, "badge_files": b.files, "icon_source": f"{kind}:{key}",
                   "token": secrets.token_urlsafe(24)}
            if not b.passed:
                run.update(status="blocked", reasons=[f"badge failed print checks: {'; '.join(b.failures)}"])
                self.save(run)
                made.append(run)
                continue
            from types import SimpleNamespace
            run["listing"] = make_listing(hook, SimpleNamespace(road=None), self.cfg, b.files["preview"], now,
                                          story=story)
            run["listing"]["Tags"] = f"badge, {year}, history"
            self.save(run)
            self._publish(run, how="history set")
            made.append(self.load(rkey))
        if made:
            lines = [f"{r['title']} ({r['year']}): {r['status']}" + (f"  {r.get('product_url')}" if r.get("product_url") else "")
                     for r in made]
            self.mailer.send(f"History set: {sum(r['status'] == 'published' for r in made)} of {len(made)} badges live",
                             "\n".join(lines), "<p>" + "<br>".join(html.escape(x) for x in lines) + "</p>")
        return made

    def process_buzz(self, posts):
        """Rule #4: WSDOT posts getting unusual attention become held drafts for your OK."""
        from .buzz import buzzing, plain_title, score, to_candidate
        from .sources import Snapshot
        created = []
        for post in buzzing(posts, self.cfg, self.clock()):
            cand = to_candidate(post)
            if self.load(cand.key):
                continue
            why = f"WSDOT's post is getting unusual attention (score {score(post)}): {post['url']}"
            snap = Snapshot(taken_at=cand.started_at)
            run = self._handle(cand, snap, fallback_title=plain_title(cand), hold_reason=why)
            if run["status"] == "blocked" and not run.get("title"):
                # nothing safe to title it with: just tell you about it, once
                self.mailer.send(f"Popular WSDOT post: worth a badge?",
                                 f"{why}\n\n{cand.official_text}\n\nNo badge was drafted: there was no safe title to make from it. "
                                 f"If you want one, it can be made by hand.",
                                 f"<p>{html.escape(why)}</p><blockquote>{html.escape(cand.official_text)}</blockquote>"
                                 f"<p>No badge was drafted: there was no safe title to make from it. "
                                 f"If you want one, it can be made by hand.</p>")
            created.append(run)
        return created

    def _handle(self, cand, snapshot, fallback_title=None, hold_reason=None):
        t0 = self.clock()
        year = (cand.started_at or snapshot.taken_at).year
        hook = propose(cand, self.cfg, year, self.proposer)
        if hook is None and fallback_title:
            hook = Hook(fallback_title, year, "a road closed sign and traffic cones", "cone", "rules")
        verdict = check(cand, hook, self.cfg)
        if hold_reason and verdict.tier != BLOCK:   # e.g. buzz: never publishes without your OK
            verdict.tier = HOLD
            verdict.reasons = verdict.reasons + [hold_reason]
        run = {
            "key": cand.key, "tier": verdict.tier, "reasons": verdict.reasons,
            "detect_reason": cand.reason, "road": cand.road, "max_delay_min": cand.max_delay_min,
            "official_text": cand.official_text, "title": hook.title if hook else None,
            "year": year, "proposer": hook.proposer if hook else None,
            "data_at": snapshot.taken_at.isoformat(), "detected_at": t0.isoformat(),
            "cost_usd": round(hook.cost_usd if hook else 0.0, 4),
            "category": verdict.category, "release": verdict.release,
        }
        if verdict.tier == BLOCK:
            run["status"] = "blocked"
            self.save(run)
            return run

        out_dir = os.path.join(self.runs_dir, cand.key)
        icon, icon_src, icon_cost = get_icon(hook, self.cfg)
        try:
            b = badge_mod.make_badge(hook, icon, self.cfg, out_dir)
        except ValueError as e:   # e.g. title too long for the arc
            run.update(status="blocked", tier=BLOCK, reasons=run["reasons"] + [str(e)],
                       cost_usd=round(run["cost_usd"] + icon_cost, 4))
            self.save(run)
            return run
        run.update(icon_source=icon_src, badge_checks=b.checks, badge_files=b.files,
                   badge_failures=b.failures)
        run["cost_usd"] = round(run["cost_usd"] + icon_cost, 4)
        if not b.passed:   # an unprintable badge is a BLOCK too
            run.update(status="blocked", tier=BLOCK, reasons=run["reasons"] + b.failures)
            self.save(run)
            return run

        run["listing"] = make_listing(hook, cand, self.cfg, b.files["preview"],
                                      cand.started_at or snapshot.taken_at)
        run["drafted_at"] = self.clock().isoformat()
        run["token"] = secrets.token_urlsafe(24)   # secret in the action links
        if verdict.tier == HOLD:
            run["status"] = "pending_hold"
            now = self.clock()
            if verdict.release == RELEASE_NEXT_MORNING:
                run["not_before"] = next_morning(now).isoformat()
            start = datetime.fromisoformat(run.get("not_before") or now.isoformat())
            run["expires_at"] = (max(now, start) + timedelta(minutes=self.cfg.hold_expiry_min)).isoformat()
            self.save(run)
            self._email(run)
            run["emailed_at"] = self.clock().isoformat()
            self.save(run)
        else:   # you hear about it once it is actually live (or if it gets stuck)
            self._publish(run, how="auto (passed every safety check)")
        return run

    # ---------- email ----------
    def action_url(self, run, action):
        base = (self.cfg.public_base_url or "http://localhost:8080").rstrip("/")
        return f"{base}/a/{run['key']}/{action}?t={run['token']}"

    def _email(self, run):
        t = f'{run["title"]} ({run["year"]})'
        img = (run.get("badge_files") or {}).get("preview")
        if run["status"] == "pending_hold":
            subject = f"Needs your OK: {t}"
            why = "; ".join(run["reasons"])
            when = (f" Even if you approve now, it publishes no earlier than {fmt_local(run['not_before'])}."
                    if run.get("not_before") else "")
            lines = [f"{t} is drafted but NOT published.", f"Why it was held: {why}",
                     "It will not publish on its own; it expires " + fmt_local(run["expires_at"]) + "." + when, "",
                     f"Approve: {self.action_url(run, 'approve')}",
                     f"Reject:  {self.action_url(run, 'reject')}"]
            buttons = (self._button("Approve", self.action_url(run, "approve"), "#1a7f37")
                       + self._button("Reject", self.action_url(run, "reject"), "#b42318"))
            lead = (f"<b>{html.escape(t)}</b> is drafted but <b>not published</b>.<br>Why it was held: {html.escape(why)}"
                    + (f"<br>{html.escape(when.strip())}" if when else ""))
        elif run["status"] == "going_live":
            subject = f"Not live yet: {t}"
            err = run.get("go_live_error") or "the store page has not appeared yet"
            lines = [f"{t} was approved for the store, but after {self.cfg.live_wait_min} minutes it is still "
                     f"not live, so nothing has been posted. Problem: {err}", "It keeps trying on its own.", "",
                     f"Cancel it: {self.action_url(run, 'unpublish')}"]
            buttons = self._button("Cancel it", self.action_url(run, "unpublish"), "#b42318")
            lead = (f"<b>{html.escape(t)}</b> is <b>not live yet</b>, so nothing has been posted.<br>"
                    f"Problem: {html.escape(err)}<br>It keeps trying on its own.")
        else:
            problems = run.get("post_problems") or []
            subject = f"Published: {t}" + (f" ({len(problems)} problem{'s' * (len(problems) > 1)})" if problems else "")
            how = ("passed every safety check and is now live" if run.get("tier") != HOLD
                   else "is now live, as you approved")
            posted = [f"{x['platform'].title()}: {x['url']}" for x in run.get("posts", [])]
            le = run.get("list_email")
            later = ([f"Your mailing list gets the email at {fmt_local(le['due_at'])} "
                      f"(Unpublish before then and it is never sent)."] if le else [])
            lines = ([f"{t} {how}.", f"Store page: {run.get('product_url')}"] + posted + later
                     + [f"Did not work: {x}" for x in problems] + ["",
                     f"Changed your mind? Unpublish: {self.action_url(run, 'unpublish')}",
                     "It takes down the store page and the posts. The link keeps working until you use it."])
            buttons = self._button("Unpublish", self.action_url(run, "unpublish"), "#b42318")
            lead = (f"<b>{html.escape(t)}</b> {how}.<br>"
                    f"<a href='{html.escape(run.get('product_url') or '')}'>Store page</a>"
                    + "".join(f" · <a href='{html.escape(x['url'] or '')}'>{x['platform'].title()}</a>"
                              for x in run.get("posts", []))
                    + "".join(f"<br>{html.escape(x)}" for x in later)
                    + "".join(f"<br><b>Did not work:</b> {html.escape(x)}" for x in problems))
        detail = (f"Road: {road_label(run.get('road')) or 'n/a'} | delay {run.get('max_delay_min', 0)} min over normal\n"
                  f"Official text: {run.get('official_text', '')[:400]}")
        text = "\n".join(lines) + "\n\n" + detail
        body = (f"<div style='font-family:-apple-system,Helvetica,Arial,sans-serif;font-size:16px;color:#111'>"
                f"<p>{lead}</p>{{{{IMG}}}}<p>{buttons}</p>"
                f"<p style='color:#555;font-size:13px'>{html.escape(detail).replace(chr(10), '<br>')}</p></div>")
        img_url = (f"{self.cfg.public_base_url.rstrip('/')}/media/{run['key']}/preview.png?t={run['token']}"
                   if self.cfg.public_base_url and img and run.get("token") else None)
        self.mailer.send(subject, text, body, img, image_url=img_url)

    @staticmethod
    def _button(label, url, color):
        return (f"<a href='{html.escape(url)}' style='display:inline-block;padding:12px 22px;margin:0 8px 8px 0;"
                f"background:{color};color:#fff;text-decoration:none;border-radius:8px;font-weight:600'>{label}</a>")

    # ---------- decisions ----------
    def act(self, key, action, token):
        """Owner pressed a link. Returns (ok, message). Constant-time token check."""
        run = self.load(key) if key and key.isalnum() else None
        if not run or not token or not secrets.compare_digest(token, run.get("token", "")):
            return False, "That link is not valid."
        if action not in ACTIONS.get(run["status"], ()):
            return False, f"Nothing to do: {run['title']} is already {run['status'].replace('_', ' ')}."
        run["decided_at"] = self.clock().isoformat()
        if action == "approve":
            nb = run.get("not_before")
            if nb and self.clock() < datetime.fromisoformat(nb):
                run["status"] = "approved_waiting"
                self.save(run)
                return True, f"Approved. {run['title']} ({run['year']}) publishes {fmt_local(nb)}."
            self._publish(run, how="owner approved")
            return True, f"Published {run['title']} ({run['year']})."
        if action == "reject":
            run["status"] = "rejected"
        elif action == "unpublish":
            todo = self._take_down(run)
            run.update(status="unpublished", unpublished_at=self.clock().isoformat(), takedown_problems=todo)
            self.save(run)
            self._write_store()
            msg = f"{run['title']} ({run['year']}) is unpublished: store page and posts taken down."
            if todo:
                msg += " Still to do by hand: " + " | ".join(todo)
            return True, msg
        self.save(run)
        self._write_store()
        return True, f"{run['title']} ({run['year']}) is {run['status']}."

    def tick(self):
        """Run every few minutes: release approved badges whose time has come, and expire
        held badges nobody approved."""
        now, changed = self.clock(), []
        self._refresh_tokens(now)
        changed += self._count_sales(now)
        for run in self.all_runs():
            if run["status"] == "going_live":
                self._go_live(run)
                changed.append(run)
            elif run["status"] == "published":
                self._send_list_email(run, now)
            elif run["status"] == "approved_waiting" and now >= datetime.fromisoformat(run["not_before"]):
                self._publish(run, how="owner approved; released the morning after the event")
                changed.append(run)
            elif run["status"] == "pending_hold":
                if run.get("expires_at"):
                    expires = datetime.fromisoformat(run["expires_at"])
                else:
                    expires = datetime.fromisoformat(run["drafted_at"]) + timedelta(minutes=self.cfg.hold_expiry_min)
                if now >= expires:
                    run["status"] = "expired"
                    run["decided_at"] = now.isoformat()
                    self.save(run)
                    changed.append(run)
        return changed

    # ---------- going live ----------
    def _publish(self, run, how):
        run.update(status="going_live", published_how=how, go_live_started=self.clock().isoformat())
        self.save(run)
        self._go_live(run)

    def _go_live(self, run):
        """Make the product, then wait for the store page to load before announcing anything."""
        url = None
        try:
            self.printify.create(run)
            self.save(run)
            url = self.printify.product_url(run)
            live = bool(url) and self.printify.is_live(url)
            run["go_live_error"] = None
        except Exception as e:   # store trouble: retried on the next tick, from where it stopped
            run["go_live_error"] = str(e)[:300]
            print(f"Store not ready for {run['title']}: {run['go_live_error']}", flush=True)
            live = False
        if live:   # past this point errors are not about the store, so they are never hidden here
            return self._finish(run, url)
        self.save(run)
        started = datetime.fromisoformat(run["go_live_started"])
        if self.clock() - started >= timedelta(minutes=self.cfg.live_wait_min) and not run.get("stuck_emailed"):
            self._email(run)
            run["stuck_emailed"] = self.clock().isoformat()
            self.save(run)

    def _finish(self, run, url):
        now = self.clock()
        run.update(status="published", published_at=now.isoformat(), product_url=url, go_live_error=None,
                   seconds_data_to_live=round((now - datetime.fromisoformat(run["data_at"])).total_seconds(), 1))
        self.save(run)
        self._write_store()
        key_dir = os.path.join(self.runs_dir, run["key"])
        img = social_image(run["badge_files"]["pod"], os.path.join(key_dir, "social.jpg"), self.cfg)
        img_url = (f"{self.cfg.public_base_url.rstrip('/')}/s/{run['key']}.jpg"
                   if self.cfg.public_base_url else None)
        posts, problems = [], []
        if run.get("quiet"):   # the history set goes live without announcements
            run.update(posts=[], post_problems=[])
            self.save(run)
            return
        for outlet in self.socials:
            try:
                posts.append(outlet.post(run, url, img, img_url))
            except Exception as e:
                problems.append(f"{outlet.name}: {str(e)[:200]}")
        try:
            draft = self.mailchimp.draft(run, url, img_url)
            draft["due_at"] = (now + timedelta(minutes=self.cfg.list_delay_min)).isoformat()
            run["list_email"] = draft
        except Exception as e:
            problems.append(f"mailing list: {str(e)[:200]}")
        run.update(posts=posts, post_problems=problems)
        self.save(run)
        try:
            self._email(run)
            run["emailed_at"] = self.clock().isoformat()
        except Exception as e:
            run["email_error"] = f"{type(e).__name__}: {e}"[:300]
            print(f"Email to you FAILED: {run['email_error']}", flush=True)
        self.save(run)

    def _send_list_email(self, run, now):
        le = run.get("list_email")
        if not le or le.get("sent_at") or le.get("error") or now < datetime.fromisoformat(le["due_at"]):
            return
        try:
            self.mailchimp.send(le)
            le["sent_at"] = now.isoformat()
        except Exception as e:   # reported once; never retried blindly, so nobody gets it twice
            le["error"] = str(e)[:300]
            self.mailer.send(f"Mailing list email failed: {run['title']} ({run['year']})",
                             f"The list email did not go out: {le['error']}\nCheck the draft in Mailchimp.",
                             f"<p>The list email for <b>{html.escape(run['title'])}</b> did not go out: "
                             f"{html.escape(le['error'])}</p><p>Check the draft in Mailchimp.</p>")
        self.save(run)

    def _take_down(self, run):
        """Undo everything that went out. Returns what still needs doing by hand."""
        todo = []
        by_name = {o.name: o for o in self.socials}
        for post in run.get("posts", []):
            outlet = by_name.get(post["platform"])
            try:
                if not outlet:
                    raise RuntimeError("that account is switched off now")
                outlet.delete(post)
                post["deleted_at"] = self.clock().isoformat()
            except Exception:
                todo.append(f"delete the {post['platform'].title()} post {post.get('url')}")
        le = run.get("list_email")
        if le and le.get("sent_at"):
            todo.append("the mailing list email had already gone out")
        elif le:
            try:
                self.mailchimp.cancel(le)
                le["cancelled_at"] = self.clock().isoformat()
            except Exception:
                todo.append("delete the draft email in Mailchimp so it never sends")
            le["error"] = le.get("error") or "cancelled"   # tick never sends a cancelled email
        try:
            self.printify.take_down(run)
        except Exception:
            todo.append(f"hide the product in Shopify: {run.get('product_url')}")
        return todo

    def _count_sales(self, now):
        """Limited editions: keep 'N of 100 left' current, and take a badge off sale at 100."""
        last = getattr(self, "_sales_checked", None)
        if last and now - last < timedelta(minutes=self.cfg.orders_every_min):
            return []
        live = [r for r in self.all_runs() if r["status"] == "published" and (r.get("printify") or {}).get("product_id")]
        if not live:
            return []
        self._sales_checked = now
        try:
            counts = self.printify.sold_counts()
        except Exception as e:
            print(f"Sales count failed: {e}", flush=True)
            return []
        changed, size = [], self.cfg.edition_size
        for run in live:
            sold = counts.get(str(run["printify"]["product_id"]), 0)
            if sold == run.get("sold", 0):
                continue
            run["sold"], left = sold, max(0, size - sold)
            try:
                if left == 0:
                    self.printify.take_down(run)
                    for post in run.get("posts", []):
                        post["kept"] = True   # announcements stay up; the badge is just sold out
                    run.update(status="sold_out", sold_out_at=now.isoformat())
                    self.mailer.send(f"Sold out: {run['title']} ({run['year']})",
                                     f"All {size} of {run['title']} ({run['year']}) have sold. It is off the store "
                                     f"and shows as sold out in the collection.",
                                     f"<p>All {size} of <b>{html.escape(run['title'])} ({run['year']})</b> have sold. "
                                     f"It is off the store and shows as sold out in the collection.</p>")
                else:
                    self.printify.update_left(run, left)
            except Exception as e:
                run["sales_error"] = str(e)[:300]
                print(f"Sales update failed for {run['title']}: {e}", flush=True)
            self.save(run)
            changed.append(run)
        self._write_store()
        return changed

    def collection(self):
        """Every badge that has been on sale, newest first, for the website's gallery."""
        out = []
        for r in self.all_runs():
            if r["status"] not in ("published", "sold_out"):
                continue
            size, sold = self.cfg.edition_size, r.get("sold", 0)
            out.append({"key": r["key"], "title": r["title"], "year": r["year"], "status": r["status"],
                        "edition": size, "left": max(0, size - sold),
                        "link": r.get("product_url") if r["status"] == "published" else None,
                        "image": f"/s/{r['key']}.jpg", "since": r.get("published_at")})
        return sorted(out, key=lambda x: x["since"] or "", reverse=True)

    def _refresh_tokens(self, now):
        problems = self.tokens.refresh(self.http or __import__("requests"), now)
        if problems:
            self.mailer.send("Social account needs attention",
                             "A login token could not be refreshed, so posts there may stop:\n" + "\n".join(problems),
                             "<p>A login token could not be refreshed, so posts there may stop:</p><p>"
                             + "<br>".join(html.escape(x) for x in problems) + "</p>")

    def _write_store(self):
        """published.csv always mirrors what is live right now (so Unpublish removes the row)."""
        rows = [dict(r["listing"], Published="TRUE", Status="active")
                for r in self.all_runs() if r["status"] == "published"]
        path = os.path.join(self.cfg.data_dir, "published.csv")
        with open(path, "w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=SHOPIFY_COLUMNS)
            w.writeheader()
            w.writerows(rows)
