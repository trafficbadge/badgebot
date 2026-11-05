"""Tiny web server for the links in the emails.

GET  /a/<key>/<action>?t=<token>   shows a confirm page (never acts: mail apps and link
                                   scanners open links on their own, so a GET must be harmless)
POST /a/<key>/<action>             does it, after checking the secret token again
GET  /media/<key>/preview.png      badge preview image
"""
import html
import os

from flask import Flask, Response, abort, request, send_file

LABELS = {"approve": ("Approve and publish", "#1a7f37"),
          "reject": ("Reject", "#b42318"),
          "unpublish": ("Unpublish", "#b42318")}

PAGE = """<!doctype html><html><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<meta name="referrer" content="no-referrer"><title>Badge</title>
<style>body{{font-family:-apple-system,Helvetica,Arial,sans-serif;max-width:480px;margin:40px auto;padding:0 16px;color:#111}}
img{{max-width:100%}}button{{font-size:18px;padding:14px 26px;border:0;border-radius:10px;color:#fff;background:{color}}}</style>
</head><body>{body}</body></html>"""


def make_app(pipeline, cfg):
    app = Flask(__name__)

    def page(body, color="#333", status=200):
        return Response(PAGE.format(body=body, color=color), status=status, mimetype="text/html")

    @app.get("/a/<key>/<action>")
    def confirm(key, action):
        run = pipeline.load(key) if key.isalnum() else None
        token = request.args.get("t", "")
        if action not in LABELS or not run or token != run.get("token"):
            return page("<p>That link is not valid.</p>", status=404)
        label, color = LABELS[action]
        title = html.escape(f"{run['title']} ({run['year']})")
        return page(f"<h2>{title}</h2><p>Currently: {html.escape(run['status'].replace('_', ' '))}</p>"
                    f"<img src='/media/{key}/preview.png?t={html.escape(token)}' alt='badge'>"
                    f"<form method='post'><input type='hidden' name='t' value='{html.escape(token)}'>"
                    f"<p><button type='submit'>{label}</button></p></form>", color)

    @app.post("/a/<key>/<action>")
    def do(key, action):
        if action not in LABELS:
            abort(404)
        ok, msg = pipeline.act(key, action, request.form.get("t", ""))
        return page(f"<p>{html.escape(msg)}</p>", status=200 if ok else 400)

    @app.get("/media/<key>/preview.png")
    def media(key):
        run = pipeline.load(key) if key.isalnum() else None
        if not run or request.args.get("t") != run.get("token"):
            abort(404)
        path = os.path.join(pipeline.runs_dir, key, "preview.png")
        if not os.path.exists(path):
            abort(404)
        return send_file(os.path.abspath(path), mimetype="image/png")

    @app.get("/s/<key>.jpg")
    def social_picture(key):
        """Public picture for posts and the list email (Threads/Instagram fetch it by URL).
        Served only while the badge is live; Unpublish makes it disappear."""
        run = pipeline.load(key) if key.isalnum() else None
        path = os.path.join(pipeline.runs_dir, key, "social.jpg")
        if not run or run.get("status") != "published" or not os.path.exists(path):
            abort(404)
        return send_file(os.path.abspath(path), mimetype="image/jpeg")

    @app.get("/health")
    def health():
        return {"ok": True}

    return app
