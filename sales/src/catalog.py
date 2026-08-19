"""Fictional ApexTech product taxonomy and pricing bands.

Hierarchy:  Category > Subcategory > Brand > Product Family > Product > SKU
All brands are invented; nothing here maps to a real-world trademark.
"""

# category -> subcategory -> [(brand, product_family, model_prefix, n_models,
#                              price_low, price_high, margin_pct)]
TAXONOMY = {
    "Electronics": {
        "Laptops": [
            ("Nimbus", "Nimbus Air", "N", 4, 1099, 1699, 0.24),
            ("Nimbus", "Nimbus Pro", "P", 3, 1999, 3499, 0.27),
            ("Vertex", "Vertex Studio", "VS", 3, 2499, 4599, 0.29),
            ("Vertex", "Vertex Field", "VF", 3, 1799, 2899, 0.25),
            ("Orbit", "Orbit Book", "OB", 4, 549, 1099, 0.17),
            ("Orbit", "Orbit Flex", "OF", 3, 799, 1499, 0.19),
        ],
        "Desktops": [
            ("Monolith", "Monolith Tower", "MT", 3, 1499, 4999, 0.26),
            ("Monolith", "Monolith Workstation", "MW", 3, 3299, 8999, 0.28),
            ("Cube", "Cube Mini", "CM", 3, 699, 1899, 0.22),
            ("Cube", "Cube Studio", "CS", 3, 1199, 2799, 0.24),
        ],
        "Tablets": [
            ("Slate", "Slate Go", "SG", 3, 429, 899, 0.20),
            ("Slate", "Slate Pro", "SP", 3, 999, 1799, 0.25),
            ("Slate", "Slate Mini", "SM", 3, 329, 649, 0.18),
        ],
        "Smartphones": [
            ("Pulse", "Pulse One", "PO", 4, 649, 1099, 0.21),
            ("Pulse", "Pulse Ultra", "PU", 3, 1099, 1699, 0.24),
            ("Pulse", "Pulse Lite", "PL", 3, 329, 649, 0.16),
        ],
        "Displays": [
            ("Lumen", "Lumen View", "LV", 3, 299, 899, 0.19),
            ("Lumen", "Lumen Studio", "LS", 3, 1099, 2499, 0.26),
            ("Lumen", "Lumen Ultrawide", "LU", 3, 749, 1899, 0.23),
        ],
        "Audio": [
            ("Sonora", "Sonora Buds", "SB", 3, 129, 329, 0.31),
            ("Sonora", "Sonora Studio", "SS", 2, 349, 699, 0.33),
            ("Sonora", "Sonora Bar", "SR", 2, 299, 899, 0.29),
        ],
        "Wearables": [
            ("Chrono", "Chrono Watch", "CW", 4, 249, 799, 0.30),
            ("Chrono", "Chrono Band", "CB", 3, 79, 229, 0.34),
        ],
        "Cameras": [
            ("Aperture", "Aperture Cam", "AP", 3, 549, 2299, 0.22),
            ("Aperture", "Aperture Web", "AB", 3, 89, 349, 0.32),
        ],
    },
    "Peripherals": {
        "Input Devices": [
            ("Tactus", "Tactus Keyboard", "TK", 3, 79, 249, 0.35),
            ("Tactus", "Tactus Pointer", "TP", 3, 49, 179, 0.37),
            ("Tactus", "Tactus Pad", "TD", 2, 99, 299, 0.33),
        ],
        "Docks & Hubs": [
            ("Nexus", "Nexus Dock", "ND", 3, 149, 499, 0.34),
            ("Nexus", "Nexus Hub", "NH", 3, 59, 199, 0.36),
        ],
        "Storage": [
            ("Vault", "Vault SSD", "VD", 4, 119, 899, 0.28),
            ("Vault", "Vault NAS", "VN", 3, 599, 2499, 0.25),
            ("Vault", "Vault Drive", "VR", 3, 79, 399, 0.24),
        ],
        "Cables & Adapters": [
            ("Conduit", "Conduit Connect", "CC", 4, 19, 89, 0.45),
            ("Conduit", "Conduit Power", "CP", 3, 29, 129, 0.42),
        ],
        "Printing": [
            ("Quill", "Quill Printer", "QP", 3, 199, 1299, 0.21),
            ("Quill", "Quill Scanner", "QS", 2, 149, 649, 0.26),
        ],
    },
    "Networking": {
        "Routers": [
            ("Beacon", "Beacon Router", "BR", 3, 179, 749, 0.30),
            ("Beacon", "Beacon Mesh", "BM", 3, 249, 899, 0.32),
        ],
        "Switches": [
            ("Relay", "Relay Switch", "RS", 3, 299, 1899, 0.28),
            ("Relay", "Relay Core", "RC", 3, 1499, 6999, 0.31),
        ],
        "Wireless Access": [
            ("Halo", "Halo Access", "HA", 3, 199, 699, 0.32),
            ("Halo", "Halo Bridge", "HB", 2, 349, 999, 0.30),
        ],
        "Security Appliances": [
            ("Bastion", "Bastion Firewall", "BF", 3, 899, 4999, 0.34),
            ("Bastion", "Bastion Gateway", "BG", 2, 599, 2299, 0.33),
        ],
    },
    "Components": {
        "Memory": [
            ("Cortex", "Cortex Memory", "CX", 4, 89, 649, 0.23),
            ("Cortex", "Cortex Server Memory", "CE", 3, 249, 1899, 0.21),
        ],
        "Processors": [
            ("Helix", "Helix Processor", "HX", 4, 249, 1799, 0.20),
            ("Helix", "Helix Server", "HS", 3, 899, 4999, 0.22),
        ],
        "Graphics": [
            ("Prism", "Prism Graphics", "PR", 4, 399, 2299, 0.18),
            ("Prism", "Prism Compute", "PM", 3, 1899, 7999, 0.24),
        ],
        "Power": [
            ("Dynamo", "Dynamo Power", "DP", 3, 89, 399, 0.26),
            ("Dynamo", "Dynamo UPS", "DU", 3, 199, 1499, 0.28),
        ],
        "Cooling": [
            ("Zephyr", "Zephyr Cooler", "ZC", 3, 49, 249, 0.33),
            ("Zephyr", "Zephyr Liquid", "ZL", 2, 149, 549, 0.30),
        ],
        "Boards": [
            ("Lattice", "Lattice Board", "LB", 3, 149, 699, 0.22),
            ("Lattice", "Lattice Server Board", "LR", 2, 599, 2499, 0.24),
        ],
    },
    "Software & Services": {
        "Productivity": [
            ("ApexWorks", "ApexWorks Suite", "AW", 3, 199, 899, 0.72),
            ("ApexWorks", "ApexWorks Collab", "AK", 2, 149, 599, 0.74),
        ],
        "Security": [
            ("Aegis", "Aegis Endpoint", "AE", 3, 149, 1199, 0.75),
            ("Aegis", "Aegis Cloud", "AG", 2, 299, 1899, 0.73),
        ],
        "Support Plans": [
            ("ApexCare", "ApexCare Plan", "AC", 3, 99, 899, 0.68),
            ("ApexCare", "ApexCare Premier", "AR", 2, 499, 2499, 0.70),
        ],
        "Cloud Services": [
            ("Stratus", "Stratus Platform", "ST", 3, 299, 2999, 0.66),
            ("Stratus", "Stratus Analytics", "SA", 2, 599, 3999, 0.69),
        ],
        "Analytics": [
            ("Insight", "Insight Suite", "IS", 3, 399, 2999, 0.71),
        ],
        "Developer Tools": [
            ("Forge", "Forge Studio", "FS", 3, 149, 999, 0.76),
        ],
    },
}

