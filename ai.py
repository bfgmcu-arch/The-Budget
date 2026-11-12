import json
import math
import os
import re
import sqlite3
from pathlib import Path
from urllib.parse import urlencode, urlparse
from urllib.request import Request, urlopen
from xml.etree import ElementTree

import ollama
from config import MODEL_NAME
from security import enforce_runtime_authorization

enforce_runtime_authorization()
from shopping_api import ShoppingApiError, expand_search_query, find_cheaper_offers, load_api_key, lookup_unknown_term_web, search_product_catalog
from secure_storage import read_file as read_protected_file, write_file as write_protected_file

import threading

CHAT_HISTORY_LIMIT = 12
CHAT_HISTORY_RETAIN = 8
_OLLAMA_OPTIONS = {"num_ctx": 1024, "num_predict": 110, "temperature": 0.2, "num_batch": 256}
_FALLBACK_MODELS = (MODEL_NAME, "qwen2.5:0.5b", "smollm2:135m", "llama3.2:1b", "llama3.2:3b", "llama3.1:8b")
_ACTIVE_MODEL = MODEL_NAME
_CONVERSATION_CACHE = {}
_CONVERSATION_DB_MTIME = None


def _chat_fast(messages, options=None):
    global _ACTIVE_MODEL
    opts = _OLLAMA_OPTIONS if options is None else {**_OLLAMA_OPTIONS, **options}
    seen = set()
    last_exc = None
    for candidate in (_ACTIVE_MODEL, *_FALLBACK_MODELS):
        if not candidate or candidate in seen:
            continue
        seen.add(candidate)
        try:
            res = ollama.chat(
                model=candidate,
                options=opts,
                keep_alive="30m",
                messages=messages,
            )
            _ACTIVE_MODEL = candidate
            return res
        except Exception as exc:
            last_exc = exc
            if "not found" not in str(exc).lower():
                raise
    if last_exc:
        raise last_exc
    raise RuntimeError("No local Ollama model is available.")


def warm_up_model():
    def _warm():
        try:
            _chat_fast(
                [{"role": "user", "content": "ok"}],
                options={"num_predict": 1, "temperature": 0.0},
            )
        except Exception:
            pass

    threading.Thread(target=_warm, daemon=True).start()

BUSINESS_ADVISOR_IDENTITY = (
    "You are a concise small-business CFO advisor. "
    "Reply in 3 to 4 short, actionable bullet points (under 80 words total) based only on the supplied numbers."
)
_PRODUCT_STOP_WORDS = frozenset({
    "a", "an", "and", "for", "from", "in", "of", "or", "the", "to", "with",
    "business", "buy", "cheaper", "product", "products", "replacement", "replacements"
})
_NON_PRODUCT_RESULT_PATTERNS = tuple(re.compile(pattern, re.IGNORECASE) for pattern in (
    r"\bsoap\s+operas?\b",
    r"\bsoap[- ]operish\b",
    r"\b(?:tv|television)\s+(?:series|show|program)\b",
    r"\b(?:sitcom|episodes?|cast\s+and\s+crew|streaming|watch\s+online)\b",
    r"\bsimple\s+object\s+access\s+protocol\b",
    r"\bxml[- ]based\s+messaging\s+protocol\b",
    r"\b(?:acronym|abbreviation|definition|meaning\s+of)\b"
))
_RETAIL_DOMAINS = (
    "amazon.", "walmart.", "target.", "costco.", "homedepot.", "lowes.",
    "staples.", "officedepot.", "uline.", "grainger.", "cvs.", "walgreens.",
    "ebay.", "wayfair.", "shopify.com", "supplyhouse.com", "sustainablesupply.com",
    "webstaurantstore.com", "globalindustrial.com", "quill.com"
)
_RETAIL_TEXT_PATTERN = re.compile(
    r"\b(?:shop|buy|price|sale|retail|store|shopping|best\s+sellers?|per\s+(?:case|pack|box|unit))\b|"
    r"\$\s?\d|\b\d+(?:\.\d{1,2})?\s?(?:USD|dollars?)\b",
    re.IGNORECASE
)
_LISTING_PRICE_PATTERN = re.compile(
    r"(?<![A-Za-z0-9])(?P<currency>US\$|CA\$|AU\$|NZ\$|USD|CAD|AUD|NZD|GBP|EUR|[$€£])\s*"
    r"(?P<amount>(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d{1,2})?)"
    r"|(?<![\d.])(?P<amount_after>(?:\d{1,3}(?:,\d{3})+|\d+)(?:\.\d{1,2})?)\s*"
    r"(?P<currency_after>USD|CAD|AUD|NZD|GBP|EUR)(?![A-Za-z])",
    re.IGNORECASE
)
_CHAT_SEARCH_TRIGGER_PATTERN = re.compile(
    r"\b(?:find\s+cheaper|cheaper\s+(?:options?|alternatives?|suppliers?|vendors?|prices?)|"
    r"where\s+(?:can\s+(?:i|we)\s+)?(?:buy|get|order|source)|"
    r"search\s+(?:for\s+)?(?:cheaper|prices?|suppliers?|options?|listings?)|"
    r"how\s+much\s+(?:does|do|is|are)\s+.+?\s+cost|"
    r"price\s+(?:of|for|check|comparison)|compare\s+prices?\s+(?:for|on)|"
    r"look\s+up\s+(?:prices?|suppliers?|listings?)\s+(?:for|on)|"
    r"what\s+(?:is|are)\s+[a-z0-9]|"
    r"(?:alternatives?|substitutes?|suppliers?|vendors?)\s+(?:for|to)\s+[a-z0-9]|"
    r"(?:save|cut\s+costs?|reduce\s+spending)\s+on\s+[a-z0-9])\b",
    re.IGNORECASE
)
_CHAT_QUERY_NOISE_WORDS = frozenset({
    "a", "an", "and", "are", "at", "best", "buy", "can", "cheap", "cheaper",
    "cheapest", "check", "compare", "comparison", "cost", "costs", "current",
    "do", "does", "find", "for", "from", "get", "how", "i", "in", "is",
    "listings", "look", "looking", "low", "lower", "market", "me", "much",
    "my", "need", "of", "on", "option", "options", "order", "our", "please",
    "price", "prices", "pricing", "product", "products", "purchase", "search",
    "shop", "show", "some", "source", "supplier", "suppliers", "the", "to",
    "up", "us", "vendor", "vendors", "we", "what", "where", "wholesale", "with", "you"
})
_ALNUM_TOKEN_RE = re.compile(r"[a-z0-9]+")
_CHAT_TOKEN_RE = re.compile(r"[a-z0-9.]+")


