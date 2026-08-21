"""Reference catalogs: name pools, geography, organization and job taxonomy.

Everything here is invented. Company, division, team and job names are made up;
personal names are drawn from ordinary given-name and surname pools chosen to
match the employee's country, so the data looks like a real HR extract without
being one. Emails use the reserved `.example` TLD, which can never resolve.
"""
from __future__ import annotations

import numpy as np

# -----------------------------------------------------------------------------
# Name pools, keyed by the name culture used for each country.
# -----------------------------------------------------------------------------
FIRST_NAMES = {
    "anglo": [
        "James", "Emma", "Michael", "Olivia", "William", "Ava", "Benjamin", "Sophia",
        "Daniel", "Isabella", "Matthew", "Mia", "Andrew", "Charlotte", "Joseph",
        "Amelia", "David", "Harper", "Ryan", "Evelyn", "Nathan", "Abigail", "Ethan",
        "Grace", "Christopher", "Chloe", "Alexander", "Zoe", "Samuel", "Lily",
        "Thomas", "Hannah", "Jonathan", "Layla", "Patrick", "Nora", "Kevin", "Ruby",
        "Brandon", "Alice", "Marcus", "Claire", "Derek", "Vivian", "Trevor", "Naomi",
        "Curtis", "Paula", "Roland", "Beatrice",
    ],
    "german": [
        "Lukas", "Hannah", "Felix", "Lena", "Jonas", "Marie", "Elias", "Sophie",
        "Maximilian", "Emilia", "Leon", "Clara", "Paul", "Johanna", "Moritz",
        "Frieda", "Tobias", "Greta", "Sebastian", "Ingrid", "Kilian", "Annika",
        "Matthias", "Birgit", "Stefan", "Katrin", "Dietrich", "Helga", "Andreas",
        "Ursula", "Rainer", "Sabine", "Bernd", "Petra", "Jurgen", "Monika",
        "Wolfgang", "Heike", "Klaus", "Ute",
    ],
    "indian": [
        "Arjun", "Priya", "Rohan", "Ananya", "Vikram", "Kavya", "Aditya", "Sneha",
        "Karthik", "Divya", "Rahul", "Meera", "Sanjay", "Pooja", "Nikhil", "Ishita",
        "Ravi", "Neha", "Amit", "Shreya", "Manish", "Aarti", "Suresh", "Lakshmi",
        "Deepak", "Sunita", "Praveen", "Rekha", "Ashwin", "Tara", "Varun", "Nisha",
        "Harsha", "Gayatri", "Naveen", "Swati", "Rajesh", "Anjali", "Kiran", "Bhavna",
    ],
    "japanese": [
        "Haruto", "Yui", "Sota", "Aoi", "Ren", "Rin", "Yuto", "Hina", "Riku", "Sakura",
        "Kaito", "Mei", "Takumi", "Nanami", "Daiki", "Akari", "Kenji", "Yuka",
        "Shota", "Miho", "Hiroshi", "Keiko", "Naoki", "Ayumi", "Tatsuya", "Chiaki",
        "Masaru", "Emi", "Yusuke", "Saki", "Ichiro", "Kaori", "Toshio", "Nao",
        "Satoshi", "Mizuki", "Osamu", "Fumiko", "Genji", "Harumi",
    ],
}

