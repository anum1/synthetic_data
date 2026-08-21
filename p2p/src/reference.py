"""Name and hierarchy pools.

Everything here is invented. No real company, person, brand or tax identifier
appears anywhere in this dataset, which is what makes it safe to put on a
screen in front of a customer - the same rule the ApexTech, Meridian, GlobalTech
and Vantage siblings follow.

The top ~60 suppliers get hand-written names, because those are the rows that
actually appear on screen in a demo and syllable-generated names look like
syllable-generated names. The long tail is built combinatorially.
"""
from __future__ import annotations

import numpy as np

# -----------------------------------------------------------------------------
# Procurement hierarchy: segment -> family -> category.
#
# Both direct and indirect spend. Indirect-only caps credible total spend at
# around $60M, which will not carry a $284.6M headline (PLAN 3).
# -----------------------------------------------------------------------------
HIERARCHY: dict[str, dict[str, list[str]]] = {
    "Direct Materials": {
        "Raw Materials": ["Steel and Alloys", "Aluminium Stock", "Polymers and Resins",
                          "Industrial Glass"],
        "Components": ["Bearings and Drives", "Fasteners", "Electronic Components",
                       "Hydraulic Assemblies", "Castings and Forgings"],
        "Packaging": ["Corrugate", "Films and Wraps", "Labels and Print", "Pallets"],
        "Process Chemicals": ["Solvents", "Lubricants", "Coatings and Finishes"],
    },
    "IT": {
        "Hardware": ["End User Compute", "Servers and Storage", "Peripherals",
                     "Mobile Devices"],
        "Software": ["Enterprise Applications", "Cloud Subscriptions",
                     "Security Software", "Developer Tooling"],
        "Network": ["Network Infrastructure", "Telecommunications", "Connectivity"],
        "IT Services": ["Managed Services", "Implementation Services",
                        "Application Support", "Data Centre Services"],
    },
    "Facilities": {
        "Maintenance": ["Building Maintenance", "HVAC and Plant", "Grounds"],
        "Security": ["Guarding Services", "Access Control", "Monitoring"],
        "Cleaning": ["Janitorial", "Specialist Cleaning", "Waste Management"],
        "Utilities": ["Electricity", "Gas and Fuel", "Water and Sewerage"],
    },
    "Professional Services": {
        "Consulting": ["Strategy Consulting", "Technology Consulting",
                       "Operations Consulting"],
        "Legal": ["Corporate Legal", "Litigation Support", "IP and Trademarks"],
        "Finance and Audit": ["External Audit", "Tax Advisory", "Actuarial Services"],
        "Marketing": ["Agency Services", "Media Buying", "Market Research",
                      "Events and Sponsorship"],
        "HR Services": ["Contingent Labour", "Recruitment", "Training and Development"],
    },
    "Travel": {
        "Air Travel": ["Domestic Airfare", "International Airfare"],
        "Lodging": ["Hotels", "Extended Stay"],
        "Ground Transportation": ["Car Rental", "Rail", "Ride Hail and Taxi"],
        "Meals and Entertainment": ["Client Entertainment", "Per Diem"],
    },
    "Logistics": {
        "Freight": ["Ocean Freight", "Air Freight", "Road Freight", "Parcel"],
        "Warehousing": ["Third Party Warehousing", "Cold Storage"],
        "Trade Services": ["Customs Brokerage", "Duties and Tariffs"],
    },
}

# Subcategories are generated from these, so the leaf level reaches ~340 rows
# without 340 lines of hand-typed noun phrases.
SUBCATEGORY_MODIFIERS = [
    "Standard", "Premium", "Contracted", "Spot Buy", "Renewal", "New Build",
    "Emergency", "Bulk", "Custom", "Refurbished", "Regional", "Global Framework",
]

