from difflib import SequenceMatcher
import base64
from concurrent.futures import ThreadPoolExecutor, as_completed
from functools import lru_cache
import html
import json
import math
import os
from pathlib import Path
import re
import time
from urllib.parse import quote_plus, urljoin, urlparse
from xml.etree import ElementTree

import requests
from requests.adapters import HTTPAdapter

from secure_storage import SecureStorageError, read_file, write_file
import integrity
from security import enforce_runtime_authorization

enforce_runtime_authorization()


MAX_PRODUCT_DETAIL_LOOKUPS = 4
REQUEST_TIMEOUT = 7
_CACHE_TTL_SECONDS = 600
_MAX_CACHE_ENTRIES = 32
_MAX_PAGE_INSPECT_BYTES = 384 * 1024

_HEADERS = {
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) "
        "Chrome/124.0.0.0 Safari/537.36"
    ),
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-US,en;q=0.9",
}

_SESSION = requests.Session()
_SESSION.headers.update(_HEADERS)
_ADAPTER = HTTPAdapter(pool_connections=16, pool_maxsize=24)
_SESSION.mount("https://", _ADAPTER)
_SESSION.mount("http://", _ADAPTER)
_EXECUTOR = ThreadPoolExecutor(max_workers=10)

_CATALOG_CACHE = {}

_STOP_WORDS = frozenset({
    "a", "an", "and", "at", "buy", "by", "cheap", "cheaper", "cheapest",
    "cost", "find", "for", "from", "get", "in", "item", "items", "looking",
    "low", "lower", "need", "of", "on", "option", "options", "order", "per",
    "price", "prices", "pricing", "product", "products", "purchase", "quote",
    "replacement", "replacements", "search", "shop", "supplier", "suppliers",
    "supply", "supplies", "the", "to", "unit", "vendor", "vendors", "where",
    "wholesale", "with"
})

_PACKAGING_WORDS = frozenset({
    "box", "case", "pack", "roll", "ream", "carton", "pallet", "count", "ct", "pk"
})

# Consumer/toy/novelty listings that keyword-match business queries but are never
# what a business buyer wants (e.g. "vehicle" -> die-cast toy cars). Rejected unless
# the user's own query contains the same word.
_CONSUMER_NOISE_WORDS = frozenset({
    "toy", "kid", "child", "children", "baby", "toddler", "infant", "playset",
    "play", "pretend", "plush", "doll", "diecast", "costume", "halloween", "lego",
    "pixar", "disney", "marvel", "novelty", "figurine", "puzzle", "juguete",
    "boy", "girl", "birthday",
})
# Accessory listings that merely mention the product (e.g. a "vehicle" safety label).
_ACCESSORY_WORDS = frozenset({
    "label", "sticker", "decal", "sign", "signage", "poster", "magnet", "keychain",
    "ornament", "mug", "shirt", "tshirt", "emblem",
})
_CONSUMER_NOISE_PHRASE_RE = re.compile(
    r"\bdie[\s-]?cast\b|\bhot\s+wheels\b|\bmatchbox\b|\bages?\s*\d+\s*(?:\+|-|and\s+up|years?|yrs?|months?)"
    r"|\b\d+\s*(?:years?|yrs?)\s*(?:and\s+up|\+)|\bfor\s+kids\b|\bscale\s+model\b|\b1:\d{2,3}\b",
    re.IGNORECASE,
)

_NON_PRODUCT_DOMAINS = (
    "bing.com", "google.com", "yahoo.com", "duckduckgo.com", "serpapi.com",
    "wikipedia.org", "wiktionary.org", "merriam-webster.com", "dictionary.com",
    "cambridge.org", "thefreedictionary.com", "thesaurus.com", "wikihow.com",
    "youtube.com", "reddit.com", "facebook.com", "instagram.com", "twitter.com",
    "x.com", "pinterest.com", "tiktok.com", "linkedin.com", "quora.com",
    "emojidb.org", "symbolsdb.com"
)

_SHOPIFY_SUPPLIERS = (
    ("CleanFreak", "https://www.cleanfreak.com"),
    ("WellBefore", "https://wellbefore.com"),
    ("GloveNation", "https://www.glovenation.com"),
    ("POSPaper", "https://www.pospaper.com"),
)

