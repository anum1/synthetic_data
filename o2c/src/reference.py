"""Static reference pools: geography, taxonomies, name banks.

Everything here is invented. No real trademark appears anywhere in this file,
which is what makes the dataset safe to put on a screen in front of a customer.
The sibling datasets' companies (ApexTech, Meridian Global, GlobalTech) are
deliberately not reused as customer names either, so the four demos never look
like they are describing the same world.
"""
from __future__ import annotations

# --------------------------------------------------------------------------
# Geography.  Region -> country -> states/provinces.
# `business_unit` is the internal reporting split, and it is what Events 5 and
# 15 are scoped to: invoicing is run by business unit, not by sales region.
# --------------------------------------------------------------------------
GEOGRAPHY = {
    "NA": {
        "United States": ["California", "Texas", "Illinois", "Ohio", "Pennsylvania",
                          "Michigan", "Georgia", "North Carolina", "New York",
                          "Washington", "Louisiana", "Alabama", "Indiana", "Wisconsin",
                          "Tennessee", "Missouri", "Arizona", "Minnesota"],
        "Canada": ["Ontario", "Quebec", "Alberta", "British Columbia", "Manitoba",
                   "Saskatchewan"],
        "Mexico": ["Nuevo Leon", "Jalisco", "Estado de Mexico", "Coahuila", "Sonora"],
    },
    "EMEA": {
        "United Kingdom": ["England", "Scotland", "Wales", "Northern Ireland"],
        "Germany": ["Bayern", "Nordrhein-Westfalen", "Baden-Wurttemberg",
                    "Niedersachsen", "Hessen", "Sachsen"],
        "France": ["Ile-de-France", "Auvergne-Rhone-Alpes", "Hauts-de-France",
                   "Grand Est", "Occitanie"],
        "Netherlands": ["Zuid-Holland", "Noord-Brabant", "Gelderland"],
        "Italy": ["Lombardia", "Veneto", "Piemonte", "Emilia-Romagna"],
        "Spain": ["Cataluna", "Madrid", "Andalucia", "Pais Vasco"],
        "Poland": ["Mazowieckie", "Slaskie", "Wielkopolskie"],
        "United Arab Emirates": ["Abu Dhabi", "Dubai", "Sharjah"],
        "Saudi Arabia": ["Eastern Province", "Riyadh", "Makkah"],
        "South Africa": ["Gauteng", "KwaZulu-Natal", "Western Cape"],
    },
    "APAC": {
        "Japan": ["Kanto", "Kansai", "Chubu", "Kyushu"],
        "Australia": ["New South Wales", "Victoria", "Queensland",
                      "Western Australia"],
        "Singapore": ["Central", "West", "North"],
        "India": ["Maharashtra", "Gujarat", "Tamil Nadu", "Karnataka", "Haryana"],
        "China": ["Guangdong", "Jiangsu", "Shandong", "Zhejiang"],
        "South Korea": ["Gyeonggi", "Ulsan", "Busan"],
    },
    "LATAM": {
        "Brazil": ["Sao Paulo", "Minas Gerais", "Rio de Janeiro", "Parana"],
        "Chile": ["Antofagasta", "Santiago", "Biobio"],
        "Colombia": ["Antioquia", "Bogota", "Valle del Cauca"],
        "Argentina": ["Buenos Aires", "Cordoba", "Santa Fe"],
        "Peru": ["Lima", "Arequipa", "Cusco"],
    },
}

# Country -> transacting currency. Everything is also carried in USD.
COUNTRY_CURRENCY = {
    "United States": "USD", "Canada": "CAD", "Mexico": "MXN",
    "United Kingdom": "GBP", "Germany": "EUR", "France": "EUR",
    "Netherlands": "EUR", "Italy": "EUR", "Spain": "EUR", "Poland": "EUR",
    "United Arab Emirates": "USD", "Saudi Arabia": "USD", "South Africa": "USD",
    "Japan": "JPY", "Australia": "AUD", "Singapore": "SGD", "India": "USD",
    "China": "USD", "South Korea": "USD",
    "Brazil": "USD", "Chile": "USD", "Colombia": "USD", "Argentina": "USD",
    "Peru": "USD",
}