# -----------------------------------------------------------------------------
# Suppliers
# -----------------------------------------------------------------------------
HERO_SUPPLIER_ROOTS = [
    "Northbeam", "Caldera", "Vireo", "Halcyon", "Ironbark", "Stellaris", "Marlowe",
    "Quarrytown", "Alderwood", "Bright Harbor", "Kestrel", "Pinnacle Reach",
    "Copperline", "Silvercrest", "Ravenswood", "Blackfen", "Windermere", "Ashgrove",
    "Cobalt Ridge", "Fairmount", "Greystone", "Harborview", "Juniper Bay", "Larkspur",
    "Meridian Falls", "Norwell", "Oakhurst", "Palisade", "Redstone", "Sableworth",
    "Thornfield", "Umbra", "Verdant", "Westmarch", "Yarrow", "Zephyr Point",
    "Amberlin", "Brookvale", "Clearwater Rise", "Dunmore", "Eastgate", "Fernhollow",
    "Glenview", "Hawthorne Park", "Inverleith", "Jasperfield", "Kingsmere",
    "Lockridge", "Morrowind", "Netherby", "Ostley", "Pemberton", "Quillon",
    "Rosemoor", "Stonebridge", "Tarnwick", "Uplands", "Vantage Point", "Wexford",
    "Yardley",
]

SUPPLIER_FORMS = [
    "Technologies", "Industrial", "Systems", "Group", "Partners", "Solutions",
    "Supply Co", "Manufacturing", "Services", "Logistics", "Labs", "Holdings",
    "Associates", "Enterprises",
]

# Syllables for the long tail. Deliberately bland - these rows exist to make the
# supplier count real, not to be read out loud.
_SYL_A = ["Bar", "Cal", "Dor", "Fen", "Gar", "Hal", "Jor", "Kel", "Lam", "Mor",
          "Nor", "Ost", "Pel", "Quin", "Ran", "Sel", "Tor", "Vel", "Wen", "Zar",
          "Ald", "Bren", "Cort", "Drav", "Elm", "Fald", "Gren", "Hurst"]
_SYL_B = ["ton", "mere", "wick", "field", "dale", "ford", "worth", "stead",
          "holm", "gate", "bury", "combe", "ridge", "haven", "port", "shaw"]

SUPPLIER_COUNTRIES = [
    ("US", 0.44), ("DE", 0.09), ("GB", 0.08), ("CN", 0.07), ("NL", 0.05),
    ("CA", 0.05), ("MX", 0.04), ("FR", 0.04), ("IN", 0.04), ("SG", 0.03),
    ("JP", 0.03), ("PL", 0.02), ("IT", 0.02),
]

COUNTRY_CURRENCY = {"US": "USD", "CA": "CAD", "MX": "MXN", "GB": "GBP", "DE": "EUR",
                    "NL": "EUR", "FR": "EUR", "IT": "EUR", "PL": "EUR",
                    "CN": "USD", "IN": "USD", "SG": "SGD", "JP": "JPY"}

CITIES = {
    "US": ["Akron", "Boise", "Charlotte", "Dayton", "Everett", "Fresno", "Gary",
           "Hartford", "Irving", "Joliet", "Kenosha", "Lansing"],
    "CA": ["Barrie", "Calgary", "Guelph", "Halifax", "Kingston"],
    "MX": ["Celaya", "Irapuato", "Monclova", "Saltillo", "Toluca"],
    "GB": ["Basildon", "Coventry", "Derby", "Halifax", "Preston"],
    "DE": ["Bielefeld", "Chemnitz", "Duisburg", "Erfurt", "Fuerth"],
    "NL": ["Almere", "Breda", "Deventer", "Ede", "Zwolle"],
    "FR": ["Amiens", "Besancon", "Caen", "Dijon", "Metz"],
    "IT": ["Bergamo", "Cremona", "Ferrara", "Latina", "Novara"],
    "PL": ["Bydgoszcz", "Gliwice", "Kielce", "Radom", "Torun"],
    "CN": ["Changzhou", "Foshan", "Huizhou", "Jinhua", "Weifang"],
    "IN": ["Coimbatore", "Indore", "Nashik", "Rajkot", "Vadodara"],
    "SG": ["Jurong", "Tuas", "Woodlands"],
    "JP": ["Hamamatsu", "Kurashiki", "Toyota", "Utsunomiya"],
}

