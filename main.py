from typing import Dict, List
import re
import time

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

app = FastAPI()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

CACHE_TTL_SECONDS = 60 * 60
_cache: Dict[str, Dict] = {}

BUILDINGS = [
    "McKinley Hill Garden Villas",
    "Viceroy Towers",
    "Tuscany Residences at McKinley",
    "Uptown Parksuites",
]

def normalize_text(s: str) -> str:
    return re.sub(r"[^a-z0-9]", "", s.lower())

def fuzzy_match(building: str, text: str) -> bool:
    if not text:
        return False
    b = normalize_text(building)
    t = normalize_text(text)
    if b in t or t in b:
        return True
    if len(b) < 5 or len(t) < 5:
        return False
    mismatches = sum(1 for x, y in zip(b, t) if x != y)
    allowed = max(2, len(b) // 4)
    return mismatches <= allowed

def cache_key(building: str, max_budget: int, bedrooms: int) -> str:
    return f"{building}|{max_budget}|{bedrooms}"

def get_from_cache(key: str):
    entry = _cache.get(key)
    if not entry:
        return None
    if time.time() - entry["timestamp"] > CACHE_TTL_SECONDS:
        return None
    return entry["data"]

def set_cache(key: str, data):
    _cache[key] = {"timestamp": time.time(), "data": data}

def normalize_listing(source, title, price, date, detail_url, search_url):
    return {
        "source": source,
        "title": title.strip(),
        "price": price.strip(),
        "date": date.strip(),
        "detail_url": detail_url,
        "search_url": search_url,
    }

def build_rentpad(building: str) -> List[Dict]:
    search_url = f"https://rentpad.com.ph/for-rent/taguig?q={building.replace(' ', '+')}"
    return [
        normalize_listing(
            "Rentpad",
            f"Search on Rentpad for {building}",
            "",
            "",
            search_url,
            search_url,
        )
    ]

def build_lamudi(building: str) -> List[Dict]:
    search_url = f"https://www.lamudi.com.ph/taguig-city/?q={building.replace(' ', '+')}"
    return [
        normalize_listing(
            "Lamudi",
            f"Search on Lamudi for {building}",
            "",
            "",
            search_url,
            search_url,
        )
    ]

def build_dotproperty(building: str) -> List[Dict]:
    search_url = f"https://www.dotproperty.com.ph/condos-for-rent/taguig?q={building.replace(' ', '+')}"
    return [
        normalize_listing(
            "DotProperty",
            f"Search on DotProperty for {building}",
            "",
            "",
            search_url,
            search_url,
        )
    ]

def build_carousell(building: str) -> List[Dict]:
    search_url = f"https://www.carousell.ph/search/{building.replace(' ', '%20')}?condition=for-rent"
    return [
        normalize_listing(
            "Carousell",
            f"Search on Carousell for {building}",
            "",
            "",
            search_url,
            search_url,
        )
    ]

def build_myproperty(building: str) -> List[Dict]:
    search_url = f"https://www.myproperty.ph/rent/taguig?keyword={building.replace(' ', '%20')}"
    return [
        normalize_listing(
            "MyProperty",
            f"Search on MyProperty for {building}",
            "",
            "",
            search_url,
            search_url,
        )
    ]

def run_all(building: str, max_budget: int, bedrooms: int) -> List[Dict]:
    results: List[Dict] = []
    results.extend(build_rentpad(building))
    results.extend(build_lamudi(building))
    results.extend(build_dotproperty(building))
    results.extend(build_carousell(building))
    results.extend(build_myproperty(building))
    return results

@app.get("/search")
def search(building: str, max_budget: int, bedrooms: int):
    matched = None
    for b in BUILDINGS:
        if fuzzy_match(b, building):
            matched = b
            break

    if not matched:
        return {"results": [], "error": "Building not recognized (even fuzzy)."}

    key = cache_key(matched, max_budget, bedrooms)
    cached = get_from_cache(key)
    if cached:
        return {"results": cached, "cached": True}

    results = run_all(matched, max_budget, bedrooms)
    set_cache(key, results)
    return {"results": results, "cached": False}
