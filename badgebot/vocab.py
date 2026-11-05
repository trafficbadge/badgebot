"""Word lists. Edit these to tune what is sticker-worthy and what is off-limits."""
import re

# Things that make a slowdown sticker-worthy: something nameable and drawable.
CARGO = {
    "blueberries", "blueberry", "salmon", "fish", "crab", "crabs", "chickens", "chicken",
    "eggs", "honey", "bees", "beer", "wine", "apples", "potatoes", "onions", "logs", "lumber",
    "hay", "milk", "cheese", "coffee", "toilet", "paper", "pumpkins", "christmas", "trees",
    "cows", "cattle", "pigs", "sheep", "goats", "llamas", "alpacas", "mattresses", "tires",
    "candy", "cherries", "berries", "frozen", "peas", "corn", "watermelons",
}
WEATHER = {"snow", "snowstorm", "blizzard", "ice", "icy", "freezing", "windstorm", "flood",
           "flooding", "landslide", "mudslide", "smoke", "wildfire", "fog", "hail"}
# Not hooks: bridge, drawbridge, tunnel, ferry, boat. They are place names in routine WSDOT
# posts ("all lanes closed due to boat traffic" happens several times a day).
EVENTS = {"sinkhole", "moose", "elk", "bear", "deer", "cougar", "goose", "geese"}
# Citizens gathering: celebrated, but only by the act, never the cause (see safety.py).
GATHERINGS = {"march", "marchers", "marched", "rally", "parade", "walkout", "vigil",
              "celebration", "celebrating", "crowd", "crowds", "strike"}
HOOK_WORDS = CARGO | WEATHER | EVENTS | GATHERINGS

# The only words a gathering badge's title may use besides GENERIC: the act itself.
# Cause words, slogans, groups and names are never allowed, even if the alert says them.
GATHERING_TITLE_WORDS = {"march", "rally", "parade", "walkout", "vigil", "celebration",
                         "crowds", "strike", "people's", "thousands", "downtown"}

# Words a title may always use, whatever the source text says.
GENERIC = {
    "truck", "semi", "spill", "spilled", "jam", "gridlock", "traffic", "on", "the", "of", "in",
    "and", "at", "great", "big", "day", "night", "rush", "hour", "pocalypse", "snowpocalypse",
    "icepocalypse", "carmageddon", "jamuary", "storm", "closure", "detour", "crawl", "standstill",
    "i-5", "i-405", "i-90", "sr-520", "sr-99", "520", "405", "90", "5", "99", "viaduct",
    "seattle", "bellevue", "tacoma", "everett", "lynnwood", "bothell", "renton", "kent",
    "redmond", "kirkland", "shoreline", "federal", "way", "mercer", "island", "evergreen",
    "point", "convention", "center", "northgate", "southcenter", "spaghetti", "bowl", "&", "*",
}

# Never on a badge: deaths and serious harm.
FATAL = re.compile(
    r"\b(fatal\w*|killed|kill|dies|died|dead|death\w*|deceased|medical examiner|coroner|"
    r"life[- ]threatening|critical(ly)? (condition|injur\w*)|serious(ly)? injur\w*|"
    r"major injur\w*|airlift\w*|shooting|shot|stabb\w*|homicide|suicide|"
    r"pedestrian (struck|hit)|struck by|body|remains)\b", re.I)

# Any injury at all: never auto-publish, wait for an explicit YES.
INJURY = re.compile(r"\b(injur\w*|hurt|hospital\w*|transported|ambulance|aid car|medics?)\b", re.I)

# Politics as a topic: ideology, offices, campaigns, slogans. Blocked outright.
POLITICAL = re.compile(
    r"\b(president\w*|presidency|administration|election\w*|vote[sd]?|voting|ballot|campaign|"
    r"democrat\w*|republican\w*|gop|maga|liberal\w*|conservative\w*|socialis\w*|communis\w*|"
    r"fascis\w*|congress\w*|senat\w*|governor|mayor|impeach\w*|protest\w*|riot\w*|"
    r"tariff\w*|deport\w*|abortion|woke)\b", re.I)

# Event categories (safety.py decides the tier from these, in this order of precedence):
#   conflict     -> BLOCK  (a gathering that turned violent is no longer celebrated)
#   officeholder -> BLOCK  (a politician's or dignitary's visit is not this project's story)
#   gathering    -> HOLD, and even when approved it publishes no earlier than the next morning
CONFLICT = re.compile(
    r"\b(riot\w*|clash\w*|loot\w*|tear gas|pepper spray|arrest\w*|vandal\w*|property damage|"
    r"unrest|violen\w*|smash\w*|set (a )?fire|fires set|molotov|dispers\w*)\b", re.I)
OFFICEHOLDER = re.compile(
    r"\b(motorcade|vip|dignitar\w*|secret service|campaign\w*|candidate\w*|president\w*|"
    r"vice president|senator\w*|congress\w*|governor|mayor|prime minister|head of state|"
    r"summit|official visit|state visit|delegation)\b", re.I)
GATHERING = re.compile(
    r"\b(march\w*|rally|rallies|protest\w*|demonstrat\w*|parade|walkout|vigil|strike|"
    r"celebrat\w*|crowds?)\b", re.I)

# Politicians: their name as the cause of a jam is an officeholder event -> BLOCK.
POLITICIANS = re.compile(
    r"\b(hillary|clinton|obama|trump|biden|harris|bush|sanders|vance|pelosi|inslee|ferguson|"
    r"murray|cantwell|jayapal|harrell)\b", re.I)
# Celebrities: a concert or appearance can be a fair hook, but needs your YES (and the
# name only if it is in the official text; otherwise it is treated as injected).
CELEBRITIES = re.compile(r"\b(pope|oprah|taylor swift|swift|beyonce|gates|bezos|musk)\b", re.I)

# Brands and companies: trademark risk, so explicit YES only.
BRANDS = re.compile(
    r"\b(amazon|microsoft|boeing|costco|starbucks|fedex|ups|usps|walmart|target|tesla|"
    r"nordstrom|rei|t-mobile|alaska airlines|seahawks|mariners|sounders|kraken|"
    r"huskies|coca[- ]cola|pepsi|budweiser|ikea|uber|lyft|waymo)\b", re.I)

PROFANITY = re.compile(r"\b(fuck\w*|shit\w*|damn\w*|hell|ass|bitch\w*|crap)\b", re.I)


def tokens(text):
    return re.findall(r"[a-z0-9&*\-]+", (text or "").lower())


def find_hook_words(text):
    return sorted({t for t in tokens(text) if t in HOOK_WORDS})