_NON_ALNUM_RE = re.compile(r"[^a-z0-9]+")
_TOKEN_RE = re.compile(r"[a-z0-9]+")
_TAG_RE = re.compile(r"<[^>]+>")
_PRICE_REGEX = re.compile(
    r"(?<![A-Za-z0-9])(?P<sym>US\$|CA\$|AU\$|NZ\$|USD|CAD|AUD|NZD|GBP|EUR|[$€£])\s*"
    r"(?P<amt>(?:\d{1,3}(?:,\d{3})+|\d+)\.\d{2}|(?:\d{1,3}(?:,\d{3})+|\d+))"
    r"(?:\s*/\s*(?P<unit>[A-Za-z]+))?",
    re.IGNORECASE,
)
_CURRENCY_CODE_RE = re.compile(r"\b(?:USD|CAD|AUD|NZD|GBP|EUR)\b", re.IGNORECASE)
_BING_U_RE = re.compile(r"[?&]u=a1([A-Za-z0-9_-]+)")
_BING_ALGO_RE = re.compile(r'<li class="b_algo"[^>]*>(.*?)</li>', re.DOTALL)
_BING_H2_RE = re.compile(r'<h2[^>]*>.*?<a[^>]+href="([^"]+)"[^>]*>(.*?)</a>', re.DOTALL)
_OD_TITLE_RE = re.compile(r'name="skuTitleGAData"\s+data-value="([^"]+)"')
_OD_HREF_RE = re.compile(r'href="(/a/products/\d+/[^"]+)"')
_OD_PRICE_RE = re.compile(r"\$(\d+(?:,\d{3})*\.\d{2})")
_WS_DESC_RE = re.compile(r'data-testid="itemDescription"[^>]*>(.*?)</span>', re.DOTALL)
_WS_HREF_RE = re.compile(r'<a[^>]+href="(/[^"]+\.html)"')
_WS_PRICE_BLOCK_RE = re.compile(r'data-testid="price"[^>]*>(.*?)</p>', re.DOTALL)
_WS_PRICE_RE = re.compile(r"\$(\d+(?:,\d{3})*\.\d{2})(?:\s*/\s*([A-Za-z]+))?")
_JSONLD_RE = re.compile(r'<script[^>]+type=["\']application/ld\+json["\'][^>]*>(.*?)</script>', re.DOTALL | re.IGNORECASE)
_META_PRICE_RE = re.compile(
    r'<meta[^>]+(?:property|name|itemprop)=["\'](?:product:price:amount|og:price:amount|price)["\'][^>]+content=["\']([0-9.,]+)["\']',
    re.IGNORECASE,
)
_TITLE_TAG_RE = re.compile(r"<title[^>]*>(.*?)</title>", re.DOTALL | re.IGNORECASE)


class ShoppingApiError(RuntimeError):
    pass


def _key_path():
    if os.name == "nt":
        data_directory = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        data_directory = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return data_directory / "BusinessBudgetAI" / "serpapi_key.enc"


def load_api_key():
    path = _key_path()
    if not path.exists():
        return ""
    content, encrypted = read_file(path)
    if not encrypted:
        raise SecureStorageError("The saved Shopping API key is not encrypted and was not loaded.")
    try:
        return json.loads(content.decode("utf-8")).get("api_key", "")
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise SecureStorageError("The saved Shopping API key file is invalid.") from exc


def save_api_key(api_key):
    key = api_key.strip()
    if not key:
        clear_api_key()
        return
    write_file(_key_path(), json.dumps({"api_key": key}).encode("utf-8"))


def clear_api_key():
    try:
        _key_path().unlink(missing_ok=True)
    except OSError as exc:
        raise SecureStorageError(f"Could not remove the saved Shopping API key: {exc}") from exc


@lru_cache(maxsize=64)
def _locale(region):
    normalized = _NON_ALNUM_RE.sub(" ", (region or "").casefold()).strip()
    aliases = (
        (("canada", "ca", "can"), "ca", "en"),
        (("australia", "au"), "au", "en"),
        (("new zealand", "nz"), "nz", "en"),
        (("united kingdom", "great britain", "uk", "gb"), "gb", "en"),
        (("germany", "de"), "de", "de"),
        (("france", "fr"), "fr", "fr"),
        (("united states", "united states of america", "usa", "us", "america"), "us", "en"),
    )
    us_states = {
        "alabama", "alaska", "arizona", "arkansas", "california", "colorado", "connecticut",
        "delaware", "florida", "georgia", "hawaii", "idaho", "illinois", "indiana", "iowa",
        "kansas", "kentucky", "louisiana", "maine", "maryland", "massachusetts", "michigan",
        "minnesota", "mississippi", "missouri", "montana", "nebraska", "nevada", "new hampshire",
        "new jersey", "new mexico", "new york", "north carolina", "north dakota", "ohio", "oklahoma",
        "oregon", "pennsylvania", "rhode island", "south carolina", "south dakota", "tennessee",
        "texas", "utah", "vermont", "virginia", "washington", "west virginia", "wisconsin", "wyoming",
    }
    words = set(normalized.split())
    if words & us_states or any(state in normalized for state in us_states if " " in state):
        return "us", "en"
    for names, country, language in aliases:
        if any(name in words or (" " in name and name in normalized) for name in names):
            return country, language
    return "us", "en"


def _currency_symbol(country):
    symbols = {"us": "$", "ca": "CA$", "au": "AU$", "nz": "NZ$", "gb": "£", "de": "€", "fr": "€"}
    return symbols.get(country, "$")


@lru_cache(maxsize=512)
def _normalized_tokens(text):
    tokens = []
    for token in _TOKEN_RE.findall((text or "").casefold()):
        if token.endswith("ies") and len(token) > 4:
            token = token[:-3] + "y"
        elif token.endswith("es") and len(token) > 4 and token[:-2].endswith(("x", "ch", "sh", "ss")):
            token = token[:-2]
        elif token.endswith("s") and not token.endswith("ss") and len(token) > 3:
            token = token[:-1]
        tokens.append(token)
    return tuple(tokens)


@lru_cache(maxsize=256)
def _core_search_terms(product, requirements=""):
    product_tokens = tuple(
        tok for tok in _normalized_tokens(product)
        if tok not in _STOP_WORDS and len(tok) > 1
    )
    req_tokens = tuple(
        tok for tok in _normalized_tokens(requirements)
        if tok not in _STOP_WORDS and len(tok) > 1
    )
    return product_tokens, req_tokens