def _product_result_score(result, product, requirements=""):
    result_text = f"{result['title']} {result['snippet']}"
    if any(pattern.search(result_text) for pattern in _NON_PRODUCT_RESULT_PATTERNS):
        return None

    def normalized_terms(text):
        terms = set()
        for token in _ALNUM_TOKEN_RE.findall(text.casefold()):
            if token.endswith("ies") and len(token) > 4:
                token = token[:-3] + "y"
            elif token.endswith("s") and not token.endswith("ss") and len(token) > 3:
                token = token[:-1]
            terms.add(token)
        return terms

    product_terms = {
        token for token in normalized_terms(product)
        if token not in _PRODUCT_STOP_WORDS and len(token) > 1
    }
    requirement_terms = {
        token for token in normalized_terms(requirements)
        if token not in _PRODUCT_STOP_WORDS and len(token) > 1
    }
    if not product_terms:
        return None
    result_terms = normalized_terms(result_text)
    matched_terms = product_terms & result_terms
    minimum_matches = 1 if len(product_terms) <= 2 else (len(product_terms) + 1) // 2
    if len(matched_terms) < minimum_matches:
        return None

    host = urlparse(result["url"]).netloc.casefold()
    is_retail_domain = any(domain in host for domain in _RETAIL_DOMAINS)
    has_retail_language = bool(_RETAIL_TEXT_PATTERN.search(result_text))
    if not is_retail_domain and not has_retail_language:
        return None

    matched_requirements = requirement_terms & result_terms
    requirement_score = len(matched_requirements) / len(requirement_terms) if requirement_terms else 0
    return (
        len(matched_terms) / len(product_terms)
        + requirement_score * 0.3
        + (0.25 if is_retail_domain else 0)
    )


def _region_currency(region):
    normalized = region.casefold()
    for markers, currency in (
        (("canada", "ca"), "CAD"),
        (("australia", "au"), "AUD"),
        (("new zealand", "nz"), "NZD"),
        (("united kingdom", "uk", "great britain", "gb"), "GBP"),
        (("europe", "eu", "germany", "france", "ireland"), "EUR"),
        (("united states", "usa", "us", "america"), "USD")
    ):
        if any(re.search(rf"\b{re.escape(marker)}\b", normalized) for marker in markers):
            return currency
    return "USD"


