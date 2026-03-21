"""
School Sports Scraper Configuration
Customize these settings for K-12 school athletics contact discovery
"""

# ==================== SUPPORTED SPORTS ====================

SUPPORTED_SPORTS = (
    "football",
    "basketball",
    "baseball",
    "softball",
    "soccer",
    "volleyball",
    "track and field",
    "cross country",
    "wrestling",
    "swimming",
    "tennis",
    "golf",
    "lacrosse",
    "field hockey",
    "cheerleading",
    "gymnastics",
    "hockey",
    "water polo",
    "bowling",
    "rugby",
    "dance",
    "drill team",
    "powerlifting",
    "archery",
    "fencing",
    "rowing",
    "badminton",
    "table tennis",
)


# ==================== SEARCH CONFIGURATION ====================

SEARCH_QUERY_TEMPLATES = {
    "by_city": "{city} {state} high school athletics",
    "by_city_coaches": "high schools in {city} {state} coaching staff directory",
    "by_district": "{district} school district athletics {state}",
    "by_k12_domain": "site:*.k12.{state_abbrev}.us {city} athletics",
    "by_city_middle": "{city} {state} middle school athletics",
}

# Maximum Google search results pages to process per query
MAX_SEARCH_PAGES = 3

# Maximum number of search queries per geographic target
MAX_QUERIES_PER_TARGET = 5


# ==================== SCHOOL WEBSITE DETECTION ====================

# URL patterns that indicate a school website
SCHOOL_DOMAIN_PATTERNS = (
    ".k12.",
    ".edu",
    "finalsite.com",
    "schoolpointe.com",
    "blackboard.com",
    "powerschool.com",
    "schoolwires.net",
    "edlio.com",
    "edlioschool.com",
    "campusinsite.com",
    "thrillshare.com",
    "apptegy.com",
)

# Keywords in titles/snippets that indicate a school
SCHOOL_TITLE_KEYWORDS = (
    "high school",
    "middle school",
    "junior high",
    "elementary school",
    "school district",
    "independent school district",
    "isd",
    "unified school district",
    "usd",
    "academy",
    "preparatory",
    "prep school",
)

# Domains to exclude from school results
EXCLUDED_DOMAINS = (
    "niche.com",
    "greatschools.org",
    "usnews.com",
    "wikipedia.org",
    "zillow.com",
    "realtor.com",
    "yelp.com",
    "facebook.com",
    "twitter.com",
    "instagram.com",
    "youtube.com",
    "linkedin.com",
    "indeed.com",
    "glassdoor.com",
    "maxpreps.com",
    "hudl.com",
    "pinterest.com",
    "nfhsnetwork.com",
    "nfhs.org",
    "si.com",
    "247sports.com",
    "rivals.com",
    "espn.com",
    "bleacherreport.com",
    "cbssports.com",
    "prep-football.net",
    "scorestream.com",
    "athleticnet.com",
    "milb.com",
    "usatoday.com",
    "timesrecorder.com",
    "zanesvilletimesrecorder.com",
)


# ==================== ATHLETICS PAGE DISCOVERY ====================

ATHLETICS_PAGE_KEYWORDS = (
    "athletics",
    "sports",
    "athletic",
    "coaches",
    "coaching-staff",
    "coaching staff",
    "staff-directory",
    "staff directory",
    "our-team",
    "our coaches",
    "varsity",
    "booster",
    "athletic-department",
    "athletic department",
)

# Common URL path patterns for athletics pages
ATHLETICS_URL_PATTERNS = (
    "/athletics",
    "/sports",
    "/athletics/coaches",
    "/athletics/staff",
    "/athletics/coaching-staff",
    "/athletics/directory",
    "/page/athletics",
    "/domain/athletics",
    "/departments/athletics",
    "/our-school/athletics",
)


# ==================== STAFF TITLE PATTERNS ====================