_SUGGESTION_NOISE_WORDS = frozenset({
    "meaning", "definition", "wiki", "wikipedia", "reddit", "lyrics", "movie",
    "cast", "actor", "song", "game", "near", "me", "login", "portal", "careers",
    "jobs", "salary", "stock", "ticker", "news", "weather", "map", "directions",
    "vs", "versus", "meme", "quotes", "horoscope", "astrology",
})


@lru_cache(maxsize=256)
def expand_search_query(query):
    """Resolve typos, trade names, brand jargon, or unfamiliar words using live search suggestions."""
    cleaned = " ".join(_TOKEN_RE.findall((query or "").casefold()))
    if not cleaned:
        return query, ()
    orig_tokens = tuple(_normalized_tokens(cleaned))
    try:
        resp = _SESSION.get(
            "https://api.bing.com/osjson.aspx",
            params={"query": cleaned},
            timeout=2.5,
        )
        if not resp.ok:
            return query, ()
        payload = resp.json()
        suggestions = payload[1] if isinstance(payload, list) and len(payload) > 1 and isinstance(payload[1], list) else []
    except Exception:
        return query, ()

    best_expanded = None
    extra_tokens = []
    seen_extra = set(orig_tokens)

    for raw_sug in suggestions[:10]:
        sug = str(raw_sug or "").strip().casefold()
        sug_words = _TOKEN_RE.findall(sug)
        if not sug_words:
            continue
        if any(w in _SUGGESTION_NOISE_WORDS for w in sug_words):
            continue
        if _is_consumer_noise(sug, cleaned, ""):
            continue
        norm_sug = _normalized_tokens(sug)
        if not norm_sug:
            continue
        # Remove store names from suggestion if present
        filtered_words = [
            w for w in sug_words
            if w not in ("walmart", "amazon", "target", "homedepot", "lowes", "costco", "canada", "uk", "usa")
        ]
        if not filtered_words:
            continue
        candidate_phrase = " ".join(filtered_words)
        if best_expanded is None and candidate_phrase != cleaned:
            # Either a typo fix (same word count & high similarity) or a single-word trade name expansion (e.g. "gaffer" -> "gaffers tape")
            sim = SequenceMatcher(None, cleaned, candidate_phrase).ratio()
            if (len(filtered_words) == len(orig_tokens) and sim >= 0.78) or (
                len(orig_tokens) == 1 and orig_tokens[0] in norm_sug and len(filtered_words) == 2
            ):
                best_expanded = candidate_phrase
        if len(extra_tokens) < 6 and (best_expanded == candidate_phrase or orig_tokens[0] in norm_sug):
            for tok in _normalized_tokens(candidate_phrase):
                if (
                    tok not in _STOP_WORDS
                    and len(tok) > 2
                    and tok not in seen_extra
                    and not any(tok.startswith(o) and len(tok) - len(o) >= 3 for o in orig_tokens)
                ):
                    seen_extra.add(tok)
                    extra_tokens.append(tok)
                    if len(extra_tokens) >= 6:
                        break

    return (best_expanded or query), tuple(extra_tokens)


_INFLECTION_SUFFIXES = ("s", "es", "e", "ed", "er", "ers", "ing")


def _token_fuzzy_match(token, title_terms):
    if token in title_terms:
        return True
    t_len = len(token)
    if t_len < 4:
        return False
    for cand in title_terms:
        c_len = len(cand)
        if c_len < 4 or abs(t_len - c_len) > 2:
            continue
        if cand.startswith(token) and cand[t_len:] in _INFLECTION_SUFFIXES:
            return True
        if token.startswith(cand) and token[c_len:] in _INFLECTION_SUFFIXES:
            return True
        if SequenceMatcher(None, token, cand).ratio() >= 0.82:
            return True
    return False


def _is_consumer_noise(title, product, requirements=""):
    query_terms = set(_normalized_tokens(f"{product} {requirements}"))
    title_terms = set(_normalized_tokens(title))
    if (title_terms & _CONSUMER_NOISE_WORDS) - query_terms:
        return True
    if (title_terms & _ACCESSORY_WORDS) - query_terms:
        return True
    if _CONSUMER_NOISE_PHRASE_RE.search(title or "") and not _CONSUMER_NOISE_PHRASE_RE.search(f"{product} {requirements}"):
        return True
    return False


def _matches_product(title, product, requirements="", expanded_terms=()):
    title_tokens = _normalized_tokens(title)
    if not title_tokens:
        return False
    if "sample" in title_tokens and "sample" not in _normalized_tokens(product):
        return False
    if _is_consumer_noise(title, product, requirements):
        return False

    title_terms = set(title_tokens)
    all_product_terms = {
        token for token in _normalized_tokens(product)
        if token not in _STOP_WORDS and len(token) > 1 and not token.isdigit()
    }
    core_product_terms = all_product_terms - _PACKAGING_WORDS
    product_terms = core_product_terms or all_product_terms
    if not product_terms:
        product_terms = {token for token in _normalized_tokens(product) if len(token) > 1}
    if not product_terms:
        return False

    required_matches = len(product_terms) if len(product_terms) <= 2 else max(2, math.ceil(len(product_terms) * 0.65))
    fuzzy_hits = sum(1 for tok in product_terms if _token_fuzzy_match(tok, title_terms))

    if fuzzy_hits < required_matches:
        # Check if expanded/synonym terms for an unfamiliar or trade word match the title
        if expanded_terms:
            exp_hits = sum(1 for tok in expanded_terms if _token_fuzzy_match(tok, title_terms))
            if exp_hits >= 1 and (fuzzy_hits >= 1 or exp_hits >= 2):
                return True
        return False

    requirement_terms = (
        {
            token for token in _normalized_tokens(requirements)
            if token not in _STOP_WORDS and len(token) > 1
        }
        | (all_product_terms & _PACKAGING_WORDS)
    )
    if requirement_terms:
        req_hits = sum(1 for tok in requirement_terms if _token_fuzzy_match(tok, title_terms))
        if req_hits == 0 and fuzzy_hits < len(product_terms):
            return False
    return True


