import pandas as pd
import numpy as np
from faker import Faker
from datetime import datetime
import random

fake = Faker()
np.random.seed(42)
random.seed(42)

NUM_EMPLOYEES = 1000

departments = [
    "Sales", "Finance", "HR", "IT",
    "Marketing", "Operations", "Customer Support"
]

locations = ["Dallas", "Austin", "New York", "Chicago", "Atlanta", "Phoenix"]
medical_plans = ["Bronze", "Silver", "Gold"]

# ----------------------------------------------------
# JOB PROFILES & GRADES
# ----------------------------------------------------

grade_salary_bands = {
    "G1": (40000,  60000),
    "G2": (55000,  80000),
    "G3": (75000, 105000),
    "G4": (95000, 135000),
    "G5": (125000, 165000),
    "G6": (155000, 205000),
    "G7": (190000, 255000),
    "G8": (240000, 350000),
}

grade_names = ["G1", "G2", "G3", "G4", "G5", "G6", "G7", "G8"]

grade_to_org_level = {
    "G1": "Individual Contributor",
    "G2": "Individual Contributor",
    "G3": "Individual Contributor",
    "G4": "Individual Contributor",
    "G5": "Senior Individual Contributor",
    "G6": "Manager",
    "G7": "Director",
    "G8": "Vice President",
}

job_titles_by_dept_grade = {
    "Sales": {
        "G1": "Sales Representative I",        "G2": "Sales Representative II",
        "G3": "Senior Sales Representative",    "G4": "Sales Specialist",
        "G5": "Senior Sales Specialist",        "G6": "Sales Manager",
        "G7": "Sales Director",                 "G8": "VP of Sales",
    },
    "Finance": {
        "G1": "Finance Analyst I",              "G2": "Finance Analyst II",
        "G3": "Senior Finance Analyst",         "G4": "Finance Lead",
        "G5": "Senior Finance Lead",            "G6": "Finance Manager",
        "G7": "Finance Director",               "G8": "VP of Finance",
    },
    "HR": {
        "G1": "HR Coordinator I",               "G2": "HR Coordinator II",
        "G3": "HR Specialist",                  "G4": "Senior HR Specialist",
        "G5": "HR Business Partner",            "G6": "HR Manager",
        "G7": "HR Director",                    "G8": "Chief HR Officer",
    },
    "IT": {
        "G1": "IT Support Specialist I",        "G2": "Software Engineer I",
        "G3": "Software Engineer II",           "G4": "Senior Software Engineer",
        "G5": "Staff Engineer",                 "G6": "Engineering Manager",
        "G7": "Engineering Director",           "G8": "VP of Engineering",
    },
    "Marketing": {
        "G1": "Marketing Coordinator I",        "G2": "Marketing Coordinator II",
        "G3": "Marketing Specialist",           "G4": "Senior Marketing Specialist",
        "G5": "Marketing Lead",                 "G6": "Marketing Manager",
        "G7": "Marketing Director",             "G8": "VP of Marketing",
    },
    "Operations": {
        "G1": "Operations Coordinator I",       "G2": "Operations Coordinator II",
        "G3": "Operations Analyst",             "G4": "Senior Operations Analyst",
        "G5": "Operations Lead",                "G6": "Operations Manager",
        "G7": "Operations Director",            "G8": "VP of Operations",
    },
    "Customer Support": {
        "G1": "Support Representative I",       "G2": "Support Representative II",
        "G3": "Senior Support Representative",  "G4": "Support Specialist",
        "G5": "Senior Support Specialist",      "G6": "Support Manager",
        "G7": "Support Director",               "G8": "VP of Customer Success",
    },
}

dept_to_family = {
    "Sales": "Sales",
    "Finance": "Finance",
    "HR": "Human Resources",
    "IT": "Technology",
    "Marketing": "Marketing",
    "Operations": "Operations",
    "Customer Support": "Customer Support",
}