STREETS = ["Ackland Way", "Bellows Road", "Cranmer Street", "Dunbar Lane",
           "Elmsworth Drive", "Fairhaven Road", "Gladwin Street", "Hollis Avenue",
           "Ingram Way", "Jarrow Road", "Keswick Lane", "Ludlow Street",
           "Marchmont Road", "Nately Way", "Oxburgh Lane", "Pentworth Street"]

# -----------------------------------------------------------------------------
# People
# -----------------------------------------------------------------------------
FIRST_NAMES = [
    "Aaron", "Adele", "Ainsley", "Alan", "Alicia", "Amara", "Andre", "Anita",
    "Arjun", "Beatriz", "Bella", "Bram", "Callum", "Camila", "Carsten", "Cecile",
    "Charles", "Chloe", "Dara", "Deepa", "Diego", "Dmitri", "Edith", "Elena",
    "Elias", "Emeka", "Esther", "Fabian", "Farida", "Fionn", "Gabriel", "Georgia",
    "Gustav", "Hana", "Harriet", "Hugo", "Ibrahim", "Imogen", "Ines", "Isaac",
    "Jae", "Janelle", "Jasper", "Jonas", "Josephine", "Kaito", "Karim", "Katya",
    "Keiko", "Kwame", "Laila", "Lars", "Leon", "Lucia", "Magnus", "Malik",
    "Marisol", "Mateo", "Maya", "Niamh", "Nikolai", "Nora", "Olamide", "Oliver",
    "Paloma", "Pavel", "Priya", "Rafael", "Ravi", "Rhys", "Rosa", "Sanne",
    "Sasha", "Selina", "Simone", "Soren", "Tariq", "Tessa", "Theo", "Ursula",
    "Valentina", "Viktor", "Wren", "Xander", "Yusuf", "Zara", "Zeynep",
]

LAST_NAMES = [
    "Abadi", "Ashworth", "Bakker", "Beaumont", "Bhandari", "Calderon", "Castellan",
    "Chan", "Cortese", "Dahl", "Delacroix", "Doyle", "Eriksen", "Falconer",
    "Ferreira", "Gallagher", "Ghosh", "Grimaldi", "Halvorsen", "Hammersley",
    "Ibarra", "Ikeda", "Jansen", "Kaur", "Keating", "Kowalski", "Laurent",
    "Lindqvist", "Maguire", "Marchetti", "Mbeki", "Moreau", "Nakamura", "Novak",
    "Okonkwo", "Oyelaran", "Pahlavi", "Petrov", "Quintero", "Rahman", "Ramirez",
    "Rossi", "Sandoval", "Schneider", "Sorensen", "Stavros", "Takahashi", "Thackeray",
    "Ulmer", "Vance", "Varga", "Villanueva", "Wainwright", "Whitlock", "Xiang",
    "Yilmaz", "Zabala", "Zielinski",
]

DEPARTMENT_NAMES = [
    "Manufacturing Operations", "Plant Engineering", "Quality Assurance",
    "Supply Chain Planning", "Logistics", "Warehouse Operations", "Procurement",
    "Information Technology", "Enterprise Applications", "Infrastructure and Cloud",
    "Information Security", "Data and Analytics", "Finance", "Financial Planning",
    "Treasury", "Internal Audit", "Tax", "Accounts Payable", "Human Resources",
    "Talent Acquisition", "Learning and Development", "Legal", "Compliance",
    "Corporate Communications", "Marketing", "Field Marketing", "Product Management",
    "Research and Development", "Facilities Management", "Real Estate",
    "Environment Health and Safety", "Customer Support", "Field Service",
    "Sales Operations", "Commercial Excellence", "Strategy", "Corporate Development",
    "Investor Relations", "Executive Office", "Shared Services",
]

