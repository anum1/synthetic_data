"""Static reference data: product taxonomy, geography, carriers, name pools.

Nothing here is random. These are the fixed vocabularies the dimension
builders draw from, kept separate so the taxonomy can be reviewed and edited
without reading generation logic.

All brands, products, suppliers and place-names are invented.
"""
from __future__ import annotations

# ---------------------------------------------------------------------------
# Product taxonomy: 8 categories x 3 subcategories = 24 (dim_product_category)
# ---------------------------------------------------------------------------
TAXONOMY: dict[str, list[str]] = {
    "Industrial Components": ["Bearings", "Drive Belts", "Gearsets"],
    "Electronics":           ["Sensors", "Controllers", "Connectors"],
    "SmartHome":             ["Smart Hubs", "Smart Lighting", "Smart Climate"],
    "Power Systems":         ["Batteries", "Inverters", "Power Supplies"],
    "Fluid Control":         ["Valves", "Pumps", "Fittings"],
    "Fasteners & Hardware":  ["Bolts & Screws", "Clamps", "Brackets"],
    "Safety Equipment":      ["Protective Gear", "Guards & Shields", "Detection"],
    "Raw Materials":         ["Polymers", "Alloys", "Composites"],
}

# Which subcategories are physically manufactured (fact_production) rather than
# bought and resold. Drives product_type on dim_product.
MANUFACTURED = {
    "Gearsets", "Controllers", "Smart Hubs", "Smart Climate", "Inverters",
    "Pumps", "Valves", "Brackets", "Guards & Shields",
}
RAW_MATERIAL_CATEGORY = "Raw Materials"

BRANDS = [
    "Meridian", "Corvex", "Halcyon", "Nimbus", "Ferrum",
    "Voltaic", "Aeris", "Sentinel", "Keystone", "Lumen",
]

# Families that the events reference by name must exist here.
FAMILIES = {
    "SmartHome":   ["Aura", "Beacon", "Cortex", "Haven"],
    "Electronics": ["Nimbus", "Pulse", "Vertex"],
}
DEFAULT_FAMILIES = ["Standard", "Pro", "Heavy Duty", "Compact", "Extended"]

MATERIALS = [
    "Stainless Steel", "Carbon Steel", "Aluminium", "Brass", "ABS Polymer",
    "Polycarbonate", "Nylon 66", "Titanium Alloy", "Copper", "Silicone",
]

# ---------------------------------------------------------------------------
# Geography: 5 regions -> 15 countries
# ---------------------------------------------------------------------------
REGIONS = ["North America", "Europe", "APAC", "LATAM", "MEA"]

COUNTRIES: dict[str, list[str]] = {
    "North America": ["United States", "Canada", "Mexico"],
    "Europe":        ["Germany", "United Kingdom", "France", "Poland", "Netherlands"],
    "APAC":          ["China", "Vietnam", "Japan", "India", "Australia"],
    "LATAM":         ["Brazil", "Chile"],
    "MEA":           ["United Arab Emirates", "South Africa"],
}

# Sub-regions exist only for North America, because Event 4 (carrier
# degradation) is geographically concentrated in the Northeast and needs a
# level between country and location to be concentrated *in*.
US_SUB_REGIONS = ["Northeast", "Southeast", "Midwest", "Southwest", "West"]