def _extract_exact_listing_price(result, region):
    text = f"{result['title']} {result['snippet']}"
    prices = {}
    symbols = {"$": _region_currency(region), "€": "EUR", "£": "GBP"}
    codes = {"US$": "USD", "CA$": "CAD", "AU$": "AUD", "NZ$": "NZD"}
    for match in _LISTING_PRICE_PATTERN.finditer(text):
        currency_text = match.group("currency") or match.group("currency_after")
        amount_text = match.group("amount") or match.group("amount_after")
        currency = codes.get(currency_text.upper(), symbols.get(currency_text, currency_text.upper()))
        amount = float(amount_text.replace(",", ""))
        if amount > 0:
            prices[(currency, amount)] = match.group(0).strip()
    if len(prices) != 1:
        return None
    (currency, amount), price_text = next(iter(prices.items()))
    return {"currency": currency, "amount": amount, "price_text": price_text}


def _search_product_web(query, offset=1):
    request = Request(
        "https://www.bing.com/search?" + urlencode({"q": query, "format": "rss", "first": offset}),
        headers={"User-Agent": "Mozilla/5.0 (compatible; BusinessBudgetAI/1.0)"}
    )
    with urlopen(request, timeout=15) as response:
        document = ElementTree.fromstring(response.read())
    results = []
    for item in document.findall("./channel/item"):
        title = item.findtext("title", default="").strip()
        url = item.findtext("link", default="").strip()
        snippet = item.findtext("description", default="").strip()
        if title and url.startswith(("http://", "https://")):
            results.append({"title": title, "url": url, "snippet": snippet})
    return results


def _product_search_queries(product, requirements, region):
    terms = [
        token for token in _ALNUM_TOKEN_RE.findall(product.casefold())
        if token not in _PRODUCT_STOP_WORDS
    ]
    core_product = " ".join(terms[-2:]) or product.strip()
    specification_text = f" {requirements.strip()}" if requirements.strip() else ""
    retailer_specifications = " ".join(reversed(requirements.split()))
    retailer_specification_text = f" {retailer_specifications}" if retailer_specifications else ""
    return [
        f"{product}{specification_text}",
        f"{product}{specification_text} wholesale",
        f"{core_product} cheaper alternatives",
        f"{product} equivalent product",
        f"site:amazon.com {product}{retailer_specification_text}",
        f"site:walmart.com {product}{retailer_specification_text}",
        f"site:target.com {product}{retailer_specification_text}",
        f"site:grainger.com {product}{retailer_specification_text} OR site:uline.com {product}{retailer_specification_text}"
    ]


_GENERIC_BUDGET_CHAT_WORDS = frozenset({
    "about", "actual", "actuals", "advice", "analyze", "budget", "budgeted", "business",
    "categories", "category", "cash", "change", "company", "cut", "cutting", "data",
    "department", "difference", "dollar", "dollars", "earn", "earned", "expense",
    "expenses", "financial", "flow", "forecast", "grow", "growth", "health", "help",
    "high", "highest", "improve", "income", "increase", "line", "lines", "loss", "make",
    "margin", "marketing", "meaning", "money", "month", "monthly", "most", "net", "next",
    "number", "numbers", "operating", "overall", "over", "overspend", "payroll", "percent",
    "period", "plan", "profit", "profitable", "reduce", "reducing", "rent", "report",
    "revenue", "revenues", "risk", "rois", "sales", "save", "saving", "savings", "should",
    "spend", "spending", "spent", "status", "step", "steps", "summary", "target", "targets",
    "tax", "taxes", "tell", "total", "totals", "track", "under", "variance", "warning",
    "way", "ways", "which", "why", "year", "yearly",
})


def _extract_chat_search_query(question):
    if not question:
        return None
    extra_stop = {"tell", "about", "what", "who", "sells", "alternatives", "alternative", "substitute", "substitutes", "save", "cut", "reduce", "spending"}
    tokens = [
        tok for tok in _CHAT_TOKEN_RE.findall(question.casefold())
        if tok not in _CHAT_QUERY_NOISE_WORDS and tok not in extra_stop and len(tok) > 1
    ]
    if not tokens:
        return None
    if _CHAT_SEARCH_TRIGGER_PATTERN.search(question):
        specific = [t for t in tokens if t not in _GENERIC_BUDGET_CHAT_WORDS]
        chosen = specific if specific else tokens
        return " ".join(chosen[:5])
    # Also trigger if the user mentions an unfamiliar/specific product or term not in generic budget vocabulary
    unfamiliar = [t for t in tokens if t not in _GENERIC_BUDGET_CHAT_WORDS and not t.isdigit() and len(t) >= 4]
    if 1 <= len(unfamiliar) <= 4 and len(tokens) <= 10:
        return " ".join(unfamiliar[:4])
    return None