# Item nouns per family, so an item name reads as something you could buy.
ITEM_NOUNS = {
    "Raw Materials": ["Coil", "Billet", "Sheet", "Rod", "Ingot", "Granulate"],
    "Components": ["Bearing", "Gearset", "Fastener Kit", "Actuator", "Sensor",
                   "Coupling", "Valve"],
    "Packaging": ["Carton", "Film Roll", "Label Reel", "Pallet", "Insert"],
    "Process Chemicals": ["Solvent Drum", "Lubricant Pail", "Coating Batch"],
    "Hardware": ["Laptop", "Workstation", "Monitor", "Server Blade", "Array Shelf",
                 "Docking Station", "Handset"],
    "Software": ["Licence", "Subscription", "Support Plan", "Module"],
    "Network": ["Switch", "Router", "Access Point", "Transceiver", "Circuit"],
    "IT Services": ["Engagement", "Support Block", "Migration Package"],
    "Maintenance": ["Service Visit", "Repair Kit", "Inspection"],
    "Security": ["Guard Shift", "Reader Unit", "Monitoring Plan"],
    "Cleaning": ["Service Period", "Deep Clean", "Waste Collection"],
    "Utilities": ["Supply Period", "Meter Charge"],
    "Consulting": ["Workstream", "Assessment", "Advisory Block"],
    "Legal": ["Matter", "Retainer Period", "Filing"],
    "Finance and Audit": ["Audit Phase", "Advisory Note", "Valuation"],
    "Marketing": ["Campaign", "Placement", "Study", "Event Package"],
    "HR Services": ["Placement", "Contract Week", "Course Seat"],
    "Air Travel": ["Ticket", "Fare Class Block"],
    "Lodging": ["Room Night", "Stay Package"],
    "Ground Transportation": ["Rental Day", "Rail Ticket", "Trip"],
    "Meals and Entertainment": ["Covers", "Hospitality Package"],
    "Freight": ["Container Move", "Shipment", "Lane Charge", "Parcel Block"],
    "Warehousing": ["Pallet Month", "Handling Block"],
    "Trade Services": ["Entry", "Declaration"],
}

HOLD_REASONS = [
    ("PRICE_VAR", "Invoice price above PO price beyond tolerance", "Procurement", 1),
    ("QTY_VAR", "Invoiced quantity above received quantity", "Receiving", 1),
    ("AMT_VAR", "Invoice total above PO total beyond tolerance", "Procurement", 1),
    ("NO_RECEIPT", "No goods receipt recorded against the PO line", "Receiving", 1),
    ("NO_PO", "PO referenced on the invoice does not exist", "AP Operations", 1),
    ("PO_CLOSED", "PO is closed or fully consumed", "Procurement", 1),
    ("DUP_SUSPECT", "Suspected duplicate of an existing invoice", "AP Operations", 1),
    ("TAX_VAR", "Tax amount inconsistent with the tax code", "Tax", 1),
    ("COST_CENTER", "Cost centre missing or invalid", "AP Operations", 1),
    ("GL_CODING", "GL account missing on a non-PO invoice", "AP Operations", 1),
    ("BUDGET", "Cost centre budget exhausted for the period", "FP&A", 1),
    ("BANK_MISSING", "Supplier has no active remit-to bank account", "Supplier Master", 1),
    ("SUPPLIER_BLOCK", "Supplier is blocked or inactive", "Supplier Master", 1),
    ("TAX_ID_MISSING", "Supplier tax identifier missing", "Supplier Master", 0),
    ("CONTRACT_EXP", "Contract expired before the invoice date", "Procurement", 0),
    ("APPROVAL_PEND", "Awaiting cost centre owner approval", "AP Operations", 1),
    ("FX_VAR", "Exchange rate differs from the PO rate", "Treasury", 0),
    ("EARLY_INVOICE", "Invoice dated before the goods receipt", "Receiving", 1),
    ("QUALITY_HOLD", "Quality rejection recorded against the receipt", "Quality", 1),
    ("FREIGHT_VAR", "Freight charge not on the PO", "Procurement", 0),
    ("REMIT_MISMATCH", "Remit-to address differs from supplier master", "Supplier Master", 1),
    ("MANUAL_REVIEW", "Held for manual review by AP", "AP Operations", 1),
]