def _relevance_score(title, snippet, product, requirements="", expanded_terms=()):
    title_terms = set(_normalized_tokens(title))
    all_terms = title_terms | set(_normalized_tokens(snippet)) if snippet else title_terms
    prod_list, req_list = _core_search_terms(product, requirements)
    prod_set = set(prod_list)
    req_set = set(req_list)
    if not prod_set:
        return 0.0

    prod_hits = sum(1 for tok in prod_set if _token_fuzzy_match(tok, title_terms))
    if prod_hits < len(prod_set) and expanded_terms:
        exp_hits = sum(1 for tok in expanded_terms if _token_fuzzy_match(tok, title_terms))
        prod_hits = min(len(prod_set), prod_hits + exp_hits)
    title_prod_ratio = prod_hits / len(prod_set)
    title_req_ratio = (
        sum(1 for tok in req_set if _token_fuzzy_match(tok, title_terms)) / len(req_set)
        if req_set else 1.0
    )
    body_req_ratio = (
        sum(1 for tok in req_set if _token_fuzzy_match(tok, all_terms)) / len(req_set)
        if req_set else 1.0
    )
    return title_prod_ratio * 0.55 + title_req_ratio * 0.35 + body_req_ratio * 0.10


def _is_direct_merchant_link(link):
    parsed = urlparse(str(link or ""))
    host = parsed.netloc.casefold().split(":", 1)[0]
    if parsed.scheme not in ("http", "https") or not host:
        return False
    for blocked in _NON_PRODUCT_DOMAINS:
        if host == blocked or host.endswith("." + blocked):
            return False
    return True


def _merchant_name_from_url(url, fallback="Retailer"):
    host = urlparse(str(url or "")).netloc.casefold().split(":", 1)[0]
    if host.startswith("www."):
        host = host[4:]
    known = {
        "walmart.com": "Walmart",
        "walmart.ca": "Walmart Canada",
        "officedepot.com": "Office Depot",
        "webstaurantstore.com": "WebstaurantStore",
        "amazon.com": "Amazon",
        "amazon.ca": "Amazon Canada",
        "amazon.co.uk": "Amazon UK",
        "staples.com": "Staples",
        "target.com": "Target",
        "homedepot.com": "The Home Depot",
        "lowes.com": "Lowe's",
        "uline.com": "ULINE",
        "grainger.com": "Grainger",
        "quill.com": "Quill",
        "costco.com": "Costco",
        "ebay.com": "eBay",
        "cleanfreak.com": "CleanFreak",
        "wellbefore.com": "WellBefore",
        "glovenation.com": "Glove Nation",
        "pospaper.com": "POS Paper",
        "globalindustrial.com": "Global Industrial",
        "zoro.com": "Zoro",
    }
    for domain, name in known.items():
        if host == domain or host.endswith("." + domain):
            return name
    if host:
        base = host.split(".")[0]
        return base.replace("-", " ").title()
    return fallback


def _exact_offer(offer, currency):
    amount = offer.get("extracted_price")
    text_price = str(offer.get("price", "")).strip()
    if amount is None:
        match = _PRICE_REGEX.search(text_price)
        if not match:
            return None
        amount = float(match.group("amt").replace(",", ""))
    try:
        amount = float(amount)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(amount) or amount <= 0:
        return None

    symbol = _currency_symbol(currency)
    if text_price and _CURRENCY_CODE_RE.search(text_price):
        currency_codes = {"us": "USD", "ca": "CAD", "au": "AUD", "nz": "NZD", "gb": "GBP", "de": "EUR", "fr": "EUR"}
        expected_code = currency_codes.get(currency, "USD")
        if expected_code not in text_price.upper():
            return None
    elif text_price and not text_price.startswith(symbol) and not (currency in {"us", "ca", "au", "nz"} and text_price.startswith("$")):
        return None

    formatted = text_price if text_price and any(ch.isdigit() for ch in text_price) else f"{symbol}{amount:,.2f}"
    return amount, formatted


def _decode_bing_url(href):
    unescaped = html.unescape(href or "").strip()
    u_match = _BING_U_RE.search(unescaped)
    if u_match:
        encoded = u_match.group(1)
        encoded += "=" * (-len(encoded) % 4)
        try:
            decoded = base64.urlsafe_b64decode(encoded).decode("utf-8", errors="ignore")
            if decoded.startswith(("http://", "https://")):
                return decoded
        except Exception:
            pass
    return unescaped


def _extract_next_data_json(html_text):
    marker_idx = html_text.find('id="__NEXT_DATA__"')
    if marker_idx == -1:
        return None
    gt_idx = html_text.find(">", marker_idx)
    if gt_idx == -1:
        return None
    end_idx = html_text.find("</script>", gt_idx + 1)
    if end_idx == -1:
        return None
    try:
        return json.loads(html_text[gt_idx + 1:end_idx])
    except ValueError:
        return None