def _build_chat_search_context(question):
    search_query = _extract_chat_search_query(question)
    if not search_query:
        return ""
    web_info = {}
    offers = []
    try:
        web_info = lookup_unknown_term_web(search_query)
    except Exception:
        web_info = {}
    try:
        offers = find_cheaper_offers(search_query, None, "", "us")
    except Exception:
        offers = []

    sections = []
    expanded = web_info.get("expanded_query") or search_query
    snippets = web_info.get("web_snippets") or []
    if snippets:
        header = f"Live web knowledge for '{search_query}'"
        if expanded.casefold() != search_query.casefold():
            header += f" (resolved to '{expanded}')"
        sections.append(header + ":\n" + "\n".join(snippets[:3]))

    if offers:
        lines = []
        for idx, offer in enumerate(offers[:5], start=1):
            shipping = f" ({offer['shipping']})" if offer.get("shipping") else ""
            lines.append(
                f"{idx}. {offer['title']} — {offer['merchant']} | Listed price: {offer['price']}{shipping} | Link: {offer['link']}"
            )
        sections.append(
            f"Live sourced product listings for '{expanded}':\n"
            + "\n".join(lines)
            + "\nWhen referencing these options, cite the exact listed prices, merchants, and full https:// links above."
        )

    return ("\n\n" + "\n\n".join(sections)) if sections else ""


def find_product_alternatives(
    product,
    current_unit_price,
    monthly_quantity,
    requirements,
    region,
    budget_context,
    conversation_history=None,
    memory=""
):
    if not budget_context or not budget_context.strip():
        raise ValueError("Load a budget with expense categories before researching products.")
    if (
        not product.strip()
        or not math.isfinite(current_unit_price)
        or not math.isfinite(monthly_quantity)
        or current_unit_price <= 0
        or monthly_quantity <= 0
    ):
        raise ValueError("Product, unit price, and monthly quantity must be valid positive values.")

    history = list(conversation_history or [])
    if len(history) > CHAT_HISTORY_LIMIT:
        older_messages = history[:-CHAT_HISTORY_RETAIN]
        memory = _summarize_chat(memory, older_messages)
        history = history[-CHAT_HISTORY_RETAIN:]

    try:
        offers, bulk_offers = find_cheaper_offers(
            product,
            current_unit_price,
            requirements,
            region,
            include_bulk_alternatives=True,
        )
    except ShoppingApiError as exc:
        answer = str(exc)
        history.extend([
            {"role": "user", "content": f"Find exact cheaper listings for {product}."},
            {"role": "assistant", "content": answer}
        ])
        return answer, memory, history

    question = (
        f"Research cheaper alternatives to {product}. Current unit price is "
        f"${current_unit_price:.2f}; we purchase {monthly_quantity:g} per month. "
        f"Required specifications: {requirements or 'None provided'}. "
        f"Region: {region or 'Not specified'}."
    )
    if offers or bulk_offers:
        current_monthly_spend = current_unit_price * monthly_quantity
        offer_lines = []
        for index, offer in enumerate(offers, start=1):
            shipping = f"; shipping: {offer['shipping']}" if offer.get("shipping") else ""
            total = f"; total: {offer['total']}" if offer.get("total") else ""
            unit_savings = max(0.0, current_unit_price - offer["comparison_amount"])
            monthly_savings = unit_savings * monthly_quantity
            annual_savings = monthly_savings * 12
            offer_lines.append(
                f"{index}. {offer['title']} — {offer['merchant']}\n"
                f"Exact listed price: {offer['price']}{shipping}{total}\n"
                f"Estimated savings: ${unit_savings:,.2f}/unit (${monthly_savings:,.2f}/month, ${annual_savings:,.2f}/year)\n"
                f"Direct product listing: {offer['link']}"
            )

        bulk_section = ""
        if bulk_offers and len(offers) < 5:
            bulk_lines = []
            for index, offer in enumerate(bulk_offers[:4], start=1):
                shipping = f"; shipping: {offer['shipping']}" if offer.get("shipping") else ""
                bulk_lines.append(
                    f"B{index}. {offer['title']} — {offer['merchant']}\n"
                    f"Listed bulk/case price: {offer['price']}{shipping}\n"
                    f"Direct product listing: {offer['link']}"
                )
            bulk_section = "\n\nAdditional bulk/case listings (verify per-unit count on store page):\n\n" + "\n\n".join(bulk_lines)

        if offer_lines:
            verified_block = (
                f"Exact lower-priced offers for {product}, compared with your current price of ${current_unit_price:,.2f} "
                f"(${current_monthly_spend:,.2f}/month):\n\n"
                + "\n\n".join(offer_lines)
                + bulk_section
            )
        else:
            verified_block = (
                f"No single-unit listing below ${current_unit_price:,.2f} was found, but these bulk/case listings were verified for {product}:\n\n"
                + bulk_section.strip()
            )

        ai_commentary = ""
        try:
            analysis_prompt = (
                f"Expense budget context:\n{budget_context}\n\n"
                f"Purchase being reviewed: {question}\n"
                f"Current monthly spend on this item: ${current_monthly_spend:,.2f} (${current_monthly_spend * 12:,.2f}/year).\n\n"
                f"Live sourced offers:\n{verified_block}\n\n"
                "Provide a concise advisor assessment (3-4 short bullet points):\n"
                "- Best-fit option(s) based on the required specifications and unit/pack value\n"
                "- How the projected monthly and annual savings affect the business's expense budget\n"
                "- Key details (pack count, shipping threshold, quality spec) to verify before ordering\n"
                "Do not invent any prices or URLs outside the sourced offers above."
            )
            response = _chat_fast(
                messages=[
                    {
                        "role": "system",
                        "content": (
                            f"{BUSINESS_ADVISOR_IDENTITY} Analyze verified supplier offers against the business budget. "
                            "Reference only prices and merchants from the supplied offers."
                        ),
                    },
                    {"role": "user", "content": analysis_prompt},
                ],
            )
            ai_commentary = (response.get("message", {}).get("content") or "").strip()
        except Exception:
            ai_commentary = ""

        if ai_commentary:
            answer = (
                f"{verified_block}\n\n"
                f"Advisor Budget & Savings Analysis:\n{ai_commentary}\n\n"
                "Confirm pack size, shipping, and required specifications on the linked store page; prices can change."
            )
        else:
            answer = (
                f"{verified_block}\n\n"
                "Confirm pack size, shipping, and required specifications on the linked store page; prices can change."
            )
    else:
        answer = (
            f"No exact, lower-priced {region} offer could be verified for {product}. "
            "No product will be shown without a structured price and direct retailer link. Try a more specific brand or model."
        )
    history.extend([
        {"role": "user", "content": question},
        {"role": "assistant", "content": answer}
    ])
    return answer, memory, history