LAST_NAMES = {
    "anglo": [
        "Anderson", "Bennett", "Carter", "Donovan", "Ellery", "Fairbanks", "Grantham",
        "Hollis", "Ingram", "Jarvis", "Kendrick", "Lockwood", "Marsden", "Norwood",
        "Oakley", "Prescott", "Quinlan", "Radcliffe", "Sterling", "Thatcher",
        "Underhill", "Vance", "Whitfield", "Yardley", "Ashcombe", "Braddock",
        "Chadwick", "Denholm", "Eastwood", "Fenwick", "Garrity", "Hawthorne",
        "Ivester", "Kelsall", "Langford", "Merritt", "Northcott", "Pemberton",
        "Ridgway", "Selwyn",
    ],
    "german": [
        "Bergmann", "Dreher", "Eichhorn", "Faber", "Gerlach", "Hoffmann", "Kastner",
        "Lindner", "Muhlbauer", "Nussbaum", "Ostermann", "Pfeiffer", "Reinhardt",
        "Schuster", "Thalberg", "Vogler", "Wendland", "Zimmerer", "Brandt",
        "Cordes", "Dittmar", "Engelhardt", "Fromm", "Grunewald", "Hartwig",
        "Kleinschmidt", "Lehmann", "Marquardt", "Neuhaus", "Rothfuss", "Sauerbrey",
        "Tillmann", "Ulmer", "Wiegand", "Zeller", "Baumgartner", "Freitag",
        "Hellwig", "Kranz", "Riedel",
    ],
    "indian": [
        "Iyer", "Nair", "Reddy", "Sharma", "Verma", "Chandra", "Deshpande", "Gokhale",
        "Kulkarni", "Malhotra", "Narayanan", "Pillai", "Raghavan", "Sundaram",
        "Varadarajan", "Bhatia", "Chauhan", "Dixit", "Ganguly", "Hegde", "Joshi",
        "Kamath", "Menon", "Oberoi", "Padmanabhan", "Rastogi", "Sabharwal",
        "Trivedi", "Venkatesh", "Bhandari", "Chakraborty", "Dhawan", "Grover",
        "Krishnan", "Mahadevan", "Purohit", "Sridhar", "Thakur", "Vaidya", "Wadhwa",
    ],
    "japanese": [
        "Takahashi", "Kobayashi", "Nakamura", "Yamashita", "Hasegawa", "Fujimoto",
        "Ishikawa", "Morimoto", "Okazaki", "Sugiyama", "Tachibana", "Uehara",
        "Watanabe", "Yoshimura", "Arakawa", "Chiba", "Nishimura", "Kawaguchi",
        "Maruyama", "Sakamoto", "Tamura", "Uchida", "Hirano", "Kadokawa",
        "Miyazaki", "Nagasawa", "Onodera", "Shimada", "Tsukamoto", "Yanagida",
        "Fukuda", "Horikawa", "Kurosawa", "Matsuda", "Nomura", "Ogawa", "Sasaki",
        "Terada", "Yamagishi", "Zaizen",
    ],
}

COUNTRY_NAME_CULTURE = {
    "US": "anglo", "Canada": "anglo", "UK": "anglo",
    "Germany": "german", "India": "indian", "Japan": "japanese",
}

COUNTRY_REGION = {
    "US": "North America", "Canada": "North America",
    "UK": "EMEA", "Germany": "EMEA",
    "India": "APAC", "Japan": "APAC",
}

COUNTRY_ISO = {"US": "USA", "Canada": "CAN", "UK": "GBR",
               "Germany": "DEU", "India": "IND", "Japan": "JPN"}

