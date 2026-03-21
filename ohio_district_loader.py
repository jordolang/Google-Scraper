#!/usr/bin/env python3
"""
Ohio School District Loader
Uses the Ohio Education Directory System (OEDS) to get every public school district.
IRN (Information Retrieval Number) is the official unique identifier for each district.
"""

import requests
import json
import csv
import time
import sys
from datetime import datetime

OEDS_API = "https://oeds.education.ohio.gov/Api/searchOrg"
COUNTY_API = "https://oeds.education.ohio.gov/Api/searchOrg/GetSearchByAddressDropDownValues"

HEADERS = {
    "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36",
    "Content-Type": "application/json",
    "X-Requested-With": "XMLHttpRequest",
}

# Ohio city names by county - used to supplement county-name searches
# Districts named after cities (e.g. "Zanesville City") won't match a county-name search
OHIO_COUNTY_CITIES = {
    "Adams": ["West Union"],
    "Allen": ["Lima", "Elida", "Delphos"],
    "Ashland": ["Ashland", "Loudonville", "Hillsdale"],
    "Ashtabula": ["Ashtabula", "Jefferson", "Geneva", "Conneaut"],
    "Athens": ["Athens", "Alexander", "Federal Hocking"],
    "Auglaize": ["Wapakoneta", "Minster", "New Knoxville"],
    "Belmont": ["Bellaire", "Bridgeport", "St Clairsville", "Union"],
    "Brown": ["Georgetown", "Western Brown", "Ripley"],
    "Butler": ["Hamilton", "Middletown", "Fairfield", "Monroe", "Edgewood", "New Miami"],
    "Carroll": ["Carrollton"],
    "Champaign": ["Urbana", "Graham", "Triad"],
    "Clark": ["Springfield", "Greenon", "Northeastern", "Tecumseh"],
    "Clermont": ["Batavia", "Milford", "Loveland", "West Clermont"],
    "Clinton": ["Wilmington", "Clinton-Massie"],
    "Columbiana": ["East Liverpool", "Salem", "Lisbon", "United"],
    "Coshocton": ["Coshocton", "River View", "Ridgewood"],
    "Crawford": ["Bucyrus", "Galion", "Colonel Crawford"],
    "Cuyahoga": ["Cleveland", "Parma", "Lakewood", "Shaker Heights", "Strongsville",
                 "Solon", "Westlake", "Rocky River", "Beachwood", "Berea", "Euclid"],
    "Darke": ["Greenville", "Versailles", "Ansonia"],
    "Defiance": ["Defiance", "Ayersville", "Hicksville", "Northeastern"],
    "Delaware": ["Delaware", "Olentangy", "Big Walnut", "Buckeye Valley"],
    "Erie": ["Sandusky", "Huron", "Perkins", "Berlin Heights"],
    "Fairfield": ["Lancaster", "Pickerington", "Bloom Carroll", "Liberty Union"],
    "Fayette": ["Washington Court House", "Miami Trace"],
    "Franklin": ["Columbus", "Dublin", "Hilliard", "Westerville", "Grove City",
                 "Upper Arlington", "Worthington", "New Albany", "Groveport"],
    "Fulton": ["Swanton", "Archbold", "Evergreen", "Wauseon"],
    "Gallia": ["Gallipolis", "Gallia County"],
    "Geauga": ["Chardon", "West Geauga", "Kenston", "Cardinal"],
    "Greene": ["Xenia", "Beavercreek", ["Fairborn", "Yellow Springs", "Greeneview"]],
    "Guernsey": ["Cambridge", "East Guernsey", "Rolling Hills"],
    "Hamilton": ["Cincinnati", "Norwood", "Loveland", "Forest Hills", "Indian Hill",
                 "Mariemont", "Oak Hills", "Sycamore", "Princeton"],
    "Hancock": ["Findlay", "Arcadia", "Liberty-Benton"],
    "Hardin": ["Kenton", "Ada", "Ridgemont"],
    "Harrison": ["Conotton Valley", "Harrison Hills"],
    "Henry": ["Napoleon", "Patrick Henry", "Holgate"],
    "Highland": ["Hillsboro", "Greenfield", "Fairfield"],
    "Hocking": ["Logan", "Hocking Hills"],
    "Holmes": ["East Holmes", "West Holmes"],
    "Huron": ["Norwalk", "Willard", "Western Reserve"],
    "Jackson": ["Jackson", "Oak Hill", "Wellston"],
    "Jefferson": ["Steubenville", "Toronto", "Edison"],
    "Knox": ["Mount Vernon", "Danville", "East Knox"],
    "Lake": ["Mentor", "Willoughby", "Eastlake", "Painesville", "Kirtland"],
    "Lawrence": ["Ironton", "South Point", "Chesapeake"],
    "Licking": ["Newark", "Heath", "Granville", "Johnstown", "Utica"],
    "Logan": ["Bellefontaine", "Indian Lake", "Benjamin Logan"],
    "Lorain": ["Elyria", "Lorain", "Amherst", "Oberlin", "Clearview", "Firelands"],
    "Lucas": ["Toledo", "Sylvania", "Perrysburg", "Springfield", "Anthony Wayne"],
    "Madison": ["London", "Jefferson", "Madison Plains"],
    "Mahoning": ["Youngstown", "Austintown", "Canfield", "Poland", "Boardman"],
    "Marion": ["Marion", "Pleasant", "Elgin", "River Valley"],
    "Medina": ["Medina", "Brunswick", "Wadsworth", "Highland"],
    "Meigs": ["Eastern", "Southern", "Meigs"],
    "Mercer": ["Celina", "Parkway", "St Henry", "Marion"],
    "Miami": ["Piqua", "Troy", "Tipp City", "Milton Union", "Covington"],
    "Monroe": ["Switzerland of Ohio"],
    "Montgomery": ["Dayton", "Kettering", "Centerville", "Huber Heights", "Oakwood",
                   "Trotwood", "Fairborn", "Northmont", "Northridge"],
    "Morgan": ["Morgan"],
    "Morrow": ["Mount Gilead", "Highland"],
    "Muskingum": ["Zanesville City", "West Muskingum", "East Muskingum",
                  "Tri-Valley", "Franklin", "Maysville", "Philo", "Dresden"],
    "Noble": ["Caldwell", "Noble"],
    "Ottawa": ["Port Clinton", "Danbury", "Benton Carroll Salem"],
    "Paulding": ["Paulding", "Antwerp", "Wayne Trace"],
    "Perry": ["New Lexington", "Northern", "Southern"],
    "Pickaway": ["Circleville", "Logan Elm", "Teays Valley"],
    "Pike": ["Eastern", "Scioto Valley", "Western"],
    "Portage": ["Ravenna", "Aurora", "Kent", "Streetsboro", "Windham"],
    "Preble": ["Eaton", "Twin Valley", "National Trail"],
    "Putnam": ["Ottawa", "Pandora", "Leipsic", "Continental"],
    "Richland": ["Mansfield", "Ontario", "Lexington", "Madison", "Plymouth"],
    "Ross": ["Chillicothe", "Zane Trace", "Union Scioto"],
    "Sandusky": ["Fremont", "Clyde Green Springs", "Gibsonburg"],
    "Scioto": ["Portsmouth", "Northwest", "Valley", "Wheelersburg"],
    "Seneca": ["Tiffin", "Fostoria", "Bettsville", "Hopewell"],
    "Shelby": ["Sidney", "Anna", "Jackson Center", "Fairlawn"],
    "Stark": ["Canton", "Massillon", "Alliance", "Jackson", "Perry", "Lake", "Marlington"],
    "Summit": ["Akron", "Cuyahoga Falls", "Stow", "Hudson", "Tallmadge", "Norton"],
    "Trumbull": ["Warren", "Niles", "Girard", "Brookfield", "Champion"],
    "Tuscarawas": ["New Philadelphia", "Dover", "Newcomerstown", "Indian Valley"],
    "Union": ["Marysville", "Dublin", "Jonathan Alder", "North Union"],
    "Van Wert": ["Van Wert", "Crestview", "Lincolnview"],
    "Vinton": ["Vinton County"],
    "Warren": ["Lebanon", "Mason", "Springboro", "Franklin", "Kings", "Little Miami"],
    "Washington": ["Marietta", "Warren", "Frontier", "Fort Frye"],
    "Wayne": ["Wooster", "Orrville", "Dalton", "Norwayne", "Smithville"],
    "Williams": ["Bryan", "Montpelier", "Stryker", "Edgerton"],
    "Wood": ["Bowling Green", "Perrysburg", "Rossford", "Otsego", "Eastwood"],
    "Wyandot": ["Upper Sandusky", "Carey", "Mohawk"],
}