def _conversation_database_path():
    if os.name == "nt":
        data_directory = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        data_directory = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return data_directory / "BusinessBudgetAI" / "chat_memory.sqlite3"


def _open_conversation_database(write_if_unencrypted=True):
    database_path = _conversation_database_path()
    database_path.parent.mkdir(parents=True, exist_ok=True)
    connection = sqlite3.connect(":memory:")
    try:
        encrypted = False
        if database_path.exists():
            database_bytes, encrypted = read_protected_file(database_path)
            connection.deserialize(database_bytes)
        connection.execute(
            """
            CREATE TABLE IF NOT EXISTS conversations (
                budget_signature TEXT PRIMARY KEY,
                memory TEXT NOT NULL,
                history_json TEXT NOT NULL,
                transcript_json TEXT NOT NULL,
                updated_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP
            )
            """
        )
        connection.commit()
        if not encrypted and write_if_unencrypted and database_path.exists():
            write_protected_file(database_path, connection.serialize())
        return connection
    except Exception:
        connection.close()
        raise


def _persist_conversation_database(connection):
    global _CONVERSATION_DB_MTIME
    database_path = _conversation_database_path()
    write_protected_file(database_path, connection.serialize())
    try:
        _CONVERSATION_DB_MTIME = database_path.stat().st_mtime_ns
    except OSError:
        _CONVERSATION_DB_MTIME = None