# -----------------------------------------------------------------------------
# Geography. (city, state/region, weight, is_hub)
# -----------------------------------------------------------------------------
CITIES = {
    "US": [("Dallas", "TX", 0.16, 1), ("Austin", "TX", 0.13, 1),
           ("San Jose", "CA", 0.12, 1), ("Seattle", "WA", 0.10, 1),
           ("Denver", "CO", 0.08, 0), ("Chicago", "IL", 0.08, 0),
           ("Atlanta", "GA", 0.07, 0), ("Boston", "MA", 0.07, 0),
           ("New York", "NY", 0.07, 1), ("Raleigh", "NC", 0.05, 0),
           ("Phoenix", "AZ", 0.04, 0), ("Columbus", "OH", 0.03, 0)],
    "Canada": [("Toronto", "ON", 0.42, 1), ("Vancouver", "BC", 0.26, 0),
               ("Montreal", "QC", 0.20, 0), ("Ottawa", "ON", 0.12, 0)],
    "UK": [("London", "England", 0.48, 1), ("Manchester", "England", 0.20, 0),
           ("Edinburgh", "Scotland", 0.14, 0), ("Bristol", "England", 0.11, 0),
           ("Belfast", "Northern Ireland", 0.07, 0)],
    "Germany": [("Munich", "Bavaria", 0.36, 1), ("Berlin", "Berlin", 0.28, 1),
                ("Frankfurt", "Hesse", 0.18, 0), ("Hamburg", "Hamburg", 0.10, 0),
                ("Cologne", "North Rhine-Westphalia", 0.08, 0)],
    "India": [("Bangalore", "Karnataka", 0.44, 1), ("Hyderabad", "Telangana", 0.22, 1),
              ("Pune", "Maharashtra", 0.16, 0), ("Chennai", "Tamil Nadu", 0.10, 0),
              ("Gurugram", "Haryana", 0.08, 0)],
    "Japan": [("Tokyo", "Kanto", 0.58, 1), ("Osaka", "Kansai", 0.22, 0),
              ("Yokohama", "Kanto", 0.12, 0), ("Fukuoka", "Kyushu", 0.08, 0)],
}

SITE_TYPES = ["Headquarters", "Engineering Center", "Sales Office",
              "Operations Center", "Shared Services", "Remote Hub"]

# -----------------------------------------------------------------------------
# Organization taxonomy.
#
# The hierarchy is FUNCTION-based, not geography-based: geography lives on
# dim_location. The design note nested country inside the org tree, which
# multiplies every function by every country and produces thousands of near-empty
# supervisory orgs. Workday does not model it that way and neither does this.
#
#   L1 Company -> L2 Business Unit -> L3 Function -> L4 Division
#              -> L5 Department -> L6 Team
# -----------------------------------------------------------------------------
BUSINESS_UNITS = {
    "Technology & Product": ["Engineering", "IT"],
    "Go-to-Market": ["Sales", "Marketing", "Customer Success"],
    "Corporate": ["Operations", "Finance", "HR", "Legal"],
}

DIVISIONS = {
    "Engineering": ["Cloud Platform", "Product Engineering", "Data & AI",
                    "Security Engineering", "Quality Engineering"],
    "IT": ["Enterprise Applications", "IT Infrastructure"],
    "Sales": ["Enterprise Sales", "Commercial Sales", "Sales Operations",
              "Partner & Channel"],
    "Marketing": ["Brand & Creative", "Growth Marketing", "Field Marketing"],
    "Customer Success": ["Customer Support", "Professional Services",
                         "Renewals & Retention"],
    "Operations": ["Business Operations", "Workplace Services",
                   "Global Procurement"],
    "Finance": ["Controllership", "Financial Planning", "Treasury & Tax"],
    "HR": ["Talent Acquisition", "People Operations"],
    "Legal": ["Corporate Legal", "Compliance & Privacy"],
}