def _search_walmart(query, country="us"):
    domain = "www.walmart.ca" if country == "ca" else "www.walmart.com"
    symbol = _currency_symbol(country)
    url = f"https://{domain}/browse/0"
    try:
        response = _SESSION.get(url, params={"q": query, "ps": "16"}, timeout=REQUEST_TIMEOUT)
    except requests.RequestException:
        return []
    if not response.ok:
        return []

    payload = _extract_next_data_json(response.text)
    if not payload:
        return []

    stacks = (
        payload.get("props", {})
        .get("pageProps", {})
        .get("initialData", {})
        .get("searchResult", {})
        .get("itemStacks", [])
    )
    results = []
    for stack in stacks:
        for item in stack.get("items", []):
            if not isinstance(item, dict) or item.get("isOutOfStock"):
                continue
            title = str(item.get("name") or "").strip()
            canonical = str(item.get("canonicalUrl") or "").strip()
            if not title or not canonical:
                continue
            link = canonical if canonical.startswith("http") else f"https://{domain}{canonical.split('?')[0]}"
            price_val = item.get("price")
            price_info = item.get("priceInfo") or {}
            unit_price_text = ""
            for line in (price_info.get("priceDetails") or {}).get("priceLines", []):
                if line.get("lineType") == "CURRENT_PRICE" and price_val is None:
                    for val in line.get("values", []):
                        if val.get("key") == "PRICE":
                            try:
                                price_val = float(str(val.get("value", "")).replace(",", ""))
                            except ValueError:
                                pass
                elif line.get("lineType") == "UNIT_PRICE":
                    for val in line.get("values", []):
                        if val.get("value"):
                            unit_price_text = str(val["value"]).strip()

            try:
                amount = float(price_val)
            except (TypeError, ValueError):
                continue
            if not math.isfinite(amount) or amount <= 0:
                continue

            seller = str(item.get("sellerName") or "Walmart").strip()
            merchant = "Walmart" if seller.lower().startswith("walmart") else f"Walmart ({seller})"
            ship_price = price_info.get("shipPrice")
            shipping = str(ship_price).strip() if ship_price else "Free delivery available"
            price_str = f"{symbol}{amount:,.2f}"
            if unit_price_text:
                price_str = f"{price_str} ({unit_price_text})"

            results.append({
                "title": title,
                "merchant": merchant,
                "extracted_price": amount,
                "price": price_str,
                "shipping": shipping,
                "unit_price": unit_price_text,
                "link": link,
                "snippet": str(item.get("shortDescription") or ""),
            })
    return results


def _search_officedepot(query, country="us"):
    if country not in ("us", "ca"):
        return []
    symbol = _currency_symbol(country)
    try:
        response = _SESSION.get(
            "https://www.officedepot.com/a/search/",
            params={"q": query},
            timeout=REQUEST_TIMEOUT,
        )
    except requests.RequestException:
        return []
    if not response.ok:
        return []

    results = []
    parts = response.text.split('data-product-id="')[1:26]
    for part in parts:
        card = part[:10000]
        title_m = _OD_TITLE_RE.search(card)
        href_m = _OD_HREF_RE.search(card)
        if not title_m or not href_m:
            continue
        price_m = _OD_PRICE_RE.search(card)
        if not price_m:
            continue
        try:
            amount = float(price_m.group(1).replace(",", ""))
        except ValueError:
            continue
        if amount <= 0:
            continue
        title = html.unescape(title_m.group(1)).strip()
        path = html.unescape(href_m.group(1)).split("?")[0]
        results.append({
            "title": title,
            "merchant": "Office Depot",
            "extracted_price": amount,
            "price": f"{symbol}{amount:,.2f}",
            "shipping": None,
            "link": f"https://www.officedepot.com{path}",
            "snippet": "",
        })
    return results


def _search_webstaurantstore(query, country="us"):
    if country not in ("us", "ca"):
        return []
    symbol = _currency_symbol(country)
    slug = _NON_ALNUM_RE.sub("-", query.casefold()).strip("-")
    if not slug:
        return []
    url = f"https://www.webstaurantstore.com/search/{slug}.html"
    try:
        response = _SESSION.get(url, timeout=REQUEST_TIMEOUT)
    except requests.RequestException:
        return []
    if not response.ok:
        return []

    results = []
    boxes = response.text.split('id="ProductBoxContainer"')[1:25]
    for box in boxes:
        chunk = box[:8000]
        desc_m = _WS_DESC_RE.search(chunk)
        href_m = _WS_HREF_RE.search(chunk)
        if not desc_m or not href_m:
            continue
        price_block_m = _WS_PRICE_BLOCK_RE.search(chunk)
        search_zone = price_block_m.group(1) if price_block_m else chunk
        clean_zone = " ".join(html.unescape(_TAG_RE.sub(" ", search_zone)).split())
        price_m = _WS_PRICE_RE.search(clean_zone)
        if not price_m:
            continue
        try:
            amount = float(price_m.group(1).replace(",", ""))
        except ValueError:
            continue
        if amount <= 0:
            continue
        title = " ".join(html.unescape(_TAG_RE.sub(" ", desc_m.group(1))).split())
        link = f"https://www.webstaurantstore.com{html.unescape(href_m.group(1))}"
        unit_label = price_m.group(2)
        price_str = f"{symbol}{amount:,.2f}/{unit_label}" if unit_label else f"{symbol}{amount:,.2f}"
        results.append({
            "title": title,
            "merchant": "WebstaurantStore",
            "extracted_price": amount,
            "price": price_str,
            "shipping": "Plus free shipping eligible",
            "link": link,
            "snippet": "",
        })
    return results