def load_conversation(budget_signature):
    global _CONVERSATION_DB_MTIME
    database_path = _conversation_database_path()
    if not database_path.exists():
        return "", [], []

    try:
        current_mtime = database_path.stat().st_mtime_ns
    except OSError:
        current_mtime = None

    if current_mtime is not None and current_mtime == _CONVERSATION_DB_MTIME and budget_signature in _CONVERSATION_CACHE:
        cached_mem, cached_hist, cached_trans = _CONVERSATION_CACHE[budget_signature]
        return cached_mem, list(cached_hist), list(cached_trans)

    connection = _open_conversation_database(write_if_unencrypted=True)
    try:
        row = connection.execute(
            "SELECT memory, history_json, transcript_json FROM conversations WHERE budget_signature = ?",
            (budget_signature,)
        ).fetchone()
    finally:
        connection.close()

    _CONVERSATION_DB_MTIME = current_mtime
    if row is None:
        _CONVERSATION_CACHE[budget_signature] = ("", [], [])
        return "", [], []

    memory = row[0]
    history = json.loads(row[1])
    transcript = [tuple(message) for message in json.loads(row[2])]
    _CONVERSATION_CACHE[budget_signature] = (memory, list(history), list(transcript))
    return memory, history, transcript


def save_conversation(budget_signature, memory, history, transcript):
    connection = _open_conversation_database()
    try:
        with connection:
            connection.execute(
                """
                INSERT INTO conversations (budget_signature, memory, history_json, transcript_json)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(budget_signature) DO UPDATE SET
                    memory = excluded.memory,
                    history_json = excluded.history_json,
                    transcript_json = excluded.transcript_json,
                    updated_at = CURRENT_TIMESTAMP
                """,
                (
                    budget_signature,
                    memory,
                    json.dumps(history),
                    json.dumps(transcript)
                )
            )
            _persist_conversation_database(connection)
            _CONVERSATION_CACHE[budget_signature] = (
                memory,
                list(history),
                [tuple(message) for message in transcript],
            )
    finally:
        connection.close()


def clear_conversation(budget_signature):
    connection = _open_conversation_database()
    try:
        with connection:
            connection.execute(
                "DELETE FROM conversations WHERE budget_signature = ?",
                (budget_signature,)
            )
        _persist_conversation_database(connection)
        _CONVERSATION_CACHE.pop(budget_signature, None)
    finally:
        connection.close()


def _compact_budget_text(df):
    rev_actual = float(df.loc[df["Type"] == "Revenue", "Actual"].sum())
    exp_actual = float(df.loc[df["Type"] == "Expense", "Actual"].sum())
    profit = rev_actual - exp_actual
    lines = [f"Totals: Revenue=${rev_actual:,.2f}, Expenses=${exp_actual:,.2f}, Net Profit=${profit:,.2f}"]
    for row in df.to_dict("records"):
        lines.append(
            f"- {row['Category']} ({row['Type']}): Budget ${row['Budget']:,.0f}, "
            f"Actual ${row['Actual']:,.0f}, Variance ${row['Variance']:+,.0f} [{row['Status']}]"
        )
    return "\n".join(lines)


def analyze(df):
    rev_actual = float(df.loc[df["Type"] == "Revenue", "Actual"].sum())
    rev_budget = float(df.loc[df["Type"] == "Revenue", "Budget"].sum())
    exp_actual = float(df.loc[df["Type"] == "Expense", "Actual"].sum())
    exp_budget = float(df.loc[df["Type"] == "Expense", "Budget"].sum())
    profit = rev_actual - exp_actual
    margin = (profit / rev_actual * 100.0) if rev_actual > 0 else 0.0
    over_rows = [
        f"{r['Category']} (${r['Actual'] - r['Budget']:,.0f} over)"
        for r in df.to_dict("records")
        if r.get("Status") == "Over Budget"
    ]
    over_text = ", ".join(over_rows) if over_rows else "None"

    snapshot_header = (
        f"• Financial Health: Net Profit ${profit:,.2f} ({margin:.1f}% margin) | "
        f"Revenue ${rev_actual:,.2f} (Budget ${rev_budget:,.2f}) | "
        f"Expenses ${exp_actual:,.2f} (Budget ${exp_budget:,.2f})\n"
        f"• Categories Over Budget: {over_text}"
    )

    prompt = (
        f"{snapshot_header}\n"
        "Give 3 short bullet points on how this business can reduce its over-budget expenses and increase profit."
    )

    response = _chat_fast(
        options={"num_predict": 95, "temperature": 0.2},
        messages=[
            {"role": "system", "content": BUSINESS_ADVISOR_IDENTITY},
            {"role": "user", "content": prompt},
        ],
    )
    ai_bullets = (response.get("message", {}).get("content") or "").strip()
    return f"{snapshot_header}\n\nAdvisor Recommendations:\n{ai_bullets}"