# Distribution centres. (city, country, sub_region, node_type)
# Ordered so that a small tier taking the first N still spans every region.
LOCATIONS: list[tuple[str, str, str, str]] = [
    ("Newark",        "United States",        "Northeast", "DC"),
    ("Frankfurt",     "Germany",              "",          "DC"),
    ("Shanghai",      "China",                "",          "DC"),
    ("Sao Paulo",     "Brazil",               "",          "DC"),
    ("Dubai",         "United Arab Emirates", "",          "DC"),
    ("Atlanta",       "United States",        "Southeast", "DC"),
    ("Rotterdam",     "Netherlands",          "",          "Port Hub"),
    ("Ho Chi Minh",   "Vietnam",              "",          "Plant"),
    ("Dallas",        "United States",        "Southwest", "DC"),
    ("Manchester",    "United Kingdom",       "",          "DC"),
    ("Osaka",         "Japan",                "",          "DC"),
    ("Monterrey",     "Mexico",               "",          "Plant"),
    ("Chicago",       "United States",        "Midwest",   "DC"),
    ("Lyon",          "France",               "",          "DC"),
    ("Pune",          "India",                "",          "Plant"),
    ("Reno",          "United States",        "West",      "DC"),
    ("Toronto",       "Canada",               "",          "DC"),
    ("Sydney",        "Australia",            "",          "DC"),
    ("Wroclaw",       "Poland",               "",          "Plant"),
    ("Santiago",      "Chile",                "",          "DC"),
    ("Boston",        "United States",        "Northeast", "DC"),
    ("Hamburg",       "Germany",              "",          "Port Hub"),
    ("Shenzhen",      "China",                "",          "Plant"),
    ("Johannesburg",  "South Africa",         "",          "DC"),
    ("Philadelphia",  "United States",        "Northeast", "DC"),
    ("Birmingham",    "United Kingdom",       "",          "Plant"),
    ("Nagoya",        "Japan",                "",          "Plant"),
    ("Guadalajara",   "Mexico",               "",          "DC"),
    ("Columbus",      "United States",        "Midwest",   "DC"),
    ("Marseille",     "France",               "",          "Port Hub"),
    ("Chennai",       "India",                "",          "DC"),
    ("Salt Lake City","United States",        "West",      "DC"),
    ("Vancouver",     "Canada",               "",          "DC"),
    ("Melbourne",     "Australia",            "",          "DC"),
    ("Gdansk",        "Poland",               "",          "Port Hub"),
    ("Recife",        "Brazil",               "",          "DC"),
    ("Charlotte",     "United States",        "Southeast", "DC"),
    ("Eindhoven",     "Netherlands",          "",          "Plant"),
    ("Hanoi",         "Vietnam",              "",          "DC"),
    ("Abu Dhabi",     "United Arab Emirates", "",          "DC"),
]

# Event 12 opens this one mid-timeline; it is appended, never in the base list.
NEW_DC = ("Phoenix", "United States", "Southwest", "DC")

# ---------------------------------------------------------------------------
# Carriers. C-07 is the one Event 4 degrades; keep the code stable.
# ---------------------------------------------------------------------------
CARRIER_NAMES = [
    "Transglobal Freight", "Apex Logistics", "BlueLine Carriers", "Meridian Express",
    "Continental Haulage", "Pacific Route", "Northstar Transit", "Vector Freight",
    "Ironway Logistics", "Cascade Shipping", "Redwood Transport", "Summit Cargo",
    "Anchor Line", "Trailhead Freight", "Beacon Logistics", "Granite Haulage",
    "Skybridge Air", "Harbour Point", "Silverlane Transit", "Foxtrot Freight",
]
CARRIER_MODES = ["Road", "Ocean", "Air", "Rail", "Parcel"]