GL_ACCOUNT_BLOCKS = [
    (5000, "Cost of Goods Sold", ["Raw Materials", "Components", "Packaging",
                                 "Process Chemicals"]),
    (6100, "IT Expense", ["Hardware", "Software", "Network", "IT Services"]),
    (6200, "Facilities Expense", ["Maintenance", "Security", "Cleaning", "Utilities"]),
    (6300, "Professional Fees", ["Consulting", "Legal", "Finance and Audit",
                                 "Marketing", "HR Services"]),
    (6400, "Travel and Entertainment", ["Air Travel", "Lodging",
                                        "Ground Transportation",
                                        "Meals and Entertainment"]),
    (6500, "Distribution Expense", ["Freight", "Warehousing", "Trade Services"]),
]


def build_supplier_names(n: int, rng: np.random.Generator) -> list[str]:
    """`n` distinct invented supplier legal names, best ones first.

    Order matters: suppliers are ranked by spend downstream, so the hand-written
    names land on the rows that actually appear on a dashboard.
    """
    names: list[str] = []
    seen: set[str] = set()

    for root in HERO_SUPPLIER_ROOTS:
        form = SUPPLIER_FORMS[rng.integers(0, len(SUPPLIER_FORMS))]
        nm = f"{root} {form}"
        if nm not in seen:
            seen.add(nm)
            names.append(nm)
        if len(names) >= n:
            return names[:n]

    # Long tail: syllable roots x forms, drawn without replacement.
    tail_roots = [a + b for a in _SYL_A for b in _SYL_B]
    rng.shuffle(tail_roots)
    for root in tail_roots:
        for form in SUPPLIER_FORMS:
            nm = f"{root} {form}"
            if nm in seen:
                continue
            seen.add(nm)
            names.append(nm)
            if len(names) >= n:
                return names[:n]
    raise ValueError(f"name pool exhausted at {len(names)} of {n}")


def build_person_names(n: int, rng: np.random.Generator) -> list[tuple[str, str]]:
    """`n` distinct (first, last) pairs."""
    pairs: list[tuple[str, str]] = []
    seen: set[tuple[str, str]] = set()
    guard = 0
    while len(pairs) < n and guard < n * 60:
        guard += 1
        f = FIRST_NAMES[rng.integers(0, len(FIRST_NAMES))]
        l = LAST_NAMES[rng.integers(0, len(LAST_NAMES))]
        if (f, l) in seen:
            continue
        seen.add((f, l))
        pairs.append((f, l))
    # Fall back to a numbered middle initial if the pool runs dry.
    i = 0
    while len(pairs) < n:
        f = FIRST_NAMES[i % len(FIRST_NAMES)]
        l = LAST_NAMES[(i // len(FIRST_NAMES)) % len(LAST_NAMES)]
        pairs.append((f"{f} {chr(65 + i % 26)}.", l))
        i += 1
    return pairs


def normalize_name(name: str) -> str:
    """Strip punctuation, corporate forms and spacing.

    This is the join key the supplier-duplication story turns on: `Northbeam
    Technologies`, `Northbeam Tech Corp.` and `N.B. Technologies` collapse to
    something comparable. Deliberately imperfect - a perfect normaliser would
    make the demo question trivial.
    """
    out = name.upper()
    for ch in ".,-&'/()":
        out = out.replace(ch, " ")
    drop = {"INC", "LLC", "LTD", "LIMITED", "CORP", "CORPORATION", "CO", "COMPANY",
            "GMBH", "BV", "SA", "AG", "PLC", "PTE", "PTY", "SRL", "SPA", "AB",
            "GROUP", "HOLDINGS", "THE"}
    tokens = [t for t in out.split() if t and t not in drop]
    return " ".join(tokens)