def ask_ai(df, question, previous_analysis=""):
    answer, _, _ = chat_with_memory(df, question, previous_analysis)
    return answer


def _summarize_chat(memory, messages):
    conversation = "\n".join(
        f"{message['role'].title()}: {message['content']}"
        for message in messages
    )
    response = _chat_fast(
        options={"num_predict": 120, "temperature": 0.1},
        messages=[
            {
                "role": "system",
                "content": (
                    f"{BUSINESS_ADVISOR_IDENTITY} Create brief memory notes for an ongoing "
                    "small-business budget conversation. Do not invent details."
                )
            },
            {
                "role": "user",
                "content": f"Existing memory:\n{memory or 'None'}\n\nOlder conversation:\n{conversation}"
            }
        ]
    )
    return response["message"]["content"]


def chat_with_memory(df, question, previous_analysis="", conversation_history=None, memory=""):
    history = list(conversation_history or [])
    if len(history) > CHAT_HISTORY_LIMIT:
        older_messages = history[:-CHAT_HISTORY_RETAIN]
        memory = _summarize_chat(memory, older_messages)
        history = history[-CHAT_HISTORY_RETAIN:]

    data = _compact_budget_text(df)
    live_search_context = _build_chat_search_context(question)
    messages = [
        {
            "role": "system",
            "content": (
                f"{BUSINESS_ADVISOR_IDENTITY} Answer concisely using the current budget and context. "
                "Never invent prices or links; if live product listings are provided, cite their exact prices and URLs."
            )
        },
        {
            "role": "user",
            "content": (
                f"Budget:\n{data}"
                + (f"\nMemory: {memory}" if memory else "")
                + f"{live_search_context}"
            )
        },
        *history[-4:],
        {"role": "user", "content": question}
    ]

    response = _chat_fast(
        messages=messages
    )

    answer = response["message"]["content"]
    history.extend([
        {"role": "user", "content": question},
        {"role": "assistant", "content": answer}
    ])
    return answer, memory, history