def oeds_search(search_field: str, session: requests.Session) -> list[dict]:
    payload = {
        "SearchField": search_field,
        "AddressText": "", "CityText": "", "ZipText": "", "FedTaxId": "",
        "DeptAccntsRvwedFlg": False, "SelectedOrgApprovalStatusKey": 0,
        "selectedOrgTypeKeyForDdl": 0, "selectedStateForAddress": 0,
        "selectedCountyForAddress": 0,
        "OrgTypes": [], "OrgStatuses": [], "SchoolTypes": [],
        "Counties": [], "Cities": [], "includeOrgsWithNoIrn": False
    }
    try:
        r = session.post(OEDS_API, json=payload, timeout=15)
        rows = r.json()["searchOrganizationResponse"]["SearchOrgRows"]
        return [x for x in rows
                if x.get("OrgTypeName") == "Public District" and x.get("Status") == "Open"]
    except Exception as e:
        print(f"    OEDS error for '{search_field}': {e}", file=sys.stderr)
        return []


def get_all_ohio_counties(session: requests.Session) -> list[dict]:
    r = session.get(COUNTY_API, timeout=10)
    return r.json().get("Counties", [])


def get_districts_for_county(county_name: str, session: requests.Session) -> dict[str, dict]:
    """Get all open public districts in a county by searching multiple terms."""
    all_districts: dict[str, dict] = {}

    # Search terms: county name + all known city names in this county
    search_terms = [county_name]
    city_terms = OHIO_COUNTY_CITIES.get(county_name, [])
    # Flatten nested lists
    for t in city_terms:
        if isinstance(t, list):
            search_terms.extend(t)
        else:
            search_terms.append(t)

    for term in search_terms:
        results = oeds_search(term, session)
        # Filter to only this county
        county_results = [r for r in results if r.get("CountyName") == county_name]
        for d in county_results:
            irn = d["Irn"]
            if irn not in all_districts:
                all_districts[irn] = d
        time.sleep(0.15)

    return all_districts