def _search_single_shopify_supplier(supplier, query, symbol):
    merchant_name, base_url = supplier
    try:
        response = _SESSION.get(
            f"{base_url}/search/suggest.json",
            params={
                "q": query,
                "resources[type]": "product",
                "resources[limit]": "8",
            },
            timeout=5,
        )
    except requests.RequestException:
        return []
    if not response.ok or "json" not in response.headers.get("Content-Type", "").lower():
        return []
    try:
        payload = response.json()
    except ValueError:
        return []

    products = payload.get("resources", {}).get("results", {}).get("products", [])
    items = []
    for prod in products:
        if not isinstance(prod, dict) or prod.get("available") is False:
            continue
        title = str(prod.get("title") or "").strip()
        raw_url = str(prod.get("url") or "").split("?")[0].strip()
        raw_price = prod.get("price")
        if not title or not raw_url or raw_price is None:
            continue
        try:
            amount = float(str(raw_price).replace(",", "").replace("$", ""))
        except ValueError:
            continue
        if amount <= 0:
            continue
        link = raw_url if raw_url.startswith("http") else urljoin(base_url, raw_url)
        items.append({
            "title": title,
            "merchant": merchant_name,
            "extracted_price": amount,
            "price": f"{symbol}{amount:,.2f}",
            "shipping": None,
            "link": link,
            "snippet": "",
        })
    return items


def _search_shopify_suppliers(query, country="us"):
    if country not in ("us", "ca"):
        return []
    symbol = _currency_symbol(country)
    results = []
    futures = [
        _EXECUTOR.submit(_search_single_shopify_supplier, supplier, query, symbol)
        for supplier in _SHOPIFY_SUPPLIERS
    ]
    for future in as_completed(futures):
        try:
            results.extend(future.result())
        except Exception:
            pass
    return results


def _search_bing_web(query):
    results = []
    seen = set()
    try:
        rss_url = f"https://www.bing.com/search?q={quote_plus(query)}&format=rss"
        rss_resp = _SESSION.get(rss_url, timeout=REQUEST_TIMEOUT)
        if rss_resp.ok:
            document = ElementTree.fromstring(rss_resp.content)
            for item in document.findall("./channel/item"):
                title = (item.findtext("title") or "").strip()
                link = _decode_bing_url(item.findtext("link") or "")
                snippet = (item.findtext("description") or "").strip()
                if title and link.startswith(("http://", "https://")) and link not in seen:
                    seen.add(link)
                    results.append({"title": title, "url": link, "snippet": snippet})
    except Exception:
        pass

    if len(results) < 5:
        try:
            response = _SESSION.get(
                "https://www.bing.com/search",
                params={"q": query},
                timeout=REQUEST_TIMEOUT,
            )
            if response.ok:
                for match in _BING_ALGO_RE.finditer(response.text):
                    block = match.group(1)
                    h2 = _BING_H2_RE.search(block)
                    if not h2:
                        continue
                    link = _decode_bing_url(h2.group(1))
                    title = " ".join(html.unescape(_TAG_RE.sub(" ", h2.group(2))).split())
                    snippet = " ".join(html.unescape(_TAG_RE.sub(" ", block)).split())
                    if title and link.startswith(("http://", "https://")) and link not in seen:
                        seen.add(link)
                        results.append({"title": title, "url": link, "snippet": snippet})
        except requests.RequestException:
            pass

    return results


def _extract_jsonld_offers(html_text, page_url, symbol):
    offers = []
    blocks = _JSONLD_RE.findall(html_text)

    def walk(node, fallback_title=""):
        if isinstance(node, list):
            for elem in node:
                walk(elem, fallback_title)
            return
        if not isinstance(node, dict):
            return
        if "@graph" in node:
            walk(node["@graph"], fallback_title)
        node_type = str(node.get("@type") or "").lower()
        if "itemlist" in node_type and "itemlistelement" in node:
            walk(node["itemlistelement"], fallback_title)
        if "listitem" in node_type and "item" in node:
            walk(node["item"], fallback_title)

        if "product" in node_type or ("name" in node and "offers" in node):
            prod_name = html.unescape(str(node.get("name") or fallback_title)).strip()
            prod_url = str(node.get("url") or page_url).strip()
            if prod_url and not prod_url.startswith("http"):
                prod_url = urljoin(page_url, prod_url)
            raw_offers = node.get("offers")
            offer_list = raw_offers if isinstance(raw_offers, list) else ([raw_offers] if isinstance(raw_offers, dict) else [])
            for off in offer_list:
                if not isinstance(off, dict):
                    continue
                avail = str(off.get("availability") or "").lower()
                if "outofstock" in avail or "discontinued" in avail:
                    continue
                price_raw = off.get("price") or off.get("lowPrice") or (off.get("priceSpecification") or {}).get("price")
                try:
                    amount = float(str(price_raw).replace(",", "").replace("$", "").strip())
                except (TypeError, ValueError):
                    continue
                if not math.isfinite(amount) or amount <= 0:
                    continue
                off_url = str(off.get("url") or prod_url or page_url).strip()
                if off_url and not off_url.startswith("http"):
                    off_url = urljoin(page_url, off_url)
                seller = off.get("seller")
                seller_name = seller.get("name") if isinstance(seller, dict) else None
                merchant = str(seller_name or _merchant_name_from_url(off_url)).strip()
                offers.append({
                    "title": prod_name,
                    "merchant": merchant,
                    "extracted_price": amount,
                    "price": f"{symbol}{amount:,.2f}",
                    "shipping": None,
                    "link": off_url,
                    "snippet": "",
                })

    for block in blocks:
        try:
            walk(json.loads(block.strip()))
        except Exception:
            continue
    return offers