job_profiles_rows = []
profile_lookup = {}
profile_id = 1

for dept in departments:
    for grade, (min_sal, max_sal) in grade_salary_bands.items():
        pid = f"JP{profile_id:04d}"
        job_profiles_rows.append({
            "job_profile_id": pid,
            "job_title": job_titles_by_dept_grade[dept][grade],
            "job_family": dept_to_family[dept],
            "grade": grade,
            "min_salary": min_sal,
            "max_salary": max_sal,
        })
        profile_lookup[(dept, grade)] = pid
        profile_id += 1

job_profiles_df = pd.DataFrame(job_profiles_rows)

# ----------------------------------------------------
# WORKERS  (diversity metrics + grade + job profile)
# ----------------------------------------------------

# Grade distribution: mostly ICs, thin management layer
grade_weights = [0.08, 0.18, 0.22, 0.20, 0.15, 0.10, 0.05, 0.02]

ethnicities = [
    "White", "Hispanic or Latino", "Black or African American",
    "Asian", "Two or more races", "Native American",
    "Pacific Islander", "Prefer not to disclose",
]
ethnicity_weights = [0.60, 0.18, 0.12, 0.06, 0.02, 0.01, 0.005, 0.005]

gender_identities = ["Male", "Female", "Non-binary", "Prefer not to disclose"]
gender_weights    = [0.48, 0.48, 0.02, 0.02]

workers = []
for i in range(NUM_EMPLOYEES):
    hire_date = fake.date_between(start_date="-10y", end_date="today")
    grade = np.random.choice(grade_names, p=grade_weights)
    dept  = np.random.choice(departments)

    workers.append({
        "employee_id":      100000 + i,
        "employee_name":    fake.name(),
        "gender_identity":  np.random.choice(gender_identities, p=gender_weights),
        "ethnicity":        np.random.choice(ethnicities, p=ethnicity_weights),
        "veteran_status":   np.random.choice(["Yes", "No"], p=[0.08, 0.92]),
        "disability_status":np.random.choice(["Yes", "No"], p=[0.07, 0.93]),
        "department":       dept,
        "location":         np.random.choice(locations),
        "hire_date":        hire_date,
        "age":              np.random.randint(22, 65),
        "grade":            grade,
        "job_title":        job_titles_by_dept_grade[dept][grade],
        "org_level":        grade_to_org_level[grade],
        "job_profile_id":   profile_lookup[(dept, grade)],
        "status":           "Active",
        "termination_date": None,
        "termination_reason": None,
    })

workers_df = pd.DataFrame(workers)

# ----------------------------------------------------
# MANAGER HIERARCHY
# ----------------------------------------------------

# Build per-department pools for each leadership grade
g8_by_dept, g7_by_dept, g6_by_dept = {}, {}, {}

for _, row in workers_df.iterrows():
    dept, grade, eid = row["department"], row["grade"], row["employee_id"]
    if grade == "G8":
        g8_by_dept.setdefault(dept, []).append(eid)
    elif grade == "G7":
        g7_by_dept.setdefault(dept, []).append(eid)
    elif grade == "G6":
        g6_by_dept.setdefault(dept, []).append(eid)

all_g8 = [e for v in g8_by_dept.values() for e in v]
all_g7 = [e for v in g7_by_dept.values() for e in v]
all_g6 = [e for v in g6_by_dept.values() for e in v]

# First G8 is the CEO — no manager
ceo_id = all_g8[0] if all_g8 else None

manager_map = {}
for _, row in workers_df.iterrows():
    eid, dept, grade = row["employee_id"], row["department"], row["grade"]

    if grade == "G8":
        manager_map[eid] = None if eid == ceo_id else ceo_id
    elif grade == "G7":
        pool = g8_by_dept.get(dept) or all_g8
        manager_map[eid] = random.choice(pool) if pool else None
    elif grade == "G6":
        pool = g7_by_dept.get(dept) or all_g7
        manager_map[eid] = random.choice(pool) if pool else None
    else:
        pool = g6_by_dept.get(dept) or all_g6
        manager_map[eid] = random.choice(pool) if pool else None