# SKU-level variants per subcategory: (suffix, label, price multiplier)
VARIANTS = {
    "Laptops": [("13-256", '13" / 256GB', 1.00), ("13-512", '13" / 512GB', 1.14),
                ("15-512", '15" / 512GB', 1.22), ("15-1TB", '15" / 1TB', 1.38)],
    "Desktops": [("BASE", "Base", 1.00), ("MID", "Mid", 1.25), ("MAX", "Max", 1.65)],
    "Tablets": [("64", "64GB", 1.00), ("256", "256GB", 1.18), ("512", "512GB", 1.34)],
    "Smartphones": [("128", "128GB", 1.00), ("256", "256GB", 1.12), ("512", "512GB", 1.26)],
    "Displays": [("27", '27"', 1.00), ("32", '32"', 1.30)],
    "Audio": [("STD", "Standard", 1.00), ("ANC", "Noise Cancelling", 1.22)],
    "Storage": [("1TB", "1TB", 1.00), ("2TB", "2TB", 1.55), ("4TB", "4TB", 2.30)],
    "Memory": [("16", "16GB", 1.00), ("32", "32GB", 1.70), ("64", "64GB", 2.90)],
    "Graphics": [("8", "8GB", 1.00), ("16", "16GB", 1.45)],
    "Processors": [("STD", "Standard", 1.00), ("OC", "Overclocked", 1.30)],
    "Productivity": [("1YR", "1 Year", 1.00), ("3YR", "3 Year", 2.60)],
    "Security": [("1YR", "1 Year", 1.00), ("3YR", "3 Year", 2.60)],
    "Support Plans": [("STD", "Standard", 1.00), ("PREM", "Premium", 1.85)],
    "Cloud Services": [("STARTER", "Starter", 1.00), ("BUSINESS", "Business", 2.20),
                       ("ENTERPRISE", "Enterprise", 4.50)],
    "Wearables": [("38", "38mm", 1.00), ("42", "42mm", 1.15), ("46", "46mm", 1.32)],
    "Cameras": [("BODY", "Body Only", 1.00), ("KIT", "Kit", 1.45)],
    "Printing": [("STD", "Standard", 1.00), ("DUPLEX", "Duplex", 1.28),
                 ("NET", "Network", 1.52)],
    "Security Appliances": [("SM", "Small Office", 1.00), ("MD", "Mid-Market", 1.90),
                            ("LG", "Enterprise", 3.40)],
    "Cooling": [("AIR", "Air", 1.00), ("PRO", "Pro", 1.40)],
    "Boards": [("STD", "Standard", 1.00), ("PLUS", "Plus", 1.35), ("MAX", "Max", 1.75)],
    "Analytics": [("1YR", "1 Year", 1.00), ("3YR", "3 Year", 2.60)],
    "Developer Tools": [("SEAT", "Per Seat", 1.00), ("TEAM", "Team", 3.20)],
    "Docks & Hubs": [("STD", "Standard", 1.00), ("PD", "Power Delivery", 1.30),
                     ("TB", "Thunderbolt", 1.75)],
    "Input Devices": [("STD", "Standard", 1.00), ("WL", "Wireless", 1.25),
                      ("MECH", "Mechanical", 1.60)],
    "Routers": [("AX", "Wi-Fi 6", 1.00), ("BE", "Wi-Fi 7", 1.45)],
    "Switches": [("8P", "8-Port", 1.00), ("24P", "24-Port", 1.85), ("48P", "48-Port", 3.10)],
    "Wireless Access": [("IN", "Indoor", 1.00), ("OUT", "Outdoor", 1.40)],
    "Power": [("450W", "450W", 1.00), ("750W", "750W", 1.40), ("1000W", "1000W", 1.85)],
    "Cables & Adapters": [("1M", "1m", 1.00), ("2M", "2m", 1.25), ("3M", "3m", 1.45)],
}
DEFAULT_VARIANTS = [("STD", "Standard", 1.00), ("PLUS", "Plus", 1.35)]