def _inspect_product_page(candidate, country="us"):
    url = candidate.get("url") or candidate.get("link") or ""
    if not _is_direct_merchant_link(url):
        return []
    symbol = _currency_symbol(country)
    try:
        with _SESSION.get(url, timeout=5, stream=True) as response:
            if not response.ok:
                return []
            chunks = []
            read_bytes = 0
            for chunk in response.iter_content(chunk_size=32768):
                if not chunk:
                    break
                chunks.append(chunk)
                read_bytes += len(chunk)
                if read_bytes >= _MAX_PAGE_INSPECT_BYTES:
                    break
            final_url = response.url
        html_text = b"".join(chunks).decode("utf-8", errors="ignore")
    except requests.RequestException:
        return []
    if not html_text:
        return []

    extracted = _extract_jsonld_offers(html_text, final_url, symbol)
    if extracted:
        return extracted

    meta_price = _META_PRICE_RE.search(html_text)
    if meta_price:
        try:
            amount = float(meta_price.group(1).replace(",", ""))
            if amount > 0:
                title_m = _TITLE_TAG_RE.search(html_text)
                page_title = (
                    " ".join(html.unescape(title_m.group(1)).split())
                    if title_m
                    else candidate.get("title", "")
                )
                return [{
                    "title": page_title,
                    "merchant": _merchant_name_from_url(final_url),
                    "extracted_price": amount,
                    "price": f"{symbol}{amount:,.2f}",
                    "shipping": None,
                    "link": final_url,
                    "snippet": candidate.get("snippet", ""),
                }]
        except ValueError:
            pass

    return []


def lookup_unknown_term_web(query):
    """Fetch live web context and expanded product terms for an unfamiliar word or phrase."""
    expanded_query, extra_terms = expand_search_query(query)
    web_results = _search_bing_web(expanded_query or query)
    snippets = []
    for item in web_results[:4]:
        title = item.get("title", "").strip()
        snip = item.get("snippet", "").strip()
        if title and snip:
            snippets.append(f"- {title}: {snip[:180]}")
    return {
        "original": query,
        "expanded_query": expanded_query,
        "related_terms": extra_terms,
        "web_snippets": snippets,
    }


def search_product_catalog(product, requirements="", region="us"):
    country, _ = _locale(region)
    cache_key = (product.strip().casefold(), (requirements or "").strip().casefold(), country)
    now = time.monotonic()
    cached = _CATALOG_CACHE.get(cache_key)
    if cached is not None and (now - cached[0]) < _CACHE_TTL_SECONDS:
        return list(cached[1]), list(cached[2])

    symbol = _currency_symbol(country)
    prod_terms, _ = _core_search_terms(product, requirements)
    core_two_word = " ".join(prod_terms[-2:]) if prod_terms else product.strip()
    full_query = " ".join(part.strip() for part in (product, requirements) if part and part.strip())
    product_only_query = product.strip()

    raw_offers = []
    web_candidates = []
    expanded_query = full_query
    expanded_terms = ()

    futures = {
        _EXECUTOR.submit(expand_search_query, full_query): "expand",
        _EXECUTOR.submit(_search_walmart, full_query, country): "walmart_full",
        _EXECUTOR.submit(_search_officedepot, full_query, country): "officedepot_full",
        _EXECUTOR.submit(_search_webstaurantstore, full_query, country): "webstaurant_full",
        _EXECUTOR.submit(_search_bing_web, core_two_word): "bing_core",
    }
    if country in ("us", "ca"):
        for supplier in _SHOPIFY_SUPPLIERS:
            futures[_EXECUTOR.submit(_search_single_shopify_supplier, supplier, core_two_word, symbol)] = "shopify"
    if full_query.casefold() != product_only_query.casefold():
        futures[_EXECUTOR.submit(_search_webstaurantstore, product_only_query, country)] = "webstaurant_prod"

    for future in as_completed(futures):
        tag = futures[future]
        try:
            res = future.result()
        except Exception:
            continue
        if tag == "expand":
            expanded_query, expanded_terms = res
        elif tag == "bing_core":
            web_candidates.extend(res)
        else:
            raw_offers.extend(res)

    # Mine consensus product terms from web candidates if the word is unfamiliar
    if not expanded_terms and web_candidates:
        freq = {}
        orig_set = set(_normalized_tokens(full_query))
        for cand in web_candidates[:8]:
            for tok in set(_normalized_tokens(cand.get("title", ""))):
                if tok not in _STOP_WORDS and tok not in orig_set and len(tok) > 3 and tok not in _CONSUMER_NOISE_WORDS:
                    freq[tok] = freq.get(tok, 0) + 1
        consensus = [tok for tok, count in sorted(freq.items(), key=lambda kv: -kv[1]) if count >= 2][:4]
        if consensus:
            expanded_terms = tuple(consensus)

    # If the user searched an unknown/misspelled/jargon word and initial results are sparse,
    # run a second-pass catalog search using the auto-discovered expanded query.
    initial_matches = sum(
        1 for offer in raw_offers
        if _matches_product(offer.get("title", ""), product, requirements, expanded_terms)
    )
    if initial_matches < 3 and expanded_query and expanded_query.casefold() != full_query.casefold():
        retry_futures = [
            _EXECUTOR.submit(_search_walmart, expanded_query, country),
            _EXECUTOR.submit(_search_webstaurantstore, expanded_query, country),
            _EXECUTOR.submit(_search_officedepot, expanded_query, country),
            _EXECUTOR.submit(_search_bing_web, expanded_query),
        ]
        for rf in as_completed(retry_futures):
            try:
                items = rf.result()
            except Exception:
                continue
            if items and isinstance(items[0], dict) and "url" in items[0] and "link" not in items[0]:
                web_candidates.extend(items)
            else:
                raw_offers.extend(items)

    inspect_targets = []
    for cand in web_candidates:
        url = cand.get("url", "")
        if not _is_direct_merchant_link(url):
            continue
        text = f"{cand.get('title', '')} {cand.get('snippet', '')}"
        matches = list(_PRICE_REGEX.finditer(text))
        if len(matches) == 1:
            try:
                amount = float(matches[0].group("amt").replace(",", ""))
                if amount > 0:
                    raw_offers.append({
                        "title": cand["title"],
                        "merchant": _merchant_name_from_url(url),
                        "extracted_price": amount,
                        "price": f"{symbol}{amount:,.2f}",
                        "shipping": None,
                        "link": url,
                        "snippet": cand.get("snippet", ""),
                    })
                    continue
            except ValueError:
                pass
        if _matches_product(cand.get("title", ""), product, requirements, expanded_terms):
            inspect_targets.append(cand)

    matched_primary_count = sum(
        1 for offer in raw_offers
        if _matches_product(offer.get("title", ""), product, requirements, expanded_terms)
    )
    if inspect_targets and matched_primary_count < 6:
        detail_futures = [
            _EXECUTOR.submit(_inspect_product_page, cand, country)
            for cand in inspect_targets[:MAX_PRODUCT_DETAIL_LOOKUPS]
        ]
        for future in as_completed(detail_futures):
            try:
                raw_offers.extend(future.result())
            except Exception:
                pass

    if len(_CATALOG_CACHE) >= _MAX_CACHE_ENTRIES:
        oldest_key = min(_CATALOG_CACHE, key=lambda k: _CATALOG_CACHE[k][0])
        _CATALOG_CACHE.pop(oldest_key, None)
    _CATALOG_CACHE[cache_key] = (now, tuple(raw_offers), tuple(web_candidates))

    return raw_offers, web_candidates