workers_df["manager_id"] = workers_df["employee_id"].map(manager_map)

# ----------------------------------------------------
# COMPENSATION  (salary constrained within grade band)
# ----------------------------------------------------

comp_rows = []
for _, row in workers_df.iterrows():
    min_sal, max_sal = grade_salary_bands[row["grade"]]
    salary = np.random.randint(min_sal, max_sal)
    bonus  = round(salary * np.random.uniform(0.05, 0.20), 2)

    comp_rows.append({
        "employee_id":        int(row["employee_id"]),
        "annual_salary":      salary,
        "annual_bonus_target": bonus,
    })

comp_df = pd.DataFrame(comp_rows)

# ----------------------------------------------------
# JOB HISTORY  (Hire · Promotion · Transfer · Termination)
# ----------------------------------------------------

termination_reasons = [
    "Voluntary Resignation", "Involuntary", "Retirement", "Contract End"
]

job_history_rows = []

for _, row in workers_df.iterrows():
    eid           = int(row["employee_id"])
    hire_date     = row["hire_date"]
    current_grade = row["grade"]
    current_dept  = row["department"]
    current_title = row["job_title"]
    current_salary = comp_df.loc[
        comp_df.employee_id == eid, "annual_salary"
    ].iloc[0]

    # Initial grade: one step below current (where possible)
    grade_idx     = grade_names.index(current_grade)
    initial_grade = grade_names[max(0, grade_idx - np.random.randint(0, 2))]
    init_min, init_max = grade_salary_bands[initial_grade]
    initial_salary = np.random.randint(init_min, min(init_max, current_salary + 1))
    initial_title  = job_titles_by_dept_grade[current_dept][initial_grade]

    # Hire event
    job_history_rows.append({
        "employee_id":   eid,
        "effective_date": hire_date,
        "event_type":    "Hire",
        "from_department": None, "to_department": current_dept,
        "from_grade":    None,   "to_grade":      initial_grade,
        "from_title":    None,   "to_title":      initial_title,
        "from_salary":   None,   "to_salary":     initial_salary,
    })

    # Promotion (30 % of employees who started below current grade)
    if initial_grade != current_grade and np.random.random() < 0.30:
        promo_date = fake.date_between(start_date=hire_date, end_date="today")
        promo_min, promo_max = grade_salary_bands[current_grade]
        promo_salary = np.random.randint(promo_min, promo_max)

        job_history_rows.append({
            "employee_id":   eid,
            "effective_date": promo_date,
            "event_type":    "Promotion",
            "from_department": current_dept, "to_department": current_dept,
            "from_grade":    initial_grade,  "to_grade":      current_grade,
            "from_title":    initial_title,  "to_title":      current_title,
            "from_salary":   initial_salary, "to_salary":     promo_salary,
        })

    # Transfer (15 % of employees)
    if np.random.random() < 0.15:
        from_dept      = random.choice([d for d in departments if d != current_dept])
        transfer_date  = fake.date_between(start_date=hire_date, end_date="today")
        from_title_val = job_titles_by_dept_grade[from_dept][current_grade]

        job_history_rows.append({
            "employee_id":   eid,
            "effective_date": transfer_date,
            "event_type":    "Transfer",
            "from_department": from_dept,     "to_department": current_dept,
            "from_grade":    current_grade,   "to_grade":      current_grade,
            "from_title":    from_title_val,  "to_title":      current_title,
            "from_salary":   current_salary,  "to_salary":     current_salary,
        })

    # Termination (8 % of employees)
    if np.random.random() < 0.08:
        term_date = fake.date_between(start_date=hire_date, end_date="today")
        reason    = np.random.choice(
            termination_reasons, p=[0.55, 0.25, 0.15, 0.05]
        )

        workers_df.loc[workers_df.employee_id == eid, "status"]             = "Terminated"
        workers_df.loc[workers_df.employee_id == eid, "termination_date"]   = term_date
        workers_df.loc[workers_df.employee_id == eid, "termination_reason"] = reason

        job_history_rows.append({
            "employee_id":   eid,
            "effective_date": term_date,
            "event_type":    "Termination",
            "from_department": current_dept, "to_department": None,
            "from_grade":    current_grade,  "to_grade":      None,
            "from_title":    current_title,  "to_title":      None,
            "from_salary":   current_salary, "to_salary":     None,
        })

