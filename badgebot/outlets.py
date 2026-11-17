"""Stage 6: going live. Printify makes the kiss-cut sticker and publishes it to Shopify; once
the store page actually loads, the badge is announced on Bluesky, Instagram and Threads.
Unpublish reverses all of it.

Every outlet runs in PRACTICE mode until its settings exist: it records the exact request
it would have made (data/outbox/outlets.jsonl, image bytes replaced by their size) and
returns made-up ids, so the whole flow can be tested with no accounts.

Post wording is a fixed template filled with only the approved title, the year and a
store link we build ourselves; no AI-written text ever reaches social media.
"""
import base64
from html import escape as html_escape
import io
import json
import os
import re
import time
from datetime import datetime, timezone

import requests
from PIL import Image, ImageDraw, ImageFont

UA = "badgebot/1.0 (Seattle traffic badges)"


def edition_html(body, left, size):
    """Listing text with the limited-edition line; only this line changes as copies sell."""
    body = re.sub(r'<p class="edition">.*?</p>', "", body or "")
    line = f"{left} of {size} left" if left > 0 else "Sold out"
    return body + f'<p class="edition"><b>Limited edition of {size}.</b> {line}.</p>'


URL_OK = re.compile(r"^https://[a-z0-9.-]+(:\d+)?/products?/[a-z0-9-]+$")   # Shopify /products/, Pop-Up /product/
TITLE_OK = re.compile(r"^[A-Z0-9 \-&*'.]{1,30}$")


class OutletError(Exception):
    pass


# ---------------------------------------------------------------- practice recorder
class Recorder:
    def __init__(self, cfg):
        self.path = os.path.join(cfg.data_dir, "outbox", "outlets.jsonl")

    def __call__(self, outlet, method, url, body=None):
        os.makedirs(os.path.dirname(self.path), exist_ok=True)
        clean = {k: (f"<{len(v)} bytes>" if isinstance(v, (bytes, str)) and len(v) > 500 else v)
                 for k, v in (body or {}).items()} if isinstance(body, dict) else body
        with open(self.path, "a", encoding="utf-8") as f:
            f.write(json.dumps({"at": datetime.now(timezone.utc).isoformat(), "outlet": outlet,
                                "method": method, "url": url, "body": clean}, default=str) + "\n")


def _check(resp, what):
    if resp.status_code >= 300:
        raise OutletError(f"{what}: HTTP {resp.status_code} {resp.text[:300]}")
    return resp.json() if resp.content else {}


# ---------------------------------------------------------------- post wording
def post_text(platform, title, year, url, store_url=None):
    """The only words that ever get posted. Refuses anything that isn't title/year/our link."""
    years = [int(y) for y in re.findall(r"\d{4}", str(year))]
    if (not TITLE_OK.match(title or "") or not re.fullmatch(r"\d{4}(\s*[-\u2013]\s*\d{4})?", str(year))
            or not all(1800 <= y <= 2200 for y in years) or years != sorted(years)):
        raise OutletError(f"refusing to post title {title!r}")
    if not URL_OK.match(url):
        raise OutletError(f"refusing to post link {url!r}")
    head = f"I SURVIVED {title} · {year}"
    if platform == "instagram":   # captions can't hold a clickable link
        domain = re.sub(r"^https://", "", (store_url or url.split("/products/")[0])).rstrip("/")
        return f"{head}\n\nNew Seattle traffic badge for your bumper. Link in bio ({domain}).\n\n#Seattle #SeattleTraffic #ISurvived"
    if platform == "threads":     # one topic tag per post
        return f"{head}\n\nNew Seattle traffic badge for your bumper: {url}\n\n#SeattleTraffic"
    return f"{head}\n\nNew Seattle traffic badge for your bumper: {url}"