STAFF_TITLE_PATTERNS = {
    "athletic_director": r"(?i)(?:athletic\s+director|(?<!\w)a\.?d\.?(?!\w)|director\s+of\s+athletics|athletics\s+director|athletic\s+coordinator)",
    "head_coach": r"(?i)(?:head\s+coach|varsity\s+coach|varsity\s+head|lead\s+coach)",
    "assistant_coach": r"(?i)(?:assistant\s+coach|asst\.?\s+coach|jv\s+coach|junior\s+varsity\s+coach|freshman\s+coach)",
    "coordinator": r"(?i)(?:offensive\s+coordinator|defensive\s+coordinator|coordinator)",
    "trainer": r"(?i)(?:athletic\s+trainer|sports\s+trainer|trainer)",
}

# Generic email prefixes to filter out (not personal contacts)
GENERIC_EMAIL_PREFIXES = (
    "info@",
    "office@",
    "admin@",
    "webmaster@",
    "noreply@",
    "no-reply@",
    "support@",
    "contact@",
    "general@",
    "main@",
    "secretary@",
    "front@",
    "help@",
    "enrollment@",
    "registrar@",
    "attendance@",
)


# ==================== FUNDRAISER CONFIGURATION ====================

FUNDRAISER_CONFIG = {
    "product_name": "Jose Madrid Salsa",
    "product_url": "https://josemadridsalsa.com",
    "fundraiser_percentage": "50%",
    "min_order": "$0",
    "upfront_cost": "$0",
    "product_types": ["salsa", "queso", "seasonings", "snack mixes"],
    "typical_raise_low": "$2,000",
    "typical_raise_high": "$10,000",
}


# ==================== SENDER INFORMATION ====================

FROM_EMAIL = "jordan@jlang.dev"
FROM_NAME = "Jordan Lang"
BUSINESS_NAME = "Jose Madrid Salsa Fundraising"
PRODUCT_URL = "https://josemadridsalsa.com"


# ==================== FILE PATHS ====================

TEMPLATE_PATH = "school_email_template.html"
OUTPUT_DIR = "generated_school_emails"
CSV_FILE = None  # None = use most recent


# ==================== GENERATION OPTIONS ====================

SKIP_NO_EMAIL = True
GENERATION_LIMIT = None


# ==================== SUBJECT LINE TEMPLATES ====================

SUBJECT_LINE_TEMPLATES = {
    "default": "Fundraising Opportunity for {school_name} {sport}",
    "profit": "Earn 50% Profit for {school_name} Athletics",
    "easy": "Easy Fundraiser for {school_name} {sport} - No Upfront Cost",
    "direct": "{sport} Fundraiser - 50% Profit, Zero Risk",
    "personal": "Coach, Here's a Fundraiser Your {sport} Team Will Love",
}

DEFAULT_SUBJECT_STYLE = "default"


# ==================== SPORT-SPECIFIC FUNDRAISER PITCHES ====================

SPORT_PITCHES = {
    "football": "equipment upgrades, travel expenses, and team gear",
    "basketball": "tournament fees, uniforms, and training equipment",
    "baseball": "field maintenance, equipment, and tournament travel",
    "softball": "field equipment, uniforms, and travel costs",
    "soccer": "league fees, uniforms, and tournament expenses",
    "volleyball": "net equipment, uniforms, and tournament fees",
    "track and field": "hurdles, shot puts, and meet travel costs",
    "cross country": "race entry fees, team gear, and travel",
    "wrestling": "mats, singlets, and tournament travel",
    "swimming": "pool time, lane equipment, and meet fees",
    "tennis": "court maintenance, rackets, and match travel",
    "golf": "green fees, equipment, and tournament entry",
    "lacrosse": "sticks, protective gear, and league fees",
    "field hockey": "sticks, turf time, and tournament travel",
    "cheerleading": "uniforms, camp fees, and competition travel",
    "gymnastics": "equipment, leotards, and meet fees",
    "hockey": "ice time, equipment, and travel expenses",
    "water polo": "pool time, caps, and tournament fees",
}

DEFAULT_PITCH = "equipment, travel, and program needs"


# ==================== FILTERING OPTIONS ====================