job_history_df = pd.DataFrame(job_history_rows).sort_values(
    ["employee_id", "effective_date"]
).reset_index(drop=True)

# ----------------------------------------------------
# BENEFITS
# ----------------------------------------------------

benefit_rows = []
plan_cost = {"Bronze": 100, "Silver": 220, "Gold": 400}

for _, row in workers_df.iterrows():
    plan       = np.random.choice(medical_plans, p=[0.3, 0.5, 0.2])
    dependents = np.random.randint(0, 4)

    benefit_rows.append({
        "employee_id":        int(row["employee_id"]),
        "medical_plan":       plan,
        "dependents":         dependents,
        "dental_plan":        np.random.choice(["Yes", "No"], p=[0.8, 0.2]),
        "vision_plan":        np.random.choice(["Yes", "No"], p=[0.7, 0.3]),
        "monthly_benefit_cost": plan_cost[plan],
    })

benefit_df = pd.DataFrame(benefit_rows)

# ----------------------------------------------------
# PAYROLL  (skip periods after termination)
# ----------------------------------------------------

payroll_rows = []
months = pd.date_range("2025-01-01", end="2026-06-01", freq="MS")

# Build a quick termination-date lookup
term_date_lookup = workers_df.set_index("employee_id")["termination_date"].to_dict()
status_lookup    = workers_df.set_index("employee_id")["status"].to_dict()

for month in months:
    for _, row in comp_df.iterrows():
        eid = int(row["employee_id"])

        if status_lookup.get(eid) == "Terminated":
            term_date = term_date_lookup.get(eid)
            if term_date is not None and pd.Timestamp(term_date) < month:
                continue

        gross      = row["annual_salary"] / 12
        gross     += np.random.randint(0, 600)
        tax        = round(gross * 0.22, 2)
        benefit    = benefit_df.loc[benefit_df.employee_id == eid, "monthly_benefit_cost"].iloc[0]
        retirement = round(gross * 0.05, 2)
        net_pay    = round(gross - tax - benefit - retirement, 2)

        payroll_rows.append({
            "employee_id":      eid,
            "pay_period":       month,
            "gross_pay":        round(gross, 2),
            "tax":              tax,
            "benefit_deduction": benefit,
            "retirement":       retirement,
            "net_pay":          net_pay,
        })

payroll_df = pd.DataFrame(payroll_rows)

# ----------------------------------------------------
# ABSENCE
# ----------------------------------------------------

absence_rows = []
for _, row in workers_df.iterrows():
    absence_rows.append({
        "employee_id": int(row["employee_id"]),
        "pto_days":    np.random.randint(0, 25),
        "sick_days":   np.random.randint(0, 8),
    })

absence_df = pd.DataFrame(absence_rows)

# ----------------------------------------------------
# PERFORMANCE  (annual reviews 2022–2024)
# ----------------------------------------------------

ratings = [
    "Exceptional", "Exceeds Expectations",
    "Meets Expectations", "Below Expectations", "Unsatisfactory"
]