# Each entry: (keywords, purchasable consumable search or None, savings playbook or None).
# Keywords are matched against whole words in the category name, so "auto" does not
# match "automation". Order matters: specific categories come before generic ones.
_CATEGORY_RULES = (
    (
        ("vehicle", "vehicles", "auto", "car", "cars", "truck", "trucks", "fleet", "van", "vans",
         "fuel", "gas", "gasoline", "diesel", "mileage", "tire", "tires", "automotive"),
        ("full synthetic motor oil", "5 quart"),
        (
            "Move fuel onto a fleet fuel card with per-gallon rebates, purchase controls, and itemized receipts.",
            "Plan routes and batch trips/deliveries to cut miles driven and idle time.",
            "Keep a preventive-maintenance schedule (oil, filters, tire pressure/rotation) to protect MPG and avoid costly repairs.",
            "Re-quote commercial auto insurance with 2-3 carriers or a broker; review deductibles and drop unused coverage on older vehicles.",
            "Log business mileage so you can compare the IRS standard mileage rate against actual-expense deductions at tax time.",
            "Buy routine maintenance consumables (oil, filters, wipers) in bulk instead of paying shop markup on quick-lube visits.",
        ),
    ),
    (
        ("insurance", "premium", "premiums", "liability", "coverage"),
        None,
        (
            "Get competing quotes from 2-3 carriers or an independent broker before renewal.",
            "Bundle general liability and property into a Business Owner's Policy (BOP) where eligible.",
            "Raise deductibles on low-claim policies and remove coverage you no longer need.",
            "Ask about safety, claims-free, and pay-in-full discounts.",
        ),
    ),
    (
        ("utility", "utilities", "electric", "electricity", "power", "energy", "water", "heating", "hvac"),
        ("led light bulbs", "pack"),
        (
            "Request a free energy audit from your utility provider and check for business rebates.",
            "Switch remaining lighting to LED and add occupancy sensors / smart thermostats.",
            "Review your rate plan or compare third-party energy suppliers where your state allows it.",
        ),
    ),
    (
        ("phone", "phones", "telecom", "internet", "wireless", "cellular", "mobile", "broadband"),
        None,
        (
            "Audit every line and cancel unused numbers, devices, and add-ons.",
            "Call retention and ask for current promotional or multi-line business pricing.",
            "Consider moving desk lines to a VoIP plan.",
        ),
    ),
    (
        ("software", "saas", "subscription", "subscriptions", "license", "licenses", "hosting", "cloud", "app", "apps"),
        None,
        (
            "List every subscription and remove unused or duplicate seats/tools.",
            "Switch high-use tools to annual billing (often discounted) and downgrade over-provisioned tiers.",
            "Ask vendors for nonprofit, startup, or multi-year pricing before renewal.",
        ),
    ),
    (
        ("marketing", "advertising", "ads", "promotion", "promotions", "media"),
        None,
        (
            "Pause campaigns and channels without measurable return and move budget to the best performers.",
            "Set hard daily/monthly caps on ad platforms.",
            "Reuse content across channels instead of paying for new creative each time.",
        ),
    ),
    (
        ("rent", "lease", "leases", "occupancy", "mortgage"),
        None,
        (
            "Negotiate at renewal using comparable local listings; ask for free months or tenant-improvement credit.",
            "Sublease unused space or move to a smaller/flexible footprint.",
        ),
    ),
    (
        ("payroll", "wage", "wages", "salary", "salaries", "labor", "staff", "staffing", "contractor", "contractors", "benefits"),
        None,
        (
            "Align schedules to demand to reduce overtime and idle hours.",
            "Cross-train staff so fewer people cover more roles during slow periods.",
            "Review benefits plans and contractor rates annually.",
        ),
    ),
    (
        ("legal", "accounting", "professional", "consulting", "bookkeeping", "attorney", "cpa"),
        None,
        (
            "Ask for fixed-fee or capped engagements instead of open hourly billing.",
            "Batch requests and bring routine bookkeeping in-house with software.",
        ),
    ),
    (
        ("travel", "airfare", "hotel", "hotels", "lodging", "meals", "entertainment"),
        None,
        (
            "Book further in advance and set a written travel/meal policy with per-diem caps.",
            "Replace non-essential trips with video meetings.",
        ),
    ),
    (
        ("bank", "banking", "fee", "fees", "processing", "interest", "loan", "loans", "credit"),
        None,
        (
            "Ask your card processor for an interchange-plus rate review and compare at least one competitor quote.",
            "Move to a no-fee business checking account and refinance high-interest debt when possible.",
        ),
    ),
    (("tax", "taxes", "depreciation", "amortization"), None, None),
    (("office", "stationery", "paper", "printing", "admin"), ("copy paper", "8.5x11 case"), None),
    (("shipping", "delivery", "freight", "postage", "packaging", "fulfillment"), ("shipping boxes", "corrugated pack"), None),
    (("cleaning", "janitorial", "sanitation", "facility", "facilities", "maintenance"), ("paper towels", "bulk roll"), None),
    (("safety", "ppe", "medical", "gloves"), ("nitrile gloves", "powder free box"), None),
    (("pos", "receipt", "receipts", "register", "merchant"), ("thermal paper", "rolls"), None),
    (("cogs", "goods", "supplies", "inventory", "materials", "production"), ("nitrile gloves", "box 100"), None),
)

_CATEGORY_WORD_RE = re.compile(r"[a-z0-9]+")


def _match_category_rule(category_name):
    words = set(_CATEGORY_WORD_RE.findall((category_name or "").casefold()))
    if not words:
        return None
    for keywords, search, playbook in _CATEGORY_RULES:
        if words.intersection(keywords):
            return search, playbook
    return None


_GENERIC_CATEGORY_FILLER = frozenset({
    "expense", "expenses", "cost", "costs", "budget", "department", "general",
    "misc", "miscellaneous", "other", "account", "line", "item", "items",
    "category", "business", "operating", "operations", "monthly", "annual",
    "random", "thing", "things", "unknown", "custom",
})


def category_to_supply_search(category_name):
    """Return a (product, requirements) consumable search for a budget category, or None.

    Matches known rules first; for unfamiliar category names, strips generic accounting
    filler words and resolves the term via live search expansion so custom supplies work.
    """
    rule = _match_category_rule(category_name)
    if rule is not None:
        return rule[0]
    words = [
        w for w in _CATEGORY_WORD_RE.findall((category_name or "").casefold())
        if w not in _GENERIC_CATEGORY_FILLER and len(w) > 2 and not w.isdigit()
    ]
    if not words:
        return None
    raw_phrase = " ".join(words[:4])
    expanded, extra = expand_search_query(raw_phrase)
    return (expanded or raw_phrase, "")


def category_savings_playbook(category_name):
    """Return proven non-retail savings levers for service-type costs, or None."""
    rule = _match_category_rule(category_name)
    return rule[1] if rule else None
