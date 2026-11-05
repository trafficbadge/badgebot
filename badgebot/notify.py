"""Email notifications to the owner: through Resend's web API when RESEND_API_KEY is set
(needed on Railway, which blocks SMTP on its smaller plans), otherwise over SMTP.

Works with any provider that allows SMTP with an app password (iCloud, Fastmail, Yahoo,
Gmail...). Without SMTP settings, each email is written to data/outbox/ as an .eml file
plus a line in data/outbox.jsonl, which is what the tests read.
"""
import base64
import html as _html
import json
import mimetypes
import os
import smtplib
import ssl
from datetime import datetime, timezone
from email.message import EmailMessage
from email.utils import formatdate, make_msgid

import requests

RESEND_URL = "https://api.resend.com/emails"


class Mailer:
    def __init__(self, cfg):
        self.cfg = cfg
        self.resend = bool(cfg.resend_api_key and cfg.owner_email)
        self.live = self.resend or all([cfg.smtp_host, cfg.smtp_user, cfg.smtp_password, cfg.owner_email])
        self.outbox_dir = os.path.join(cfg.data_dir, "outbox")

    def build(self, subject, text, html, image_path=None):
        msg = EmailMessage()
        msg["Subject"] = subject
        msg["From"] = self.cfg.mail_from or self.cfg.smtp_user or "badgebot@localhost"
        msg["To"] = self.cfg.owner_email or "owner@localhost"
        # Gmail rejects mail without these two headers, after the sending server has accepted it
        msg["Date"] = formatdate(localtime=True)
        sender = msg["From"]
        msg["Message-ID"] = make_msgid(domain=sender.split("@")[-1] if "@" in sender else "badgebot.local")
        msg.set_content(text)
        if image_path and os.path.exists(image_path):
            cid = make_msgid(domain="badgebot")
            msg.add_alternative(html.replace("{{IMG}}", f'<img src="cid:{cid[1:-1]}" width="300" '
                                                   f'alt="badge preview" style="display:block;margin:12px 0">'),
                                subtype="html")
            ctype, _ = mimetypes.guess_type(image_path)
            maintype, subtype = (ctype or "image/png").split("/")
            with open(image_path, "rb") as f:
                msg.get_payload()[1].add_related(f.read(), maintype=maintype, subtype=subtype, cid=cid)
        else:
            msg.add_alternative(html.replace("{{IMG}}", ""), subtype="html")
        return msg

    def _send_resend(self, subject, text, html, image_path=None, image_url=None):
        sender = self.cfg.mail_from or "info@badtraffic206.com"
        body = {"from": f"Badgebot <{sender}>", "to": [self.cfg.owner_email], "subject": subject, "text": text}
        if image_url:   # the server's own picture link: shows in every mail app
            body["html"] = html.replace("{{IMG}}", f'<img src="{_html.escape(image_url)}" width="300" '
                                                   f'alt="badge preview" style="display:block;margin:12px 0">')
        else:
            body["html"] = html.replace("{{IMG}}", "")
            if image_path and os.path.exists(image_path):
                with open(image_path, "rb") as f:
                    body["attachments"] = [{"filename": "badge.png", "content": base64.b64encode(f.read()).decode()}]
        r = requests.post(RESEND_URL, json=body, timeout=30,
                          headers={"Authorization": f"Bearer {self.cfg.resend_api_key}", "User-Agent": "badgebot/1.0"})
        if r.status_code >= 300:
            raise RuntimeError(f"Resend refused the email: HTTP {r.status_code} {r.text[:200]}")
        print(f"Email sent to {self.cfg.owner_email} via Resend: {subject}", flush=True)

    def send(self, subject, text, html, image_path=None, image_url=None):
        if self.resend:
            return self._send_resend(subject, text, html, image_path, image_url)
        msg = self.build(subject, text, html, image_path)
        if not self.live:
            os.makedirs(self.outbox_dir, exist_ok=True)
            stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S%f")
            with open(os.path.join(self.outbox_dir, f"{stamp}.eml"), "wb") as f:
                f.write(bytes(msg))
            missing = [n for n, v in (("SMTP_HOST", self.cfg.smtp_host), ("SMTP_USER", self.cfg.smtp_user),
                                      ("SMTP_PASSWORD", self.cfg.smtp_password),
                                      ("OWNER_EMAIL", self.cfg.owner_email)) if not v]
            print(f"Email NOT sent (missing {', '.join(missing)}); saved to {self.outbox_dir}: {subject}", flush=True)
            with open(os.path.join(self.cfg.data_dir, "outbox.jsonl"), "a", encoding="utf-8") as f:
                f.write(json.dumps({"at": stamp, "subject": subject, "text": text}) + "\n")
            return
        port = int(self.cfg.smtp_port or 587)
        ctx = ssl.create_default_context()
        if port == 465:
            with smtplib.SMTP_SSL(self.cfg.smtp_host, port, context=ctx, timeout=30) as s:
                s.login(self.cfg.smtp_user, self.cfg.smtp_password)
                s.send_message(msg)
        else:
            with smtplib.SMTP(self.cfg.smtp_host, port, timeout=30) as s:
                s.starttls(context=ctx)
                s.login(self.cfg.smtp_user, self.cfg.smtp_password)
                s.send_message(msg)
        print(f"Email sent to {self.cfg.owner_email} via {self.cfg.smtp_host}: {subject}", flush=True)