DEPARTMENTS = {
    # Engineering - the divisions the planted events reach into
    "Cloud Platform": ["Compute Services", "Storage Services", "Platform Services",
                       "Site Reliability"],
    "Data & AI": ["Data Engineering", "Data Infrastructure", "Machine Learning",
                  "Analytics Engineering"],
    "Product Engineering": ["Core Product", "Mobile Engineering",
                            "Integrations", "Developer Experience"],
    "Security Engineering": ["Application Security", "Security Operations"],
    "Quality Engineering": ["Test Automation", "Release Engineering"],
    "Enterprise Applications": ["ERP Systems", "Workplace Technology"],
    "IT Infrastructure": ["Network Services", "End User Computing"],
    "Enterprise Sales": ["Strategic Accounts", "Named Accounts", "Public Sector"],
    "Commercial Sales": ["Mid-Market", "SMB", "Inside Sales"],
    "Sales Operations": ["Deal Desk", "Revenue Operations"],
    "Partner & Channel": ["Channel Sales", "Alliances"],
    "Brand & Creative": ["Brand Studio", "Content Marketing"],
    "Growth Marketing": ["Campaign Operations", "Lifecycle Marketing"],
    "Field Marketing": ["Regional Marketing", "Events"],
    "Customer Support": ["Tier 1 Support", "Tier 2 Support", "Support Engineering"],
    "Professional Services": ["Implementation", "Solution Architecture"],
    "Renewals & Retention": ["Renewals", "Customer Advocacy"],
    "Business Operations": ["Strategy & Planning", "Process Excellence"],
    "Workplace Services": ["Facilities", "Real Estate"],
    "Global Procurement": ["Sourcing", "Vendor Management"],
    "Controllership": ["General Accounting", "Revenue Accounting", "Payroll Finance"],
    "Financial Planning": ["Corporate FP&A", "Business Unit FP&A"],
    "Treasury & Tax": ["Treasury", "Tax"],
    "Talent Acquisition": ["Technical Recruiting", "GTM Recruiting"],
    "People Operations": ["HR Business Partners", "Total Rewards",
                          "People Analytics"],
    "Corporate Legal": ["Commercial Legal", "Employment Legal"],
    "Compliance & Privacy": ["Compliance", "Privacy Office"],
}

# Divisions created by the Marketing reorganisation (Event 8). They do not exist
# before the reorg month, which is what makes the hierarchy-history demo work.
REORG_DIVISIONS = {
    "Product Marketing": ["Core Product Marketing", "Competitive Intelligence"],
    "Demand Generation": ["Campaign Management", "Marketing Operations"],
    "Corporate Communications": ["Internal Communications", "Public Relations"],
}

TEAM_SUFFIXES = ["Alpha", "Bravo", "Charlie", "Delta", "Echo", "Foxtrot", "Gamma",
                 "Horizon", "Ignite", "Juniper", "Kestrel", "Lumen", "Meridian",
                 "Nova", "Orion", "Pinnacle", "Quartz", "Ridge", "Summit", "Titan",
                 "Vertex", "Willow", "Zenith", "Beacon", "Cobalt", "Drift"]

# -----------------------------------------------------------------------------
# Job taxonomy: function -> job family -> subfamilies.
# -----------------------------------------------------------------------------
JOB_FAMILIES = {
    "Engineering": {
        "Software Engineering": ["Backend", "Frontend", "Full Stack", "Mobile",
                                 "Distributed Systems"],
        "Site Reliability": ["SRE", "Infrastructure Engineering"],
        "Data Engineering": ["Data Pipelines", "Data Platform", "Analytics Engineering"],
        "Machine Learning": ["ML Engineering", "Applied Science"],
        "Security Engineering": ["Application Security", "Security Operations"],
        "Quality Engineering": ["Test Engineering", "Release Engineering"],
        "Engineering Management": ["Software Engineering Management",
                                   "Platform Engineering Management"],
    },
    "IT": {
        "IT Operations": ["Systems Administration", "Network Engineering",
                          "End User Support"],
        "Enterprise Systems": ["ERP Analysis", "Business Systems"],
    },
    "Sales": {
        "Account Executive": ["Enterprise AE", "Mid-Market AE", "SMB AE"],
        "Sales Engineering": ["Solutions Engineering", "Technical Account Management"],
        "Sales Development": ["Outbound SDR", "Inbound BDR"],
        "Sales Operations": ["Deal Desk", "Revenue Operations", "Sales Compensation"],
        "Channel Sales": ["Partner Management", "Alliances"],
        "Sales Management": ["Regional Sales Management", "Sales Leadership"],
    },
    "Marketing": {
        "Product Marketing": ["Product Marketing", "Competitive Intelligence"],
        "Demand Generation": ["Campaign Management", "Marketing Operations"],
        "Brand & Content": ["Content Strategy", "Creative Design",
                            "Corporate Communications"],
        "Field Marketing": ["Regional Marketing", "Event Marketing"],
    },
    "Customer Success": {
        "Customer Support": ["Technical Support", "Support Operations"],
        "Customer Success Management": ["Enterprise CSM", "Commercial CSM"],
        "Professional Services": ["Implementation Consulting", "Solution Architecture"],
    },
    "Operations": {
        "Business Operations": ["Strategy & Planning", "Process Excellence",
                                "Program Management"],
        "Procurement": ["Sourcing", "Vendor Management"],
        "Workplace": ["Facilities Management", "Workplace Experience"],
    },
    "Finance": {
        "Accounting": ["General Accounting", "Revenue Accounting", "Payroll Accounting"],
        "Financial Planning & Analysis": ["Corporate FP&A", "Business Partner FP&A"],
        "Treasury & Tax": ["Treasury Operations", "Tax Compliance"],
    },
    "HR": {
        "Talent Acquisition": ["Technical Recruiting", "GTM Recruiting",
                               "Recruiting Operations"],
        "HR Business Partner": ["HR Business Partner", "Employee Relations"],
        "Total Rewards": ["Compensation", "Benefits"],
        "People Analytics": ["Workforce Analytics", "HR Systems"],
    },
    "Legal": {
        "Legal Counsel": ["Commercial Legal", "Employment Legal", "Corporate Legal"],
        "Compliance": ["Regulatory Compliance", "Privacy"],
    },
}