# US states split East / Central / West; everything else is Export. This is the
# billing organisation, and Events 5 and 15 are scoped to it.
US_BUSINESS_UNIT = {
    "California": "West", "Washington": "West", "Arizona": "West",
    "Texas": "Central", "Illinois": "Central", "Ohio": "Central",
    "Michigan": "Central", "Indiana": "Central", "Wisconsin": "Central",
    "Missouri": "Central", "Minnesota": "Central", "Louisiana": "Central",
    "Pennsylvania": "East", "Georgia": "East", "North Carolina": "East",
    "New York": "East", "Alabama": "East", "Tennessee": "East",
}


def business_unit(country: str, state: str) -> str:
    if country == "United States":
        return US_BUSINESS_UNIT.get(state, "East")
    if country in ("Canada", "Mexico"):
        return "West" if state in ("British Columbia", "Alberta", "Sonora",
                                   "Jalisco") else "Central"
    return "Export"


# --------------------------------------------------------------------------
# Customer taxonomy
# --------------------------------------------------------------------------
SEGMENTS = ["Strategic", "Enterprise", "Mid-Market", "Small Business"]
SEGMENT_MIX = [0.04, 0.16, 0.34, 0.46]

INDUSTRIES = ["Manufacturing", "Oil & Gas", "Utilities", "Mining",
              "Food & Beverage", "Automotive", "Chemicals", "Pharmaceuticals",
              "Construction", "Aerospace", "Pulp & Paper", "Marine",
              "Metals & Steel", "Cement & Aggregates"]

CHANNELS = ["Direct Sales", "Distributor", "E-Commerce", "EDI", "Inside Sales"]
CHANNEL_MIX = [0.44, 0.21, 0.12, 0.15, 0.08]

SITE_TYPES = ["Plant", "Warehouse", "Distribution Center", "Head Office",
              "Service Depot", "Mine Site", "Refinery"]

# Customer names are built as prefix + suffix, with a locality inserted when a
# collision needs breaking. Nothing here is a real company.
NAME_PREFIX = [
    "Ironclad", "Redstone", "Northbridge", "Kestrel", "Granite Peak", "Copperline",
    "Blackwater", "Silverton", "Highfield", "Cobalt", "Foundry", "Anvil",
    "Bluewater", "Steelhaven", "Westgate", "Pinnacle Ridge", "Ridgeline",
    "Quarry Hill", "Cinder", "Basalt", "Tunstall", "Harrow", "Larkspur",
    "Mercer", "Oakfield", "Penrose", "Quarryman", "Ravenswood", "Sable",
    "Thornton", "Underhill", "Vellum", "Wrenfield", "Yardley", "Zephyr",
    "Ambervale", "Brightwater", "Caldwell", "Dunmore", "Elmridge", "Fairhaven",
    "Glenmark", "Hollowbrook", "Inglewood", "Junction", "Kingsmill", "Loxley",
    "Marbury", "Norwood", "Ostend", "Pemberton", "Quillfield", "Rothbury",
    "Stonegate", "Truro", "Upton", "Valemount", "Whitlock", "Yarrow",
]
NAME_SUFFIX = [
    "Industrial", "Manufacturing", "Engineering", "Fabrication", "Systems",
    "Works", "Industries", "Technologies", "Group", "Holdings", "Partners",
    "Equipment", "Machinery", "Components", "Processing", "Refining",
    "Resources", "Materials", "Assembly", "Precision", "Dynamics", "Solutions",
]
LEGAL_FORM = {"United States": "Inc.", "Canada": "Ltd.", "Mexico": "S.A. de C.V.",
              "United Kingdom": "Ltd.", "Germany": "GmbH", "France": "S.A.",
              "Netherlands": "B.V.", "Italy": "S.p.A.", "Spain": "S.L.",
              "Poland": "Sp. z o.o.", "United Arab Emirates": "LLC",
              "Saudi Arabia": "LLC", "South Africa": "(Pty) Ltd",
              "Japan": "K.K.", "Australia": "Pty Ltd", "Singapore": "Pte Ltd",
              "India": "Pvt Ltd", "China": "Co., Ltd", "South Korea": "Co., Ltd",
              "Brazil": "Ltda.", "Chile": "SpA", "Colombia": "S.A.S.",
              "Argentina": "S.A.", "Peru": "S.A.C."}