def social_image(pod_png, out_path, cfg, size=1080):
    """Square JPEG for the posts: the patch on Express Yellow under I SURVIVED."""
    bg = Image.new("RGB", (size, size), "#FCCC0A")
    d = ImageDraw.Draw(bg)
    f = ImageFont.truetype(cfg.banner_font, 132)
    w = d.textlength("I SURVIVED", font=f)
    d.text(((size - w) / 2, 70), "I SURVIVED", font=f, fill="#111111")
    patch = Image.open(pod_png).convert("RGBA")
    patch = patch.crop(patch.getchannel("A").getbbox())          # drop the sheet's blank margin
    pw = 940
    patch = patch.resize((pw, round(patch.height * pw / patch.width)), Image.LANCZOS)
    top, bottom = 250, size - (120 if cfg.store_url else 60)    # the space between banner and URL
    bg.paste(patch, ((size - pw) // 2, top + (bottom - top - patch.height) // 2), patch)
    if cfg.store_url:
        g = ImageFont.truetype(cfg.title_font, 46)
        dom = re.sub(r"^https?://", "", cfg.store_url).rstrip("/")
        d.text(((size - d.textlength(dom, font=g)) / 2, size - 80), dom, font=g, fill="#111111")
    bg.save(out_path, "JPEG", quality=88)
    return out_path


# ---------------------------------------------------------------- Printify -> Shopify
class Printify:
    BASE = "https://api.printify.com/v1"

    def __init__(self, cfg, http=None, record=None):
        self.cfg, self.http, self.record = cfg, http or requests.Session(), record or Recorder(cfg)
        self.practice = not all([cfg.printify_token, cfg.printify_shop_id, cfg.printify_blueprint_id,
                                 cfg.printify_provider_id, cfg.printify_variant_id])

    def _h(self):
        return {"Authorization": f"Bearer {self.cfg.printify_token}", "User-Agent": UA}

    def _shop(self, path):
        return f"{self.BASE}/shops/{self.cfg.printify_shop_id}{path}"

    def create(self, run):
        """Upload the art, make the product, publish it to the connected Shopify store."""
        L = run["listing"]
        with open(run["badge_files"]["pod"], "rb") as f:
            art = base64.b64encode(f.read()).decode()
        upload = {"file_name": f"{L['Handle']}.png", "contents": art}
        product = {
            "title": L["Title"], "description": edition_html(L["Body (HTML)"], self.cfg.edition_size,
                                                             self.cfg.edition_size),
            "blueprint_id": int(self.cfg.printify_blueprint_id or 0),
            "print_provider_id": int(self.cfg.printify_provider_id or 0),
            "tags": [t.strip() for t in L["Tags"].split(",")],
            "variants": [{"id": int(self.cfg.printify_variant_id or 0),
                          "price": int(round(float(L["Variant Price"]) * 100)), "is_enabled": True}],
            "print_areas": [{"variant_ids": [int(self.cfg.printify_variant_id or 0)],
                             "placeholders": [{"position": "front", "images": [
                                 {"id": "<image id>", "x": 0.5, "y": 0.5, "scale": 1, "angle": 0}]}]}],
        }
        publish = {"title": True, "description": True, "images": True, "variants": True,
                   "tags": True, "keyFeatures": True, "shipping_template": True}
        state = run.setdefault("printify", {})   # progress is kept, so a retry never makes a duplicate
        if self.practice:
            self.record("printify", "POST", f"{self.BASE}/uploads/images.json", upload)
            self.record("printify", "POST", self._shop("/products.json"), product)
            self.record("printify", "POST", self._shop("/products/<product id>/publish.json"), publish)
            state.update(product_id=f"practice-{run['key']}", image_id="practice-image", publish_sent=True,
                         practice=True)
            return state
        if not state.get("image_id"):
            img = _check(self.http.post(f"{self.BASE}/uploads/images.json", json=upload, headers=self._h(),
                                        timeout=60), "Printify image upload")
            state["image_id"] = img["id"]
        if not state.get("product_id"):
            product["print_areas"][0]["placeholders"][0]["images"][0]["id"] = state["image_id"]
            prod = _check(self.http.post(self._shop("/products.json"), json=product, headers=self._h(), timeout=60),
                          "Printify create product")
            state["product_id"] = prod["id"]
        if not state.get("publish_sent"):
            _check(self.http.post(self._shop(f"/products/{state['product_id']}/publish.json"), json=publish,
                                  headers=self._h(), timeout=60), "Printify publish")
            state["publish_sent"] = True
        return state

    def product_url(self, run):
        """The Shopify page for the product, once Shopify has it; None until then."""
        handle = run["listing"]["Handle"]
        if self.practice:
            return f"{(self.cfg.store_url or 'https://practice.example').rstrip('/')}/products/{handle}"
        data = _check(self.http.get(self._shop(f"/products/{run['printify']['product_id']}.json"),
                                    headers=self._h(), timeout=30), "Printify product status")
        ext = (data.get("external") or {}).get("handle") or ""
        if not ext:
            return None
        if ext.startswith("https://") and ".myshopify.com/" not in ext:
            return ext.rstrip("/")   # e.g. the Pop-Up Store's own link: use it as given
        slug = ext.rstrip("/").split("/")[-1]
        if self.cfg.store_url:
            return f"{self.cfg.store_url.rstrip('/')}/products/{slug}"
        return ext if ext.startswith("https://") else None

    def is_live(self, url):
        """True only when the public page loads (a password-protected store redirects away)."""
        if self.practice:
            return True
        try:
            r = self.http.get(url, headers={"User-Agent": UA}, timeout=20, allow_redirects=True)
        except requests.RequestException:
            return False
        return r.status_code == 200 and ("/products/" in r.url or "/product/" in r.url)

    def sold_counts(self, pages=10):
        """Copies sold per product, from the shop's orders (canceled orders don't count)."""
        if self.practice:
            path = os.path.join(self.cfg.data_dir, "practice_sales.json")   # tests and dry runs
            return json.load(open(path, encoding="utf-8")) if os.path.exists(path) else {}
        counts = {}
        for page in range(1, pages + 1):
            data = _check(self.http.get(self._shop("/orders.json"), headers=self._h(), timeout=30,
                                        params={"limit": 50, "page": page}), "Printify orders")
            for order in data.get("data", []):
                if order.get("status") in ("canceled", "cancelled"):
                    continue
                for item in order.get("line_items", []):
                    pid = str(item.get("product_id"))
                    counts[pid] = counts.get(pid, 0) + int(item.get("quantity", 1))
            if page >= int(data.get("last_page") or 1):
                break
        return counts

    def update_left(self, run, left):
        """Rewrite the listing's '63 of 100 left' line."""
        pid = run["printify"]["product_id"]
        body = {"description": edition_html(run["listing"]["Body (HTML)"], left, self.cfg.edition_size)}
        if self.practice:
            self.record("printify", "PUT", self._shop(f"/products/{pid}.json"), body)
            return
        _check(self.http.put(self._shop(f"/products/{pid}.json"), json=body, headers=self._h(), timeout=30),
               "Printify update listing")
        _check(self.http.post(self._shop(f"/products/{pid}/publish.json"), headers=self._h(), timeout=60,
                              json={"title": False, "description": True, "images": False, "variants": False,
                                    "tags": False, "keyFeatures": False, "shipping_template": False}),
               "Printify republish listing")

    def update_art(self, run, pod_png, listing, left):
        """Swap in place: new picture, title and text on the product already on sale. Same product
        id, so its sales count and edition carry on."""
        pid = run["printify"]["product_id"]
        variant = int(self.cfg.printify_variant_id or 0)
        with open(pod_png, "rb") as f:
            upload = {"file_name": f"{listing['Handle']}-v2.png", "contents": base64.b64encode(f.read()).decode()}
        body = {"title": listing["Title"],
                "description": edition_html(listing["Body (HTML)"], left, self.cfg.edition_size),
                "tags": [t.strip() for t in listing["Tags"].split(",")],
                "variants": [{"id": variant, "price": int(round(float(listing["Variant Price"]) * 100)),
                              "is_enabled": True}],
                "print_areas": [{"variant_ids": [variant], "placeholders": [{"position": "front", "images": [
                    {"id": "<image id>", "x": 0.5, "y": 0.5, "scale": 1, "angle": 0}]}]}]}
        publish = {"title": True, "description": True, "images": True, "variants": False,
                   "tags": True, "keyFeatures": False, "shipping_template": False}
        if self.practice:
            self.record("printify", "POST", f"{self.BASE}/uploads/images.json", upload)
            self.record("printify", "PUT", self._shop(f"/products/{pid}.json"), body)
            self.record("printify", "POST", self._shop(f"/products/{pid}/publish.json"), publish)
            return
        # Printify attaches every size of the blueprint to a product (only ours enabled), and an
        # update must list them all: read the product's own variants and send them back as they are.
        current = _check(self.http.get(self._shop(f"/products/{pid}.json"), headers=self._h(), timeout=30),
                         "Printify read product")
        variants = [{"id": v["id"], "price": v.get("price"), "is_enabled": v.get("is_enabled", False)}
                    for v in current.get("variants") or [] if "id" in v]
        if variants:
            body["variants"] = variants
            body["print_areas"][0]["variant_ids"] = [v["id"] for v in variants]
        img = _check(self.http.post(f"{self.BASE}/uploads/images.json", json=upload, headers=self._h(), timeout=60),
                     "Printify image upload")
        body["print_areas"][0]["placeholders"][0]["images"][0]["id"] = img["id"]
        _check(self.http.put(self._shop(f"/products/{pid}.json"), json=body, headers=self._h(), timeout=60),
               "Printify update art")
        _check(self.http.post(self._shop(f"/products/{pid}/publish.json"), json=publish, headers=self._h(),
                              timeout=60), "Printify republish")

    def take_down(self, run):
        pid = (run.get("printify") or {}).get("product_id")
        if not pid:
            return
        if self.practice:
            self.record("printify", "DELETE", self._shop(f"/products/{pid}.json"))
            return
        _check(self.http.delete(self._shop(f"/products/{pid}.json"), headers=self._h(), timeout=30),
               "Printify delete product")


# ---------------------------------------------------------------- tokens that expire
class Tokens:
    """Instagram and Threads tokens last 60 days; tick() refreshes them weekly and keeps the
    newest copy in data/tokens.json (readable only by the server's user)."""
    REFRESH_DAYS = 7

    def __init__(self, cfg):
        self.cfg, self.path = cfg, os.path.join(cfg.data_dir, "tokens.json")

    def _load(self):
        try:
            return json.load(open(self.path, encoding="utf-8"))
        except (OSError, ValueError):
            return {}

    def get(self, name):
        return (self._load().get(name) or {}).get("token") or getattr(self.cfg, f"{name}_token")

    def save(self, name, token, error=None, now=None):
        data = self._load()
        entry = data.get(name, {})
        stamp = (now or datetime.now(timezone.utc)).isoformat()
        if token:
            entry.update(token=token, refreshed_at=stamp, error=None, failed_at=None)
        else:
            entry.update(error=error, failed_at=stamp)
        data[name] = entry
        fd = os.open(self.path, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            json.dump(data, f)

    def due(self, name, now):
        entry = self._load().get(name) or {}
        failed = entry.get("failed_at")
        if failed and (now - datetime.fromisoformat(failed)).total_seconds() < 86400:
            return False   # after a failure, try (and email you) at most once a day
        last = entry.get("refreshed_at")
        return not last or (now - datetime.fromisoformat(last)).days >= self.REFRESH_DAYS

    def refresh(self, http, now):
        """Returns a list of problems (empty if fine)."""
        problems = []
        for name, url, grant in (
                ("instagram", "https://graph.instagram.com/refresh_access_token", "ig_refresh_token"),
                ("threads", "https://graph.threads.net/refresh_access_token", "th_refresh_token")):
            tok = self.get(name)
            if not tok or not self.due(name, now):
                continue
            try:
                data = _check(http.get(url, params={"grant_type": grant, "access_token": tok}, timeout=30),
                              f"{name} token refresh")
                self.save(name, data["access_token"], now=now)
            except (OutletError, KeyError, requests.RequestException) as e:
                self.save(name, None, error=str(e)[:200], now=now)
                problems.append(f"{name}: {e}")
        return problems


# ---------------------------------------------------------------- social
class Bluesky:
    name = "bluesky"

    def __init__(self, cfg, http=None, record=None):
        self.cfg, self.http, self.record = cfg, http or requests.Session(), record or Recorder(cfg)
        self.practice = not (cfg.bluesky_handle and cfg.bluesky_app_password)
        self.pds = cfg.bluesky_pds.rstrip("/")

    def _session(self):
        return _check(self.http.post(f"{self.pds}/xrpc/com.atproto.server.createSession", timeout=30,
                                     json={"identifier": self.cfg.bluesky_handle,
                                           "password": self.cfg.bluesky_app_password}), "Bluesky sign-in")

    def post(self, run, url, image_path, image_url=None):
        text = post_text("bluesky", run["title"], run["year"], url)
        start = text.encode("utf-8").index(url.encode("utf-8"))
        record = {
            "$type": "app.bsky.feed.post", "text": text,
            "createdAt": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "langs": ["en"],
            "facets": [{"index": {"byteStart": start, "byteEnd": start + len(url.encode("utf-8"))},
                        "features": [{"$type": "app.bsky.richtext.facet#link", "uri": url}]}],
            "embed": {"$type": "app.bsky.embed.external", "external": {
                "uri": url, "title": f"I SURVIVED {run['title']} · {run['year']}",
                "description": "A collectible badge for your I Survived Seattle Traffic bumper sticker.",
                "thumb": "<uploaded image>"}},
        }
        if self.practice:
            self.record("bluesky", "POST", f"{self.pds}/xrpc/com.atproto.repo.createRecord", record)
            return {"platform": self.name, "id": "practice", "url": "https://bsky.app/practice", "practice": True}
        s = self._session()
        h = {"Authorization": f"Bearer {s['accessJwt']}"}
        with open(image_path, "rb") as f:
            blob = _check(self.http.post(f"{self.pds}/xrpc/com.atproto.repo.uploadBlob", data=f.read(), timeout=60,
                                         headers=dict(h, **{"Content-Type": "image/jpeg"})), "Bluesky image")["blob"]
        record["embed"]["external"]["thumb"] = blob
        res = _check(self.http.post(f"{self.pds}/xrpc/com.atproto.repo.createRecord", headers=h, timeout=30,
                                    json={"repo": s["did"], "collection": "app.bsky.feed.post", "record": record}),
                     "Bluesky post")
        rkey = res["uri"].rsplit("/", 1)[-1]
        return {"platform": self.name, "id": res["uri"],
                "url": f"https://bsky.app/profile/{self.cfg.bluesky_handle}/post/{rkey}"}

    def delete(self, post):
        if post.get("practice"):
            self.record("bluesky", "POST", f"{self.pds}/xrpc/com.atproto.repo.deleteRecord", {"uri": post["id"]})
            return
        s = self._session()
        repo, coll, rkey = post["id"].replace("at://", "").split("/")
        _check(self.http.post(f"{self.pds}/xrpc/com.atproto.repo.deleteRecord", timeout=30,
                              headers={"Authorization": f"Bearer {s['accessJwt']}"},
                              json={"repo": repo, "collection": coll, "rkey": rkey}), "Bluesky delete")


class _Meta:
    """Instagram and Threads publish the same way: make a container from a public image URL,
    wait until it has processed, then publish it."""
    name = api_attr = create_path = publish_path = ""

    def __init__(self, cfg, http=None, record=None, tokens=None, sleep=time.sleep):
        self.cfg, self.http, self.record = cfg, http or requests.Session(), record or Recorder(cfg)
        self.tokens, self.sleep = tokens or Tokens(cfg), sleep
        self.uid = getattr(cfg, f"{self.name}_user_id")
        self.api = getattr(cfg, f"{self.name}_api").rstrip("/")
        self.practice = not (self.uid and self.tokens.get(self.name))

    def _params(self, **kw):
        return dict(kw, access_token=self.tokens.get(self.name))

    def _container(self, run, url, image_url):
        raise NotImplementedError

    def post(self, run, url, image_path, image_url=None):
        body = self._container(run, url, image_url or "<public image url>")
        if self.practice:
            self.record(self.name, "POST", f"{self.api}/{self.uid or '<user id>'}/{self.create_path}", body)
            self.record(self.name, "POST", f"{self.api}/{self.uid or '<user id>'}/{self.publish_path}")
            return {"platform": self.name, "id": "practice", "url": f"https://{self.name}.example/practice",
                    "practice": True}
        if not image_url:
            raise OutletError(f"{self.name} needs PUBLIC_BASE_URL so it can fetch the picture")
        c = _check(self.http.post(f"{self.api}/{self.uid}/{self.create_path}", params=self._params(**body),
                                  timeout=60), f"{self.name} upload")
        for _ in range(20):   # usually ready within seconds; Threads suggests waiting up to 30
            st = _check(self.http.get(f"{self.api}/{c['id']}", params=self._params(fields="status_code,status"),
                                      timeout=30), f"{self.name} status")
            state = st.get("status_code") or st.get("status")
            if state == "FINISHED":
                break
            if state in ("ERROR", "EXPIRED"):
                raise OutletError(f"{self.name} could not process the picture: {st}")
            self.sleep(3)
        pub = _check(self.http.post(f"{self.api}/{self.uid}/{self.publish_path}",
                                    params=self._params(creation_id=c["id"]), timeout=60), f"{self.name} publish")
        link = _check(self.http.get(f"{self.api}/{pub['id']}", params=self._params(fields="permalink"),
                                    timeout=30), f"{self.name} link").get("permalink")
        return {"platform": self.name, "id": pub["id"], "url": link}

    def delete(self, post):
        if post.get("practice"):
            self.record(self.name, "DELETE", f"{self.api}/{post['id']}")
            return
        _check(self.http.delete(f"{self.api}/{post['id']}", params=self._params(), timeout=30),
               f"{self.name} delete")


class Instagram(_Meta):
    name, create_path, publish_path = "instagram", "media", "media_publish"

    def _container(self, run, url, image_url):
        return {"image_url": image_url,
                "caption": post_text("instagram", run["title"], run["year"], url, self.cfg.store_url)}


class Threads(_Meta):
    name, create_path, publish_path = "threads", "threads", "threads_publish"

    def _container(self, run, url, image_url):
        return {"media_type": "IMAGE", "image_url": image_url,
                "text": post_text("threads", run["title"], run["year"], url)}


def social_outlets(cfg, http=None, record=None, sleep=time.sleep):
    record = record or Recorder(cfg)
    tokens = Tokens(cfg)
    out = [Bluesky(cfg, http, record), Threads(cfg, http, record, tokens, sleep)]
    if cfg.instagram_enabled:
        out.insert(1, Instagram(cfg, http, record, tokens, sleep))
    return out


# ---------------------------------------------------------------- mailing list
class Mailchimp:
    """Drafts the list email as soon as the badge is live (so problems show up early), sends it
    list_delay_min later, and deletes the draft if you Unpublish first."""
    name = "mailchimp"

    def __init__(self, cfg, http=None, record=None):
        self.cfg, self.http, self.record = cfg, http or requests.Session(), record or Recorder(cfg)
        key = cfg.mailchimp_api_key or ""
        self.practice = not (key and "-" in key and cfg.mailchimp_list_id)
        self.base = f"https://{key.rsplit('-', 1)[-1] if not self.practice else '<dc>'}.api.mailchimp.com/3.0"

    def _req(self, method, path, what, **kw):
        r = self.http.request(method, f"{self.base}{path}", auth=("badgebot", self.cfg.mailchimp_api_key),
                              headers={"User-Agent": UA}, timeout=30, **kw)
        return _check(r, f"Mailchimp {what}")

    def email_html(self, run, url, image_url):
        t = f"I SURVIVED {run['title']} · {run['year']}"
        img = f'<p><img src="{image_url}" width="480" alt="{t}" style="max-width:100%"></p>' if image_url else ""
        return (f'<div style="font-family:Helvetica,Arial,sans-serif;font-size:17px;color:#111;max-width:520px">'
                f'<h1 style="font-size:26px">{t}</h1>{img}'
                f'<p>A new badge for your I Survived Seattle Traffic bumper sticker.</p>'
                f'<p><a href="{url}" style="display:inline-block;padding:14px 24px;background:#111;color:#FCCC0A;'
                f'text-decoration:none;border-radius:8px;font-weight:bold">Get the badge</a></p>'
                f'<p style="font-size:12px;color:#666">*|LIST:ADDRESSLINE|*<br>'
                f'<a href="*|UNSUB|*">Unsubscribe</a></p></div>')

    def draft(self, run, url, image_url=None):
        post_text("mailchimp", run["title"], run["year"], url)   # same refusal rules as the posts
        subject = f"I SURVIVED {run['title']} · {run['year']}"
        campaign = {"type": "regular", "recipients": {"list_id": self.cfg.mailchimp_list_id},
                    "settings": {"subject_line": subject, "title": f"badge {run['key']}",
                                 "preview_text": "A new Seattle traffic badge just dropped.",
                                 "from_name": self.cfg.list_from_name,
                                 "reply_to": self.cfg.list_reply_to or self.cfg.mail_from or ""}}
        content = {"html": self.email_html(run, url, image_url)}
        if self.practice:
            self.record("mailchimp", "POST", f"{self.base}/campaigns", campaign)
            self.record("mailchimp", "PUT", f"{self.base}/campaigns/<id>/content", content)
            return {"platform": self.name, "id": "practice", "practice": True}
        c = self._req("POST", "/campaigns", "draft", json=campaign)
        self._req("PUT", f"/campaigns/{c['id']}/content", "content", json=content)
        return {"platform": self.name, "id": c["id"]}

    def draft_announcement(self, items):
        """One email showing a set of badges (the V2 drop). Drafted only; you send it from Mailchimp.
        Each item: title, year, url, image_url, new (True = first time on sale)."""
        for i in items:
            post_text("mailchimp", i["title"], i["year"], i["url"])   # same refusal rules as the posts
        n_new = sum(i["new"] for i in items)
        subject = "New Seattle traffic badges, and a new look"
        preview = (f"{n_new} new badges and fresh art on {len(items) - n_new} more."
                   if n_new and len(items) > n_new else "Fresh art for the badges you know.")
        def cell(i):
            t = html_escape(f"{i['title']} · {str(i['year']).replace('-', '–')}")
            img = (f'<img src="{i["image_url"]}" width="240" alt="{t}" style="max-width:100%;display:block;margin:0 auto">'
                   if i.get("image_url") else "")
            tag = '<div style="font-size:12px;color:#b42318;font-weight:bold">NEW</div>' if i["new"] else ""
            return (f'<td style="width:50%;padding:10px;text-align:center;vertical-align:top">{img}{tag}'
                    f'<div style="font-weight:bold;margin:6px 0">{t}</div>'
                    f'<a href="{i["url"]}" style="color:#111">Get the badge</a></td>')
        order = sorted(items, key=lambda i: not i["new"])
        rows = "".join("<tr>" + "".join(cell(i) for i in order[k:k + 2]) + "</tr>" for k in range(0, len(order), 2))
        body = (f'<div style="font-family:Helvetica,Arial,sans-serif;font-size:17px;color:#111;max-width:560px">'
                f'<h1 style="font-size:26px">New badges, and a new look</h1>'
                f'<p>Every badge in the Bad Traffic 206 history set now has a painted picture, and some have new '
                f'names. Each one is still a limited edition of 100, made for the slots on your '
                f'I Survived Seattle Traffic bumper sticker.</p>'
                f'<table role="presentation" style="width:100%;border-collapse:collapse">{rows}</table>'
                f'<p style="font-size:12px;color:#666">*|LIST:ADDRESSLINE|*<br>'
                f'<a href="*|UNSUB|*">Unsubscribe</a></p></div>')
        campaign = {"type": "regular", "recipients": {"list_id": self.cfg.mailchimp_list_id},
                    "settings": {"subject_line": subject, "title": "V2 badges", "preview_text": preview,
                                 "from_name": self.cfg.list_from_name,
                                 "reply_to": self.cfg.list_reply_to or self.cfg.mail_from or ""}}
        if self.practice:
            self.record("mailchimp", "POST", f"{self.base}/campaigns", campaign)
            self.record("mailchimp", "PUT", f"{self.base}/campaigns/<id>/content", {"html": body})
            return {"platform": self.name, "id": "practice", "practice": True, "title": "V2 badges"}
        c = self._req("POST", "/campaigns", "draft", json=campaign)
        self._req("PUT", f"/campaigns/{c['id']}/content", "content", json={"html": body})
        return {"platform": self.name, "id": c["id"], "title": "V2 badges"}

    def send(self, draft):
        if draft.get("practice"):
            self.record("mailchimp", "POST", f"{self.base}/campaigns/<id>/actions/send")
            return
        self._req("POST", f"/campaigns/{draft['id']}/actions/send", "send")

    def cancel(self, draft):
        if draft.get("practice"):
            self.record("mailchimp", "DELETE", f"{self.base}/campaigns/<id>")
            return
        self._req("DELETE", f"/campaigns/{draft['id']}", "delete draft")