# Career track and title prefix by job level. IC and management ladders overlap
# between L4 and L7, which is what makes compa-ratio comparisons interesting.
LEVEL_TRACKS = {
    "L1": [("Individual Contributor", "Associate ")],
    "L2": [("Individual Contributor", "")],
    "L3": [("Individual Contributor", "Senior ")],
    "L4": [("Individual Contributor", "Staff "), ("Manager", "Manager, ")],
    "L5": [("Individual Contributor", "Senior Staff "), ("Manager", "Senior Manager, ")],
    "L6": [("Individual Contributor", "Principal "), ("Director", "Director, ")],
    "L7": [("Individual Contributor", "Distinguished "), ("Director", "Senior Director, ")],
    "L8": [("Executive", "Vice President, ")],
    "L9": [("Executive", "Senior Vice President, ")],
}

# Market premium applied to the level midpoint for a job family. This is what
# makes "salary by job family" a real question rather than a restatement of
# "salary by level".
JOB_FAMILY_PREMIUM = {
    "Machine Learning": 1.14, "Data Engineering": 1.07, "Software Engineering": 1.05,
    "Site Reliability": 1.06, "Security Engineering": 1.08, "Quality Engineering": 0.94,
    "Engineering Management": 1.10, "Legal Counsel": 1.12, "Compliance": 0.98,
    "Account Executive": 0.92, "Sales Engineering": 1.00, "Sales Development": 0.82,
    "Sales Operations": 0.93, "Channel Sales": 0.95, "Sales Management": 1.06,
    "Product Marketing": 1.02, "Demand Generation": 0.92, "Brand & Content": 0.88,
    "Field Marketing": 0.90, "Customer Support": 0.80,
    "Customer Success Management": 0.95, "Professional Services": 0.98,
    "Business Operations": 0.96, "Procurement": 0.90, "Workplace": 0.78,
    "Accounting": 0.92, "Financial Planning & Analysis": 1.00, "Treasury & Tax": 1.02,
    "Talent Acquisition": 0.88, "HR Business Partner": 0.94, "Total Rewards": 0.96,
    "People Analytics": 1.00, "IT Operations": 0.86, "Enterprise Systems": 0.94,
}

# Families whose senior levels are a management ladder rather than an IC one.
MANAGEMENT_FAMILIES = {"Engineering Management", "Sales Management"}

MANAGEMENT_LEVEL = {
    "Individual Contributor": "Individual Contributor",
    "Manager": "Manager",
    "Director": "Director",
    "Executive": "Executive",
}

TERMINATION_REASONS_VOLUNTARY = [
    "Career Growth", "Compensation", "Manager", "Relocation",
    "Work-Life Balance", "Better Opportunity", "Retirement", "Personal Reasons",
]
TERMINATION_REASONS_INVOLUNTARY = [
    "Performance", "Layoff", "Restructuring", "Policy Violation",
    "End of Contract",
]