# --------------------------------------------------------------------------
# Product taxonomy: Category -> Family -> (line count, price tier)
# "Hydraulic Pumps" carries Event 8; "Electrical & Automation" carries Event 12.
# --------------------------------------------------------------------------
PRODUCT_TAXONOMY = {
    "Power Transmission": {
        "Gearboxes": 4, "Belts & Chains": 3, "Couplings": 3, "Electric Motors": 4,
    },
    "Fluid Handling": {
        "Hydraulic Pumps": 4, "Valves": 4, "Hoses & Fittings": 3, "Filtration": 3,
    },
    "Electrical & Automation": {
        "Drives & Inverters": 3, "Sensors": 4, "Controllers": 3,
        "Cable & Connectors": 3,
    },
    "Material Handling": {
        "Conveyor Components": 4, "Hoists & Cranes": 3, "Casters & Wheels": 2,
    },
    "Bearings & Seals": {
        "Ball Bearings": 3, "Roller Bearings": 3, "Seals & Gaskets": 3,
    },
    "Safety & PPE": {
        "Protective Equipment": 3, "Lockout Tagout": 2, "Fall Protection": 2,
    },
    "Tools & Consumables": {
        "Hand Tools": 3, "Power Tools": 3, "Abrasives": 2, "Lubricants": 3,
    },
    "HVAC & Refrigeration": {
        "Compressors": 3, "Heat Exchangers": 2, "Fans & Blowers": 3,
    },
}

LINE_QUALIFIER = ["Standard", "Heavy Duty", "Premium", "Compact", "High Flow",
                  "Corrosion Resistant", "Explosion Proof", "Economy",
                  "Precision", "Extended Life"]

UOM = ["EA", "BOX", "CASE", "SET", "PAIR", "ROLL", "DRUM", "PALLET"]

# Product families that are made to order rather than stocked. These carry
# longer lead times and are where backorders concentrate naturally.
MADE_TO_ORDER_FAMILIES = {"Gearboxes", "Heat Exchangers", "Hoists & Cranes"}

# --------------------------------------------------------------------------
# Carriers. "Meridian Freight" carries Event 4.
# --------------------------------------------------------------------------
CARRIER_NAMES = [
    "Continental Express", "Meridian Freight", "Northstar Logistics",
    "Vector Transport", "Atlas Cargo", "Blue Ridge Carriers",
    "Pacific Rim Shipping", "Eurolink Freight", "Summit Parcel",
    "Ironwood Haulage",
]
SERVICE_LEVELS = [
    # name, transit multiplier, cost multiplier, is_expedited
    ("Ground", 1.00, 1.00, 0),
    ("Two-Day", 0.55, 1.85, 1),
    ("Overnight", 0.28, 3.40, 1),
    ("Freight LTL", 1.25, 0.82, 0),
    ("Freight FTL", 1.05, 1.15, 0),
    ("Ocean", 3.20, 0.45, 0),
    ("Air Freight", 0.45, 2.60, 1),
]

DELIVERY_EVENT_TYPES = ["Label Created", "Picked Up", "In Transit",
                        "Out for Delivery", "Delivered"]
EXCEPTION_CODES = ["WEATHER", "MECHANICAL", "CUSTOMS", "ADDRESS", "CAPACITY",
                   "MISSORT", "RECIPIENT", "DAMAGE"]

# --------------------------------------------------------------------------
# Payment terms. `due_days` drives the invoice due date; the discount pair
# drives the early-payment behaviour in collections.py.
# --------------------------------------------------------------------------
PAYMENT_TERMS = [
    # code, name, due_days, discount_pct, discount_days, weight
    ("DOR",     "Due on Receipt",  0,  0.00,  0, 0.05),
    ("COD",     "Cash on Delivery", 0, 0.00,  0, 0.02),
    ("PREPAY",  "Prepaid",        -5,  0.02,  0, 0.02),
    ("N15",     "Net 15",         15,  0.00,  0, 0.09),
    ("N30",     "Net 30",         30,  0.00,  0, 0.32),
    ("2N30",    "2/10 Net 30",    30,  0.02, 10, 0.13),
    ("N45",     "Net 45",         45,  0.00,  0, 0.15),
    ("1N45",    "1/15 Net 45",    45,  0.01, 15, 0.06),
    ("N60",     "Net 60",         60,  0.00,  0, 0.10),
    ("N75",     "Net 75",         75,  0.00,  0, 0.02),
    ("N90",     "Net 90",         90,  0.00,  0, 0.03),
    ("N120",    "Net 120",       120,  0.00,  0, 0.01),
]