# ---------------------------------------------------------------------------
# Supplier naming. Event 1 and 5 pin SUP-104 and SUP-137, so supplier
# master ids are assigned as SUP-100 + index and those two must land in range.
# ---------------------------------------------------------------------------
SUPPLIER_STEMS = [
    "Acme Components", "Torvald Industrial", "Kestrel Manufacturing", "Orion Precision",
    "Baltic Metalworks", "Sunrise Polymers", "Ardent Fabrication", "Cobalt Systems",
    "Delta Forge", "Everline Plastics", "Fairmont Tooling", "Granite Alloys",
    "Highpoint Electronics", "Ivory Composites", "Juniper Circuits", "Kingsway Bearings",
    "Lakeshore Castings", "Monarch Valves", "Northwind Fasteners", "Oakridge Sensors",
    "Pinnacle Drives", "Quarry Materials", "Redstone Assembly", "Silverpeak Motors",
    "Tidewater Supply", "Umbra Optics", "Vanguard Machining", "Westfield Rubber",
    "Yellowstone Steel", "Zenith Controls", "Alder Instruments", "Brightwater Chemicals",
    "Cedarline Extrusion", "Dunmore Hardware", "Eastgate Components", "Foundry Nine",
    "Glenrock Industrial", "Harborview Plastics", "Inlet Manufacturing", "Jadestone Alloys",
]
SUPPLIER_SUFFIXES = ["Inc.", "Ltd", "LLC", "GmbH", "Co.", "S.A.", "Pte Ltd", "AB"]

# Deliberate dirt (baseline.data_quality.supplier_name_variant_count).
# Applied to the *display* name only; supplier_master_id stays clean, so the
# same dataset supports both the broken view and the corrected one.
NAME_VARIANT_RULES = [
    lambda s: s.upper(),
    lambda s: s.replace(".", ""),
    lambda s: s.replace("Inc.", "Incorporated").replace("Ltd", "Limited"),
    lambda s: s + " ",
    lambda s: s.replace(" ", "  "),
    lambda s: s.rstrip(".").replace("Components", "Comp."),
]

PAYMENT_TERMS = ["Net 30", "Net 45", "Net 60", "2/10 Net 30"]
SUPPLIER_TIERS = ["Strategic", "Preferred", "Approved", "At Risk"]

# ---------------------------------------------------------------------------
# Customers
# ---------------------------------------------------------------------------
CUSTOMER_PREFIXES = [
    "Alpine", "Bayside", "Crestwood", "Dockside", "Eastvale", "Fielding",
    "Greenhill", "Hartley", "Ingram", "Jasper", "Kirkwood", "Langley",
    "Maplewood", "Norfolk", "Oakmont", "Prescott", "Quinton", "Ridgefield",
    "Stonebridge", "Thornton", "Underwood", "Vernon", "Whitfield", "Yorkshire",
]
CUSTOMER_SUFFIXES = [
    "Manufacturing", "Industries", "Group", "Holdings", "Systems", "Partners",
    "Engineering", "Distribution", "Technologies", "Works",
]
CUSTOMER_SEGMENTS = ["Enterprise", "Mid-Market", "SMB", "Distributor", "OEM"]

# ---------------------------------------------------------------------------
# Employees (planners and buyers). Event 15 attributes overrides to planners.
# ---------------------------------------------------------------------------
EMPLOYEE_ROLES = ["Demand Planner", "Supply Planner", "Buyer",
                  "Category Manager", "Logistics Coordinator"]
FIRST_NAMES = [
    "Avery", "Blake", "Casey", "Devon", "Emerson", "Finley", "Gray", "Harper",
    "Indigo", "Jordan", "Kai", "Logan", "Morgan", "Noel", "Oakley", "Parker",
    "Quinn", "Reese", "Sawyer", "Tatum", "Umber", "Vale", "Wren", "Xen",
]
LAST_NAMES = [
    "Adeyemi", "Bergstrom", "Castellanos", "Duong", "Eriksen", "Fontaine",
    "Gallagher", "Hoffman", "Iwata", "Jankowski", "Kowalczyk", "Lindqvist",
    "Moreau", "Nakamura", "Okonkwo", "Petrov", "Quintero", "Rasmussen",
    "Santoro", "Tremblay", "Ueda", "Villanueva", "Weaver", "Zhang",
]


def flat_taxonomy() -> list[tuple[str, str]]:
    """[(category, subcategory)] in stable order."""
    return [(c, s) for c, subs in TAXONOMY.items() for s in subs]


def country_region_map() -> dict[str, str]:
    return {c: r for r, cs in COUNTRIES.items() for c in cs}