def find_cheaper_offers(product, current_unit_price, requirements="", region="us", api_key=None, include_bulk_alternatives=False):
    country, _ = _locale(region)
    full_query = " ".join(part.strip() for part in (product, requirements) if part and part.strip())
    expanded_query, expanded_terms = expand_search_query(full_query)
    raw_offers, _ = search_product_catalog(product, requirements, region)

    cheaper_offers = []
    bulk_or_higher_offers = []
    seen_links = set()

    for offer in raw_offers:
        link = offer.get("link")
        if not _is_direct_merchant_link(link) or link in seen_links:
            continue
        title = str(offer.get("title") or "").strip()
        if not _matches_product(title, product, requirements, expanded_terms) and not (
            expanded_query != full_query and _matches_product(title, expanded_query, "", expanded_terms)
        ):
            continue
        exact_price = _exact_offer(offer, country)
        if not exact_price:
            continue
        amount, price_text = exact_price

        shipping_total = offer.get("extracted_total")
        if shipping_total is None and offer.get("total"):
            parsed_total = _exact_offer({"price": offer["total"]}, country)
            if parsed_total:
                shipping_total = parsed_total[0]
        if shipping_total is None:
            shipping_amount = offer.get("shipping_extracted")
            if shipping_amount is not None:
                shipping_total = amount + float(shipping_amount)
            else:
                shipping_total = amount

        try:
            comparison_amount = float(shipping_total)
        except (TypeError, ValueError):
            comparison_amount = amount
        if not math.isfinite(comparison_amount) or comparison_amount <= 0:
            continue

        if current_unit_price is not None and current_unit_price >= 10 and comparison_amount < max(1.50, current_unit_price * 0.08):
            continue

        seen_links.add(link)
        relevance = _relevance_score(title, offer.get("snippet", ""), product, requirements, expanded_terms)
        structured = {
            "title": title,
            "merchant": offer.get("merchant") or offer.get("name") or offer.get("source") or _merchant_name_from_url(link),
            "amount": amount,
            "comparison_amount": comparison_amount,
            "price": price_text,
            "shipping": offer.get("shipping"),
            "total": offer.get("total"),
            "unit_price": offer.get("unit_price"),
            "link": link,
            "relevance": relevance,
        }
        if current_unit_price is None or comparison_amount < current_unit_price:
            cheaper_offers.append(structured)
        else:
            bulk_or_higher_offers.append(structured)

    cheaper_offers.sort(key=lambda item: (0 if item["relevance"] >= 0.75 else 1, item["comparison_amount"]))

    if include_bulk_alternatives:
        bulk_or_higher_offers.sort(key=lambda item: (0 if item["relevance"] >= 0.75 else 1, item["amount"]))
        return cheaper_offers[:10], bulk_or_higher_offers[:6]
    return cheaper_offers[:10]