PAYMENT_METHODS = ["ACH", "Wire Transfer", "Check", "Credit Card",
                   "Direct Debit", "Lockbox"]
PAYMENT_METHOD_MIX = [0.34, 0.22, 0.18, 0.09, 0.10, 0.07]

SHIPPING_PRIORITY = ["Standard", "High", "Critical"]
SHIPPING_PRIORITY_MIX = [0.78, 0.17, 0.05]

LOST_REASONS = ["Price", "Lead Time", "Competitor Incumbent", "No Budget",
                "Specification Mismatch", "Payment Terms", "No Decision",
                "Credit Declined"]
LOST_REASON_MIX = [0.31, 0.17, 0.16, 0.12, 0.09, 0.06, 0.06, 0.03]

DISPUTE_OWNERS = ["AR Collections", "Billing", "Sales Operations",
                  "Customer Service", "Credit"]

RESOLUTION_CODES = ["Credit Issued", "Customer Withdrew", "Price Corrected",
                    "Goods Replaced", "Partial Credit", "Escalated to Legal",
                    "Written Off"]

RETURN_REASONS = ["Damaged in Transit", "Wrong Item Shipped", "Ordered in Error",
                  "Quality Defect", "Late Delivery Refused", "Overstock Return",
                  "Specification Mismatch"]

# First and last names for sales reps and dispute owners.
FIRST_NAMES = [
    "Alan", "Priya", "Marcus", "Elena", "Tomas", "Aisha", "Derek", "Yuki",
    "Rowan", "Ingrid", "Hassan", "Bianca", "Callum", "Mei", "Diego", "Fiona",
    "Gustav", "Hana", "Isaac", "Jolene", "Karim", "Lena", "Mateo", "Nadia",
    "Oscar", "Petra", "Quentin", "Rosa", "Sven", "Tanvi", "Ulrich", "Vera",
    "Wesley", "Ximena", "Yusuf", "Zara", "Bridget", "Cormac", "Delphine",
    "Emeka", "Freya", "Gideon", "Helena", "Idris", "Juliet", "Kenji", "Liam",
    "Marisol", "Niamh", "Otto", "Paloma", "Rafael", "Sofia", "Thandeka",
]
LAST_NAMES = [
    "Okafor", "Lindqvist", "Marchetti", "Delacroix", "Ferreira", "Nakamura",
    "Whitfield", "Abernathy", "Kowalski", "Petrov", "Salazar", "Thornbury",
    "Vasquez", "Oyelaran", "Brennan", "Castellanos", "Dubois", "Eriksen",
    "Falconer", "Gallagher", "Halvorsen", "Ivanov", "Jansen", "Kaur",
    "Lindgren", "Moreau", "Nkemdirim", "Ortega", "Pereira", "Quintero",
    "Rasmussen", "Sorensen", "Tanaka", "Ueda", "Villanueva", "Wexford",
    "Yamamoto", "Zieliński", "Adeyemi", "Bergstrom", "Chaudhry", "Donnelly",
    "Espinosa", "Fitzgerald", "Grimaldi", "Haugen", "Ishikawa", "Jovanovic",
]

# Warehouse city pool, paired with a region on assignment.
WAREHOUSE_CITIES = {
    "NA": ["Columbus", "Dallas", "Reno", "Atlanta", "Chicago", "Memphis",
           "Toronto", "Monterrey", "Phoenix", "Newark", "Seattle", "Kansas City"],
    "EMEA": ["Rotterdam", "Duisburg", "Birmingham", "Lyon", "Milan", "Katowice",
             "Dubai", "Johannesburg", "Zaragoza"],
    "APAC": ["Osaka", "Sydney", "Singapore", "Pune", "Shenzhen", "Busan"],
    "LATAM": ["Sao Paulo", "Santiago", "Bogota", "Buenos Aires"],
}
