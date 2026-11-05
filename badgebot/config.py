"""All tunable settings in one place. Secrets come from environment variables only."""
import os
from dataclasses import dataclass, field


FONT_DIR = os.path.join(os.path.dirname(__file__), "fonts")


def _env(name, default=None):
    v = os.environ.get(name)
    return v if v not in (None, "") else default


@dataclass
class Config:
    # --- Detection -------------------------------------------------------
    # Minutes of delay over WSDOT's average before a corridor counts as "epic".
    delay_threshold_min: int = 120
    # WSDOT travel-time routes we watch: any RouteName containing one of these.
    corridors: tuple = ("I-5", "I-405", "I-90", "SR 520", "SR-520", "SR 99", "SR-99")
    # WSDOT region codes for the Seattle area in Highway Alerts.
    regions: tuple = ("Northwest", "NW")
    # A hook alone (no 2-hour delay) is enough if the alert is this priority or higher.
    hook_only_priorities: tuple = ("Highest", "High")

    # --- Buzz: WSDOT's own Bluesky posts that get unusual attention --------------------
    # Never publishes on its own: drafts a badge and emails you Approve / Reject.
    wsdot_bluesky: str = "traffic.wsdot.wa.gov"
    buzz_min_score: int = 30           # likes + 2 x reposts + replies (Aug-Nov 2026: ~1 post a week)
    buzz_max_age_h: int = 48
    buzz_every_min: int = 15

    # --- Approval ----------------------------------------------------------
    hold_expiry_min: int = 4320        # HOLD-tier drafts expire after 3 days if never approved

    # --- Badge ---------------------------------------------------------------
    # Locked test design (Badge Style Explorations canvas, "Oval patches in a row",
    # Express Yellow): wide oval patch, black "road" ring with a dashed center line,
    # white title arched on top, white year at the bottom, orange center, black picture.
    shape: str = "patch_oval"
    width_in: float = 1.8              # art fits a 2 x 2 in kiss-cut sheet after the vendor's border
    height_in: float = 1.345
    pod_sheet_in: float = 2.0          # Printify kiss-cut sticker size the patch ships on
    pod_px: int = 1800                 # vendor-recommended square file size
    dpi: int = 300
    bleed_mm: float = 3.0              # white artwork extends past the cut line
    title_max_chars: int = 22          # one arched line; the renderer shrinks it to fit
    min_cap_height_mm: float = 1.8     # smallest allowed letter height in print
    min_contrast: float = 4.5          # WCAG AA: text vs ring, picture vs center
    palette: dict = field(default_factory=lambda: {
        "edge": "#FFFFFF",      # thin white rim at the cut line
        "ring": "#111111",      # the road
        "field": "#FF6319",     # orange center
        "icon": "#111111",      # the picture
        "highlight": "#FCCC0A", # yellow details inside the picture (honey, sparks)
        "text": "#FFFFFF",      # title, year, road dashes
    })
    # Archivo (free, Open Font License), bundled in badgebot/fonts with its OFL.txt.
    title_font: str = field(default_factory=lambda: _env("BADGE_FONT", os.path.join(FONT_DIR, "Archivo_Condensed-Bold.ttf")))
    banner_font: str = field(default_factory=lambda: os.path.join(FONT_DIR, "Archivo-Black.ttf"))
    body_font: str = field(default_factory=lambda: os.path.join(FONT_DIR, "Archivo_Condensed-Medium.ttf"))

    # --- Listing -------------------------------------------------------------
    badge_price: str = "4.00"
    vendor: str = "I Survived Seattle Traffic"

    # --- Services (from environment) ----------------------------------------
    wsdot_access_code: str = field(default_factory=lambda: _env("WSDOT_ACCESS_CODE"))
    anthropic_api_key: str = field(default_factory=lambda: _env("ANTHROPIC_API_KEY"))
    anthropic_model: str = field(default_factory=lambda: _env("ANTHROPIC_MODEL", "claude-sonnet-5-5"))
    smtp_host: str = field(default_factory=lambda: _env("SMTP_HOST"))
    smtp_port: str = field(default_factory=lambda: _env("SMTP_PORT", "587"))
    smtp_user: str = field(default_factory=lambda: _env("SMTP_USER"))
    smtp_password: str = field(default_factory=lambda: _env("SMTP_PASSWORD"))   # an app password
    mail_from: str = field(default_factory=lambda: _env("MAIL_FROM"))
    owner_email: str = field(default_factory=lambda: _env("OWNER_EMAIL"))
    public_base_url: str = field(default_factory=lambda: _env("PUBLIC_BASE_URL"))  # where the action links point
    data_dir: str = field(default_factory=lambda: _env("BADGEBOT_DATA", "data"))

    # --- Store: Printify makes the sticker and publishes it to Shopify -----------------
    # Each service below runs in PRACTICE mode (records what it would send, in
    # data/outbox/outlets.jsonl) until its settings are present.
    store_url: str = field(default_factory=lambda: _env("STORE_URL"))        # https://seattletrafficbadges.com
    printify_token: str = field(default_factory=lambda: _env("PRINTIFY_TOKEN"))
    printify_shop_id: str = field(default_factory=lambda: _env("PRINTIFY_SHOP_ID"))
    printify_blueprint_id: str = field(default_factory=lambda: _env("PRINTIFY_BLUEPRINT_ID"))  # Kiss-Cut Stickers
    printify_provider_id: str = field(default_factory=lambda: _env("PRINTIFY_PROVIDER_ID"))
    printify_variant_id: str = field(default_factory=lambda: _env("PRINTIFY_VARIANT_ID"))      # the 2" x 2" size
    live_wait_min: int = 45            # give up waiting for the store page after this, and email you

    # --- Social: posted only after the store page is live; deleted on Unpublish ---------
    bluesky_handle: str = field(default_factory=lambda: _env("BLUESKY_HANDLE"))
    bluesky_app_password: str = field(default_factory=lambda: _env("BLUESKY_APP_PASSWORD"))
    bluesky_pds: str = field(default_factory=lambda: _env("BLUESKY_PDS", "https://bsky.social"))
    instagram_enabled: bool = field(default_factory=lambda: _env("INSTAGRAM_ENABLED", "") == "1")  # off for the first set
    instagram_user_id: str = field(default_factory=lambda: _env("INSTAGRAM_USER_ID"))
    instagram_token: str = field(default_factory=lambda: _env("INSTAGRAM_TOKEN"))   # long-lived; auto-refreshed
    instagram_api: str = field(default_factory=lambda: _env("INSTAGRAM_API", "https://graph.instagram.com/v23.0"))
    threads_user_id: str = field(default_factory=lambda: _env("THREADS_USER_ID"))
    threads_token: str = field(default_factory=lambda: _env("THREADS_TOKEN"))       # long-lived; auto-refreshed
    threads_api: str = field(default_factory=lambda: _env("THREADS_API", "https://graph.threads.net/v1.0"))

    # --- Mailing list: an email can't be taken back, so it waits; Unpublish cancels it --
    mailchimp_api_key: str = field(default_factory=lambda: _env("MAILCHIMP_API_KEY"))   # ends in -us21 etc.
    mailchimp_list_id: str = field(default_factory=lambda: _env("MAILCHIMP_LIST_ID"))   # the Audience ID
    list_from_name: str = field(default_factory=lambda: _env("LIST_FROM_NAME", "Seattle Traffic Badges"))
    list_reply_to: str = field(default_factory=lambda: _env("LIST_REPLY_TO"))
    list_delay_min: int = 120
