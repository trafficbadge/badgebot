"""The history set: retro badges for events that already happened, from the Historical Badges
running list. They go on sale together, quietly: no posts, no list email, one summary email to you.

V2 (Nov 17, 2026): all 17 badges use painted pictures in badgebot/art replace the drawn scenes and icons, and the
titles come from the V2 art. Badges already on sale keep their listing, their sales count and
their edition of 100; only the picture, title and text change ("swap in place"). `was` is the
title a badge first went on sale under: it keeps the badge's key, so it is never listed twice.

Art kinds: ("art", file in badgebot/art), ("scene", key in icons.SCENES), ("icon", key in icons.LIBRARY).
Not here yet: the Feb 2019 snowstorm (needs a new name; Snowpocalypse stays with Dec 2008).
"""
import hashlib

HISTORY = [
    dict(title="SHIP CANAL SQUEEZE", year=2025, art=("art", "ship_canal_squeeze.png"),
         story="Summer 2025: northbound I-5 squeezed to two lanes on the Ship Canal Bridge for four weeks."),
    dict(title="MADISON MAYHEM", was="MADISON ST.", year="2021-2024", art=("art", "madison_mayhem.png"),
         story="2021 to 2024: Madison Street torn up to build the RapidRide G Line."),
    dict(title="PORTAGE BAY PURGATORY", was="520", year="2024-2032", art=("art", "portage_bay_purgatory.png"),
         story="2024 to about 2032: the SR 520 Portage Bay Bridge rebuild."),
    dict(title="WEST SEATTLE BRIDGE", year=2020, art=("art", "west_seattle_bridge.png"),
         story="March 23, 2020: the West Seattle Bridge closed for about 908 days after it cracked."),
    dict(title="VIADOOM", year=2019, art=("art", "viadoom.png"),
         story="January 2019: the Alaskan Way Viaduct closed for good, and three weeks with no SR 99."),
    dict(title="FEATHERED KERFLUFFLE", was="RUFFLED FEATHERS", year=2018, art=("art", "feathered_kerfluffle.png"),
         story="May 23, 2018: about 40,000 pounds of chicken feathers spilled across I-5."),
    dict(title="CRABPOCALYPSE", year=2016, art=("art", "crabpocalypse.png"),
         story="April 4, 2016: frozen crab spilled across the northbound Viaduct."),
    dict(title="STICKY SITUATION", was="HONEY - DON'T", year=2015, art=("art", "sticky_situation.png"),
         story="April 17, 2015: a semi carrying beehives overturned at I-5 and I-405."),
    dict(title="FISHY BUSINESS", was="FISHY FRACAS", year=2015, art=("art", "fishy_business.png"),
         story="March 24, 2015: a fish truck rolled on the southbound Viaduct and closed it for nine hours."),
    dict(title="BERTHA", was="BERTHA GOT STUCK", year=2013, art=("art", "bertha.png"),
         story="December 6, 2013: the SR 99 tunnel machine stopped, and stayed stuck for about two years."),
    dict(title="SNOWPOCALYPSE", year=2008, art=("art", "snowpocalypse.png"),
         story="December 2008: the storm that buried Seattle for days."),
    dict(title="THUNDER SNOW", year=2002, art=("art", "thunder_snow.png"),
         story="March 8, 2002: snow, hail and lightning all at once."),
    dict(title="I-90 SINKING BRIDGE", was="I-90 BRIDGE", year=1990, art=("art", "i90_sinking_bridge.png"),
         story="November 25, 1990: the old I-90 floating bridge sank."),
    dict(title="HOOD CANAL BRIDGE", was="HOOD CANAL", year=1979, art=("art", "hood_canal_bridge.png"),
         story="February 13, 1979: the Hood Canal Bridge's western half sank in a windstorm."),
    dict(title="SPOKANE ST.", year=1978, art=("art", "spokane_st.png"),
         story="June 11, 1978: a freighter hit the Spokane Street drawbridge and left it stuck open."),
    dict(title="RECORD 20-INCH SNOW", year=1950, art=("art", "record_20_inch_snow.png"),
         story="January 13, 1950: 20 inches of snow in one day, the Sea-Tac record."),
    dict(title="GALLOPING GERTIE", year=1940, art=("art", "galloping_gertie.png"),
         story="November 7, 1940: the first Tacoma Narrows Bridge twisted itself apart in the wind, "
               "four months after it opened."),
]

# Waiting for better art (none right now); everything else is on sale.
HELD = set()
LAUNCH = {h["title"] for h in HISTORY if h["title"] not in HELD}
# The V2 drop: what the one-time announcement email shows.
V2 = [h["title"] for h in HISTORY if h["art"][0] == "art"]


def history_key(h):
    """Run key for a history badge. Built from the first title it sold under, so a rename keeps it."""
    return "h" + hashlib.sha1(f"{h.get('was', h['title'])}|{h['year']}".encode()).hexdigest()[:9]


def source(h):
    return f"{h['art'][0]}:{h['art'][1]}"