# Higher grades skew toward better ratings (survivorship bias)
rating_weights_by_grade = {
    "G1": [0.05, 0.20, 0.50, 0.18, 0.07],
    "G2": [0.07, 0.22, 0.48, 0.16, 0.07],
    "G3": [0.08, 0.25, 0.47, 0.14, 0.06],
    "G4": [0.10, 0.27, 0.45, 0.13, 0.05],
    "G5": [0.12, 0.28, 0.44, 0.12, 0.04],
    "G6": [0.14, 0.30, 0.42, 0.10, 0.04],
    "G7": [0.16, 0.32, 0.40, 0.09, 0.03],
    "G8": [0.18, 0.35, 0.38, 0.07, 0.02],
}

# Correlated score ranges per rating
rating_score_range = {
    "Exceptional":           (85, 100),
    "Exceeds Expectations":  (70,  85),
    "Meets Expectations":    (50,  70),
    "Below Expectations":    (30,  50),
    "Unsatisfactory":        ( 0,  30),
}

potential_by_rating = {
    "Exceptional":           ["High",   "High",   "Medium"],
    "Exceeds Expectations":  ["High",   "Medium", "Medium"],
    "Meets Expectations":    ["Medium", "Medium", "Low"],
    "Below Expectations":    ["Low",    "Low",    "Medium"],
    "Unsatisfactory":        ["Low",    "Low",    "Low"],
}

review_years = [2022, 2023, 2024, 2025]

performance_rows = []

for _, row in workers_df.iterrows():
    eid       = int(row["employee_id"])
    grade     = row["grade"]
    hire_date = row["hire_date"]
    hire_year = pd.Timestamp(hire_date).year

    term_date = workers_df.loc[workers_df.employee_id == eid, "termination_date"].iloc[0]
    term_year = pd.Timestamp(term_date).year if term_date else 9999

    for year in review_years:
        # Skip years before hire or after termination
        if year < hire_year or year > term_year:
            continue

        rating      = np.random.choice(ratings, p=rating_weights_by_grade[grade])
        lo, hi      = rating_score_range[rating]
        mgr_score   = round(np.random.uniform(lo / 10, hi / 10), 1)
        goals_met   = np.random.randint(lo, hi + 1)
        potential   = random.choice(potential_by_rating[rating])

        performance_rows.append({
            "employee_id":    eid,
            "review_year":    year,
            "review_period":  "Annual",
            "rating":         rating,
            "potential":      potential,
            "manager_score":  mgr_score,
            "goals_met_pct":  goals_met,
        })

performance_df = pd.DataFrame(performance_rows)

# ----------------------------------------------------
# LEARNING & DEVELOPMENT
# ----------------------------------------------------

# Required courses to have completed AT each grade level
required_by_grade = {
    "G1": [("Compliance Basics",                "Compliance"),
           ("Foundations of Excellence",        "Technical")],
    "G2": [("Communication Skills 101",         "Communication"),
           ("Project Management Fundamentals",  "Technical")],
    "G3": [("Advanced Communication",           "Communication"),
           ("Data-Driven Decision Making",      "Technical")],
    "G4": [("Strategic Thinking",               "Leadership"),
           ("Cross-functional Collaboration",   "Communication")],
    "G5": [("Leadership Essentials",            "Leadership"),
           ("People Management Basics",         "Management")],
    "G6": [("Executive Presence",               "Leadership"),
           ("Organizational Leadership",        "Management")],
    "G7": [("Executive Leadership Program",     "Leadership"),
           ("Business Strategy",                "Management")],
    "G8": [],
}

optional_courses = [
    ("Python for Data Analysis",   "Technical"),
    ("Excel Advanced",             "Technical"),
    ("Power BI Fundamentals",      "Technical"),
    ("SQL Essentials",             "Technical"),
    ("Cloud Computing Basics",     "Technical"),
    ("Presentation Skills",        "Communication"),
    ("Negotiation Tactics",        "Communication"),
    ("Business Writing",           "Communication"),
    ("Coaching Skills",            "Leadership"),
    ("Conflict Resolution",        "Leadership"),
    ("Change Management",          "Leadership"),
    ("Data Privacy & GDPR",        "Compliance"),
    ("Workplace Safety",           "Compliance"),
    ("Anti-Harassment Training",   "Compliance"),
    ("Performance Management",     "Management"),
    ("Talent Acquisition",         "Management"),
    ("Budget Planning",            "Management"),
]

