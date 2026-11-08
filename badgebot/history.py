"""The history set: retro badges for events that already happened, from the Historical Badges
running list. They are drawn from scenes (hand-tuned) or the icon library, and go on sale
together, quietly: no posts, no list email, one summary email to you.

Not here yet: the 2019 snowstorm (needs a new name). Cut: Galloping Gertie.
LAUNCH is the first set to go on sale; the rest wait for better art (a sketch or a scene).
"""

LAUNCH = {"SHIP CANAL SQUEEZE", "MADISON ST.", "520", "WEST SEATTLE BRIDGE", "CRABPOCALYPSE",
          "HONEY - DON'T", "SNOWPOCALYPSE", "THUNDER SNOW", "RECORD 20-INCH SNOW"}

HISTORY = [
    # title, year, the story line for the listing, art ("scene" or "icon", key)
    ("SHIP CANAL SQUEEZE", 2025, "Summer 2025: northbound I-5 squeezed to two lanes on the Ship Canal Bridge for four weeks.", ("scene", "ship_canal")),
    ("MADISON ST.", "2021-2024", "2021 to 2024: Madison Street torn up to build the RapidRide G Line.", ("scene", "madison_closed")),
    ("520", "2024-2032", "2024 to about 2032: the SR 520 Portage Bay Bridge rebuild.", ("scene", "sr520_construction")),
    ("WEST SEATTLE BRIDGE", 2020, "March 23, 2020: the West Seattle Bridge closed for about 908 days after it cracked.", ("scene", "west_seattle")),
    ("VIADOOM", 2019, "January 2019: the Alaskan Way Viaduct closed for good, and three weeks with no SR 99.", ("scene", "viadoom")),
    ("RUFFLED FEATHERS", 2018, "May 23, 2018: about 40,000 pounds of chicken feathers spilled across I-5.", ("icon", "truck")),
    ("CRABPOCALYPSE", 2016, "April 4, 2016: frozen crab spilled across the northbound Viaduct.", ("icon", "crab")),
    ("HONEY - DON'T", 2015, "April 17, 2015: a semi carrying beehives overturned at I-5 and I-405.", ("icon", "bee_truck")),
    ("FISHY FRACAS", 2015, "March 24, 2015: a fish truck rolled on the southbound Viaduct and closed it for nine hours.", ("icon", "truck")),
    ("BERTHA GOT STUCK", 2013, "December 6, 2013: the SR 99 tunnel machine stopped, and stayed stuck for about two years.", ("icon", "cone")),
    ("SNOWPOCALYPSE", 2008, "December 2008: the storm that buried Seattle for days.", ("scene", "snowpocalypse")),
    ("THUNDER SNOW", 2002, "March 8, 2002: snow, hail and lightning all at once.", ("scene", "thunder_snow")),
    ("I-90 BRIDGE", 1990, "November 25, 1990: the old I-90 floating bridge sank.", ("scene", "i90_bridge")),
    ("HOOD CANAL", 1979, "February 13, 1979: the Hood Canal Bridge's western half sank in a windstorm.", ("scene", "hood_canal")),
    ("SPOKANE ST.", 1978, "June 11, 1978: a freighter hit the Spokane Street drawbridge and left it stuck open.", ("icon", "bridge")),
    ("RECORD 20-INCH SNOW", 1950, "January 13, 1950: 20 inches of snow in one day, the Sea-Tac record.", ("scene", "snowpocalypse")),
]