# Colors used only as SKU flavour text on hardware.
COLORS = ["Graphite", "Silver", "Midnight", "Arctic", "Sage"]

SUPPLIER_GROUPS = [
    "Global Components",      # referenced by the supplier cost shock event
    "Pacific Manufacturing",
    "Atlas Industrial",
    "Meridian Supply Co",
    "Northwind Materials",
    "Cascade Electronics",
    "Ironforge Assembly",
]

PROMOTION_TEMPLATES = [
    ("Spring Sale", "Seasonal", "Discount", 0.12, "Email"),
    ("Back to School", "Seasonal", "Discount", 0.15, "Digital Ads"),
    ("Black Friday", "Seasonal", "Deep Discount", 0.28, "Multi-Channel"),
    ("Cyber Week", "Seasonal", "Deep Discount", 0.25, "Digital Ads"),
    ("Holiday Bundle", "Seasonal", "Bundle", 0.18, "Retail"),
    ("Clearance", "Inventory", "Deep Discount", 0.35, "Online"),
    ("New Product Launch", "Product", "Introductory Offer", 0.08, "Multi-Channel"),
    ("Enterprise Contract", "Contract", "Volume Discount", 0.20, "Direct Sales"),
    ("Partner Rebate", "Channel", "Rebate", 0.10, "Partner Portal"),
    ("Loyalty Reward", "Retention", "Loyalty", 0.07, "Email"),
    ("Trade-In Offer", "Product", "Trade-In", 0.14, "Retail"),
    ("Volume Tier Incentive", "Contract", "Volume Discount", 0.16, "Direct Sales"),
]

RETURN_REASONS = {
    "Damaged": "Logistics",
    "Wrong Product": "Fulfillment",
    "Customer Changed Mind": "Customer",
    "Late Delivery": "Logistics",
    "Product Defect": "Quality",
    "Duplicate Order": "Fulfillment",
    "Not As Described": "Customer",
    "Better Price Elsewhere": "Customer",
}

INDUSTRIES = ["Technology", "Healthcare", "Manufacturing", "Financial Services",
              "Retail", "Public Sector", "Education", "Energy",
              "Telecommunications", "Professional Services"]

CUSTOMER_SEGMENTS = ["Enterprise", "Mid-Market", "SMB", "Consumer"]
CUSTOMER_TIERS = ["Strategic", "Standard", "Growth", "Emerging"]