# (benefit_type, plan_name, provider, tiers, cost, cost_basis)
# cost_basis "flat" -> cost is an annual USD amount for Employee Only cover.
# cost_basis "pct"  -> cost is a fraction of base salary. Retirement match is a
# percentage of pay in every real plan, and modelling it as a flat fee both
# understates the cost and breaks the link between a pay rise and its knock-on
# benefits cost - which is a line in the cost bridge.
BENEFIT_CATALOG = [
    ("Medical", "Core PPO", "Northwind Health", 4, 11_400, "flat"),
    ("Medical", "Value HMO", "Northwind Health", 4, 8_600, "flat"),
    ("Medical", "High Deductible Plus", "Northwind Health", 4, 7_100, "flat"),
    ("Medical", "International Medical", "Global Care Partners", 4, 6_000, "flat"),
    ("Dental", "Dental Standard", "Brightline Dental", 4, 780, "flat"),
    ("Dental", "Dental Premium", "Brightline Dental", 4, 1_240, "flat"),
    ("Vision", "Vision Care", "ClearSight Vision", 4, 310, "flat"),
    ("401K", "401(k) Match", "Cardinal Retirement", 1, 0.055, "pct"),
    ("401K", "Pension Contribution", "Cardinal Retirement", 1, 0.045, "pct"),
    ("Life Insurance", "Basic Life 1x", "Sentinel Assurance", 1, 420, "flat"),
    ("Life Insurance", "Supplemental Life 3x", "Sentinel Assurance", 1, 960, "flat"),
    ("Disability", "Short Term Disability", "Sentinel Assurance", 1, 540, "flat"),
    ("Disability", "Long Term Disability", "Sentinel Assurance", 1, 690, "flat"),
    ("HSA", "Health Savings Account", "Northwind Health", 1, 1_200, "flat"),
    ("FSA", "Flexible Spending Account", "Northwind Health", 1, 0, "flat"),
    ("Wellness", "Wellness Stipend", "GlobalTech", 1, 600, "flat"),
]

COVERAGE_TIERS = ["Employee Only", "Employee + Spouse", "Employee + Children", "Family"]
COVERAGE_COST_FACTOR = {"Employee Only": 1.00, "Employee + Spouse": 1.85,
                        "Employee + Children": 1.70, "Family": 2.55}

ETHNICITY_MIX = {
    "US": {"White": 0.52, "Asian": 0.27, "Hispanic or Latino": 0.11,
           "Black or African American": 0.07, "Two or More Races": 0.02,
           "Not Specified": 0.01},
    "Canada": {"White": 0.58, "Asian": 0.29, "Black or African American": 0.06,
               "Two or More Races": 0.04, "Not Specified": 0.03},
    "UK": {"White": 0.68, "Asian": 0.20, "Black or African American": 0.07,
           "Two or More Races": 0.03, "Not Specified": 0.02},
    "Germany": {"White": 0.79, "Asian": 0.11, "Two or More Races": 0.05,
                "Not Specified": 0.05},
    "India": {"Asian": 0.97, "Not Specified": 0.03},
    "Japan": {"Asian": 0.96, "Not Specified": 0.04},
}


def make_name_pool(rng: np.random.Generator, culture: str, n: int):
    """n (first, last) pairs for a culture. Duplicates are allowed on purpose -
    real companies have two Priya Sharmas, and that feeds the data-quality story."""
    first = np.array(FIRST_NAMES[culture])
    last = np.array(LAST_NAMES[culture])
    return rng.choice(first, n), rng.choice(last, n)


def weighted_choice(rng: np.random.Generator, mapping: dict, n: int) -> np.ndarray:
    keys = np.array(list(mapping.keys()))
    p = np.array(list(mapping.values()), dtype=float)
    return rng.choice(keys, size=n, p=p / p.sum())