ld_rows = []

for _, row in workers_df.iterrows():
    eid        = int(row["employee_id"])
    grade      = row["grade"]
    hire_date  = row["hire_date"]
    grade_idx  = grade_names.index(grade)

    term_date  = workers_df.loc[workers_df.employee_id == eid, "termination_date"].iloc[0]
    end_date   = term_date if term_date else "today"

    # Required courses for current grade and all grades below (completed)
    for g in grade_names[:grade_idx + 1]:
        for course_name, skill_cat in required_by_grade.get(g, []):
            # 90% completion rate for current-grade requirements
            if np.random.random() < 0.90:
                completion = fake.date_between(start_date=hire_date, end_date=end_date)
                ld_rows.append({
                    "employee_id":     eid,
                    "course_name":     course_name,
                    "completion_date": completion,
                    "skill_category":  skill_cat,
                    "is_required":     "Yes",
                })

    # Required courses for NEXT grade — 55% done (45% = promotion blocker)
    next_grade_idx = grade_idx + 1
    if next_grade_idx < len(grade_names):
        next_grade = grade_names[next_grade_idx]
        for course_name, skill_cat in required_by_grade.get(next_grade, []):
            if np.random.random() < 0.55:
                completion = fake.date_between(start_date=hire_date, end_date=end_date)
                ld_rows.append({
                    "employee_id":     eid,
                    "course_name":     course_name,
                    "completion_date": completion,
                    "skill_category":  skill_cat,
                    "is_required":     "Yes",
                })

    # 1–5 optional courses per employee
    n_optional = np.random.randint(1, 6)
    chosen     = random.sample(optional_courses, min(n_optional, len(optional_courses)))
    for course_name, skill_cat in chosen:
        completion = fake.date_between(start_date=hire_date, end_date=end_date)
        ld_rows.append({
            "employee_id":     eid,
            "course_name":     course_name,
            "completion_date": completion,
            "skill_category":  skill_cat,
            "is_required":     "No",
        })

ld_df = pd.DataFrame(ld_rows).sort_values(
    ["employee_id", "completion_date"]
).reset_index(drop=True)

# ----------------------------------------------------
# SAVE FILES
# ----------------------------------------------------

workers_df["employee_id"] = workers_df["employee_id"].astype(int)
workers_df["manager_id"]  = workers_df["manager_id"].astype("Int64")

workers_df.to_csv("workers.csv",             index=False)
comp_df.to_csv("compensation.csv",           index=False)
benefit_df.to_csv("benefit_enrollment.csv",  index=False)
payroll_df.to_csv("payroll.csv",             index=False)
absence_df.to_csv("absence.csv",             index=False)
job_profiles_df.to_csv("job_profiles.csv",       index=False)
job_history_df.to_csv("job_history.csv",         index=False)
performance_df.to_csv("performance.csv",         index=False)
ld_df.to_csv("learning_development.csv",         index=False)

print("Enhanced Workday HR dataset created!")
print(f"  workers:             {len(workers_df):>6} rows  |  terminated: {(workers_df.status == 'Terminated').sum()}")
print(f"  job_profiles:        {len(job_profiles_df):>6} rows")
print(f"  compensation:        {len(comp_df):>6} rows")
print(f"  benefit_enrollment:  {len(benefit_df):>6} rows")
print(f"  payroll:             {len(payroll_df):>6} rows")
print(f"  absence:             {len(absence_df):>6} rows")
print(f"  job_history:         {len(job_history_df):>6} rows")
print(f"  performance:         {len(performance_df):>6} rows")
print(f"  learning_development:{len(ld_df):>6} rows")