def get_all_ohio_districts(target_counties: list[str] | None = None) -> list[dict]:
    """Get all open public school districts in Ohio (or a subset of counties)."""
    session = requests.Session()
    session.headers.update(HEADERS)

    all_counties = get_all_ohio_counties(session)
    print(f"Ohio counties: {len(all_counties)}")

    all_districts: dict[str, dict] = {}

    counties_to_process = all_counties
    if target_counties:
        counties_to_process = [c for c in all_counties
                                if c["Value"] in target_counties]

    for i, county in enumerate(counties_to_process):
        county_name = county["Value"]
        print(f"[{i+1}/{len(counties_to_process)}] {county_name}...", end=" ", flush=True)
        districts = get_districts_for_county(county_name, session)
        new = {k: v for k, v in districts.items() if k not in all_districts}
        all_districts.update(new)
        print(f"{len(districts)} districts ({len(new)} new)")

    return list(all_districts.values())


def save_districts(districts: list[dict], filename: str | None = None) -> str:
    if not filename:
        filename = f"ohio_districts_{datetime.now().strftime('%Y%m%d_%H%M%S')}.csv"
    fields = ["Irn", "Name", "CountyName", "CityName", "WebUrl", "Phone", "Email",
              "Address", "Fax", "Status", "OrgTypeName"]
    with open(filename, "w", newline="", encoding="utf-8") as f:
        w = csv.DictWriter(f, fieldnames=fields, extrasaction="ignore")
        w.writeheader()
        w.writerows(sorted(districts, key=lambda x: (x.get("CountyName",""), x.get("Name",""))))
    print(f"Saved {len(districts)} districts to {filename}")
    return filename


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser(description="Load all Ohio public school districts from OEDS")
    parser.add_argument("--counties", nargs="+", help="Specific county names to load (default: all 88)")
    parser.add_argument("--output", help="Output CSV filename")
    args = parser.parse_args()

    districts = get_all_ohio_districts(target_counties=args.counties)
    print(f"\nTotal open public districts: {len(districts)}")
    save_districts(districts, args.output)