MIN_RATING = None
SPORTS_FILTER = None  # None = all sports, or list like ["football", "basketball"]
ROLES_FILTER = None  # None = all roles, or list like ["athletic_director", "head_coach"]
EXCLUDE_KEYWORDS = []


# ==================== ADVANCED OPTIONS ====================

# Maximum athletics sub-pages to crawl per school
MAX_PAGES_PER_SCHOOL = 5

# Delay between requests (seconds) - be respectful
REQUEST_DELAY = 3.0

# Page load timeout (seconds)
PAGE_LOAD_TIMEOUT = 30

VERBOSE = True


# ==================== US STATE ABBREVIATIONS ====================

STATE_ABBREVIATIONS = {
    "Alabama": "al", "Alaska": "ak", "Arizona": "az", "Arkansas": "ar",
    "California": "ca", "Colorado": "co", "Connecticut": "ct", "Delaware": "de",
    "Florida": "fl", "Georgia": "ga", "Hawaii": "hi", "Idaho": "id",
    "Illinois": "il", "Indiana": "in", "Iowa": "ia", "Kansas": "ks",
    "Kentucky": "ky", "Louisiana": "la", "Maine": "me", "Maryland": "md",
    "Massachusetts": "ma", "Michigan": "mi", "Minnesota": "mn", "Mississippi": "ms",
    "Missouri": "mo", "Montana": "mt", "Nebraska": "ne", "Nevada": "nv",
    "New Hampshire": "nh", "New Jersey": "nj", "New Mexico": "nm", "New York": "ny",
    "North Carolina": "nc", "North Dakota": "nd", "Ohio": "oh", "Oklahoma": "ok",
    "Oregon": "or", "Pennsylvania": "pa", "Rhode Island": "ri", "South Carolina": "sc",
    "South Dakota": "sd", "Tennessee": "tn", "Texas": "tx", "Utah": "ut",
    "Vermont": "vt", "Virginia": "va", "Washington": "wa", "West Virginia": "wv",
    "Wisconsin": "wi", "Wyoming": "wy",
}

# Reverse lookup: abbreviation -> full name
ABBREV_TO_STATE = {v: k for k, v in STATE_ABBREVIATIONS.items()}


# ==================== DO NOT EDIT BELOW THIS LINE ====================

def get_config():
    """Return configuration as a dictionary"""
    return {
        "supported_sports": SUPPORTED_SPORTS,
        "search_query_templates": SEARCH_QUERY_TEMPLATES,
        "school_domain_patterns": SCHOOL_DOMAIN_PATTERNS,
        "school_title_keywords": SCHOOL_TITLE_KEYWORDS,
        "excluded_domains": EXCLUDED_DOMAINS,
        "athletics_page_keywords": ATHLETICS_PAGE_KEYWORDS,
        "athletics_url_patterns": ATHLETICS_URL_PATTERNS,
        "staff_title_patterns": STAFF_TITLE_PATTERNS,
        "generic_email_prefixes": GENERIC_EMAIL_PREFIXES,
        "fundraiser_config": FUNDRAISER_CONFIG,
        "from_email": FROM_EMAIL,
        "from_name": FROM_NAME,
        "template_path": TEMPLATE_PATH,
        "output_dir": OUTPUT_DIR,
        "csv_file": CSV_FILE,
        "skip_no_email": SKIP_NO_EMAIL,
        "generation_limit": GENERATION_LIMIT,
        "subject_line_templates": SUBJECT_LINE_TEMPLATES,
        "default_subject_style": DEFAULT_SUBJECT_STYLE,
        "sport_pitches": SPORT_PITCHES,
        "default_pitch": DEFAULT_PITCH,
        "sports_filter": SPORTS_FILTER,
        "roles_filter": ROLES_FILTER,
        "max_pages_per_school": MAX_PAGES_PER_SCHOOL,
        "request_delay": REQUEST_DELAY,
        "page_load_timeout": PAGE_LOAD_TIMEOUT,
        "verbose": VERBOSE,
    }
