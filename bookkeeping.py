from functools import lru_cache
import re
from statistics import median

import pandas as pd

from budget import _parse_amount
import integrity
from security import enforce_runtime_authorization

enforce_runtime_authorization()


TRANSACTION_ALIASES = {
    "Date": {
        "date", "transactiondate", "posteddate", "postingdate", "transdate"
    },
    "Description": {
        "description", "memo", "payee", "merchant", "name", "detail", "transaction"
    },
    "Amount": {
        "amount", "transactionamount", "value", "netamount"
    }
}

_NON_ALNUM_COL_RE = re.compile(r"[^a-z0-9]")
_MERCHANT_NOISE_RE = re.compile(r"\b(?:purchase|pending|debit|credit|card|transaction|payment|pmt|ref)\b")
_DIGITS_4_RE = re.compile(r"\b\d{4,}\b")
_ALPHA_WORDS_RE = re.compile(r"[a-z]+")

_CATEGORY_KEYWORDS = (
    ("Payroll & Wages", "Expense", ("payroll", "gusto", "adp", "paychex", "wage", "salary", "direct deposit")),
    ("Rent & Lease", "Expense", ("rent", "lease", "property", "landlord", "realty")),
    ("Shipping & Delivery", "Expense", ("ups", "fedex", "usps", "dhl", "pirate ship", "stamps", "freight", "shipping", "postage")),
    ("Utilities & Internet", "Expense", ("comcast", "verizon", "att", "spectrum", "electric", "power", "water", "gas", "utility", "internet", "telecom")),
    ("Marketing & Advertising", "Expense", ("google ads", "meta", "facebook", "linkedin", "mailchimp", "marketing", "advertising", "promo", "print")),
    ("Business Insurance", "Expense", ("insurance", "hiscox", "hartford", "progressive", "state farm", "geico", "liability", "policy")),
    ("Office Supplies & Software", "Expense", ("staples", "office depot", "quill", "amazon", "walmart", "adobe", "microsoft", "slack", "zoom", "intuit", "quickbooks", "paper", "toner", "software")),
    ("Cost of Goods Sold - Supplies", "Expense", ("uline", "grainger", "webstaurant", "wholesale", "inventory", "materials", "supply", "supplies", "packaging", "gloves")),
    ("Product & Service Sales", "Revenue", ("stripe", "square", "shopify", "paypal", "deposit", "invoice", "client", "customer", "sales", "revenue", "ach credit")),
)


class TransactionAuditError(ValueError):
    pass


def _normalize_column(value):
    return _NON_ALNUM_COL_RE.sub("", str(value).casefold())


def load_transactions(frame):
    column_lookup = {_normalize_column(column): column for column in frame.columns}
    mapping = {}
    for field, aliases in TRANSACTION_ALIASES.items():
        source = next((column_lookup[alias] for alias in aliases if alias in column_lookup), None)
        if source is None:
            raise TransactionAuditError(
                "Transaction CSV must contain date, description/payee, and amount columns."
            )
        mapping[field] = source

    transactions = frame[[mapping[field] for field in ("Date", "Description", "Amount")]].copy()
    transactions.columns = ["Date", "Description", "Amount"]
    transactions["Date"] = pd.to_datetime(transactions["Date"], errors="coerce")
    transactions["Description"] = transactions["Description"].fillna("").astype(str).str.strip()
    if pd.api.types.is_numeric_dtype(transactions["Amount"]):
        transactions["Amount"] = transactions["Amount"].astype(float)
    else:
        transactions["Amount"] = transactions["Amount"].map(_parse_amount)
    transactions = transactions.dropna(subset=["Date", "Amount"])
    transactions = transactions[transactions["Description"] != ""].copy()
    if transactions.empty:
        raise TransactionAuditError("No valid dated transactions with descriptions and amounts were found.")
    transactions["Amount"] = transactions["Amount"].astype(float)
    return transactions.sort_values("Date").reset_index(drop=True)


@lru_cache(maxsize=4096)
def _merchant_key(description):
    text = str(description).casefold()
    text = _MERCHANT_NOISE_RE.sub(" ", text)
    text = _DIGITS_4_RE.sub(" ", text)
    return " ".join(_ALPHA_WORDS_RE.findall(text))


def _prepare_keyed_transactions(transactions):
    if "MerchantKey" in transactions.columns and "AmountKey" in transactions.columns and "Sign" in transactions.columns:
        return transactions
    keyed = transactions.copy()
    keyed["MerchantKey"] = keyed["Description"].map(_merchant_key)
    keyed["AmountKey"] = keyed["Amount"].abs().round(2)
    keyed["Sign"] = keyed["Amount"].ge(0).map({True: 1, False: -1})
    return keyed[keyed["MerchantKey"].str.len() >= 3]


def _find_duplicate_charges(transactions):
    issues = []
    keyed = _prepare_keyed_transactions(transactions)

    for (merchant_key, amount_key, sign), group in keyed.groupby(["MerchantKey", "AmountKey", "Sign"], sort=False):
        if len(group) < 2:
            continue
        ordered = group.sort_values("Date") if not group["Date"].is_monotonic_increasing else group
        cluster = []
        cluster_start = None
        for transaction in ordered.to_dict("records"):
            transaction_date = transaction["Date"]
            if cluster_start is None or (transaction_date - cluster_start).days <= 2:
                if cluster_start is None:
                    cluster_start = transaction_date
                cluster.append(transaction)
            else:
                if len(cluster) >= 2:
                    issues.append(_duplicate_issue(merchant_key, amount_key, sign, cluster))
                cluster = [transaction]
                cluster_start = transaction_date
        if len(cluster) >= 2:
            issues.append(_duplicate_issue(merchant_key, amount_key, sign, cluster))
    return issues


def _duplicate_issue(merchant_key, amount, sign, transactions):
    dates = [transaction["Date"] for transaction in transactions]
    description = transactions[-1]["Description"]
    return {
        "Issue": "Possible duplicate charge",
        "Merchant": description,
        "Occurrences": len(transactions),
        "Amount": amount * sign,
        "Change": "",
        "Last date": max(dates).strftime("%Y-%m-%d"),
        "Details": f"Same merchant and amount appeared {len(transactions)} times within 2 days. Review the original statements."
    }


def _recurrence_pattern(intervals):
    if not intervals:
        return None
    med = float(median(intervals))
    patterns = (
        ("Weekly", 7, 2),
        ("Every 2 weeks", 14, 3),
        ("Monthly", 30, 5),
        ("Annual", 365, 15)
    )
    total = len(intervals)
    for name, target, tolerance in patterns:
        if abs(med - target) <= tolerance:
            consistent = sum(1 for interval in intervals if abs(interval - target) <= tolerance)
            if consistent / total >= 0.75:
                return name
    return None


def _find_recurring_charges(transactions):
    issues = []
    keyed = _prepare_keyed_transactions(transactions)

    for (merchant_key, sign), group in keyed.groupby(["MerchantKey", "Sign"], sort=False):
        if len(group) < 3:
            continue
        ordered = group.sort_values("Date") if not group["Date"].is_monotonic_increasing else group
        dates = ordered["Date"].tolist()
        intervals = [(dates[index] - dates[index - 1]).days for index in range(1, len(dates))]
        recurrence = _recurrence_pattern(intervals)
        if recurrence is None:
            continue

        amounts = ordered["AmountKey"].tolist()
        prior_amount = float(median(amounts[:-1]))
        latest_amount = amounts[-1]
        change_percent = ((latest_amount - prior_amount) / prior_amount * 100) if prior_amount else 0.0
        issue_name = "Recurring charge increased" if change_percent >= 15 else "Recurring charge"
        detail = f"Appeared {len(ordered)} times on an approximately {recurrence.casefold()} schedule."
        if issue_name == "Recurring charge increased":
            detail += " Latest amount is at least 15% above the prior median. Verify the new rate."
        else:
            detail += " No increase of 15% or more was detected in the latest charge."
        issues.append({
            "Issue": issue_name,
            "Merchant": ordered.iloc[-1]["Description"],
            "Occurrences": len(ordered),
            "Amount": latest_amount * sign,
            "Change": f"{change_percent:+.1f}%" if prior_amount else "N/A",
            "Last date": dates[-1].strftime("%Y-%m-%d"),
            "Details": detail
        })
    return issues


def audit_transactions(transactions):
    required = {"Date", "Description", "Amount"}
    if not required.issubset(transactions.columns):
        raise TransactionAuditError("Audit data must include Date, Description, and Amount columns.")
    if transactions.empty:
        raise TransactionAuditError("There are no transactions to audit.")
    keyed = _prepare_keyed_transactions(transactions)
    return sorted(
        _find_duplicate_charges(keyed) + _find_recurring_charges(keyed),
        key=lambda issue: (issue["Last date"], issue["Merchant"]),
        reverse=True
    )


def draft_vendor_action_message(issue):
    merchant = issue.get("Merchant", "Vendor")
    amount = abs(float(issue.get("Amount", 0.0)))
    last_date = issue.get("Last date", "recent statement")
    occurrences = issue.get("Occurrences", 2)
    kind = issue.get("Issue", "")
    change = issue.get("Change", "")

    if kind == "Possible duplicate charge":
        return (
            f"Subject: Duplicate Charge Inquiry — {merchant} (${amount:,.2f} on {last_date})\n\n"
            f"Hello Billing Team,\n\n"
            f"While auditing our business account statements, we noticed {occurrences} identical charges of "
            f"${amount:,.2f} from {merchant} posted around {last_date}.\n\n"
            f"Please confirm whether the additional charge(s) were processed in error and issue a refund of "
            f"${amount:,.2f} to our original payment method, or provide the corresponding invoice numbers if "
            f"they represent separate authorized orders.\n\n"
            f"Thank you,\nAccounts Payable"
        )
    if kind == "Recurring charge increased":
        return (
            f"Subject: Rate Increase Review & Account Retention — {merchant}\n\n"
            f"Hello Account Management Team,\n\n"
            f"During our quarterly vendor review, we noted that our most recent billing on {last_date} increased "
            f"by {change} to ${amount:,.2f} (across {occurrences} billing cycles).\n\n"
            f"We are actively consolidating suppliers to keep operating costs within our approved budget. "
            f"Can you restore our previous rate or apply a loyalty/volume discount so we can keep our account "
            f"with {merchant} rather than switching providers?\n\n"
            f"Thank you,\nOperations & Purchasing"
        )
    return (
        f"Subject: Recurring Subscription & Billing Audit — {merchant} (${amount:,.2f})\n\n"
        f"Hello Support Team,\n\n"
        f"We are reviewing our recurring business subscriptions ({occurrences} charges, latest ${amount:,.2f} on {last_date}). "
        f"Please send a breakdown of active seats/services on our plan and let us know what lower-tier or annual "
        f"discount options are available.\n\n"
        f"Thank you,\nOperations & Purchasing"
    )


def summarize_transactions_Into_budget(transactions, existing_df=None):
    existing_map = {}
    if existing_df is not None and not existing_df.empty:
        for row in existing_df.to_dict("records"):
            cat = str(row["Category"]).strip()
            tokens = set(_ALPHA_WORDS_RE.findall(cat.casefold())) - {"and", "the", "of", "for"}
            existing_map[cat] = {
                "Type": str(row["Type"]).strip().title(),
                "Budget": float(row["Budget"]),
                "Actual": 0.0,
                "tokens": tokens,
            }

    has_negative = (transactions["Amount"] < 0).any()
    has_positive = (transactions["Amount"] > 0).any()

    aggregated = {}
    for row in transactions.to_dict("records"):
        desc = str(row["Description"]).casefold()
        amt = float(row["Amount"])
        if amt == 0:
            continue

        if has_negative and has_positive:
            inferred_type = "Revenue" if amt > 0 else "Expense"
        else:
            inferred_type = "Expense"
        abs_amt = abs(amt)

        matched_cat = None
        matched_type = inferred_type
        desc_tokens = set(_ALPHA_WORDS_RE.findall(desc))

        for cat_name, info in existing_map.items():
            if info["tokens"] and (info["tokens"] & desc_tokens):
                matched_cat = cat_name
                matched_type = info["Type"]
                break

        if matched_cat is None:
            for std_cat, std_type, keywords in _CATEGORY_KEYWORDS:
                if any(kw in desc for kw in keywords):
                    for cat_name, info in existing_map.items():
                        if std_cat.casefold() in cat_name.casefold() or (info["tokens"] & set(_ALPHA_WORDS_RE.findall(std_cat.casefold()))):
                            matched_cat = cat_name
                            matched_type = info["Type"]
                            break
                    if matched_cat is None:
                        matched_cat = std_cat
                        matched_type = std_type
                    break

        if matched_cat is None:
            matched_cat = "Product & Service Sales" if inferred_type == "Revenue" else "General Operating Expenses"
            matched_type = inferred_type

        if matched_cat not in aggregated:
            default_budget = existing_map.get(matched_cat, {}).get("Budget", round(abs_amt, 2))
            aggregated[matched_cat] = {
                "Category": matched_cat,
                "Type": matched_type,
                "Budget": default_budget,
                "Actual": 0.0,
            }
        aggregated[matched_cat]["Actual"] = round(aggregated[matched_cat]["Actual"] + abs_amt, 2)

    for cat_name, info in existing_map.items():
        if cat_name not in aggregated:
            aggregated[cat_name] = {
                "Category": cat_name,
                "Type": info["Type"],
                "Budget": info["Budget"],
                "Actual": float(existing_df.loc[existing_df["Category"] == cat_name, "Actual"].iloc[0]),
            }

    for item in aggregated.values():
        if item["Category"] not in existing_map:
            item["Budget"] = round(item["Actual"], 2)

    return pd.DataFrame(list(aggregated.values()))


def draft_vendor_action_message(issue):
    merchant = issue.get("Merchant", "Vendor")
    amount = abs(float(issue.get("Amount", 0.0)))
    last_date = issue.get("Last date", "recent statement")
    occurrences = issue.get("Occurrences", 2)
    kind = issue.get("Issue", "")
    change = issue.get("Change", "")

    if kind == "Possible duplicate charge":
        return (
            f"Subject: Duplicate Charge Inquiry — {merchant} (${amount:,.2f} on {last_date})\n\n"
            f"Hello Billing Team,\n\n"
            f"While auditing our business account statements, we noticed {occurrences} identical charges of "
            f"${amount:,.2f} from {merchant} posted around {last_date}.\n\n"
            f"Please confirm whether the additional charge(s) were processed in error and issue a refund of "
            f"${amount:,.2f} to our original payment method, or provide the corresponding invoice numbers if "
            f"they represent separate authorized orders.\n\n"
            f"Thank you,\nAccounts Payable"
        )
    if kind == "Recurring charge increased":
        return (
            f"Subject: Rate Increase Review & Account Retention — {merchant}\n\n"
            f"Hello Account Management Team,\n\n"
            f"During our quarterly vendor review, we noted that our most recent billing on {last_date} increased "
            f"by {change} to ${amount:,.2f} (across {occurrences} billing cycles).\n\n"
            f"We are actively consolidating suppliers to keep operating costs within our approved budget. "
            f"Can you restore our previous rate or apply a loyalty/volume discount so we can keep our account "
            f"with {merchant} rather than switching providers?\n\n"
            f"Thank you,\nOperations & Purchasing"
        )
    return (
        f"Subject: Recurring Subscription & Billing Audit — {merchant} (${amount:,.2f})\n\n"
        f"Hello Support Team,\n\n"
        f"We are reviewing our recurring business subscriptions ({occurrences} charges, latest ${amount:,.2f} on {last_date}). "
        f"Please send a breakdown of active seats/services on our plan and let us know what lower-tier or annual "
        f"discount options are available.\n\n"
        f"Thank you,\nOperations & Purchasing"
    )


def summarize_transactions_Into_budget(transactions, existing_df=None):
    existing_map = {}
    if existing_df is not None and not existing_df.empty:
        for row in existing_df.to_dict("records"):
            cat = str(row["Category"]).strip()
            tokens = set(_ALPHA_WORDS_RE.findall(cat.casefold())) - {"and", "the", "of", "for"}
            existing_map[cat] = {
                "Type": str(row["Type"]).strip().title(),
                "Budget": float(row["Budget"]),
                "Actual": 0.0,
                "tokens": tokens,
            }

    has_negative = (transactions["Amount"] < 0).any()
    has_positive = (transactions["Amount"] > 0).any()

    aggregated = {}
    for row in transactions.to_dict("records"):
        desc = str(row["Description"]).casefold()
        amt = float(row["Amount"])
        if amt == 0:
            continue

        if has_negative and has_positive:
            inferred_type = "Revenue" if amt > 0 else "Expense"
        else:
            inferred_type = "Expense"
        abs_amt = abs(amt)

        matched_cat = None
        matched_type = inferred_type
        desc_tokens = set(_ALPHA_WORDS_RE.findall(desc))

        for cat_name, info in existing_map.items():
            if info["tokens"] and (info["tokens"] & desc_tokens):
                matched_cat = cat_name
                matched_type = info["Type"]
                break

        if matched_cat is None:
            for std_cat, std_type, keywords in _CATEGORY_KEYWORDS:
                if any(kw in desc for kw in keywords):
                    for cat_name, info in existing_map.items():
                        if std_cat.casefold() in cat_name.casefold() or (info["tokens"] & set(_ALPHA_WORDS_RE.findall(std_cat.casefold()))):
                            matched_cat = cat_name
                            matched_type = info["Type"]
                            break
                    if matched_cat is None:
                        matched_cat = std_cat
                        matched_type = std_type
                    break

        if matched_cat is None:
            matched_cat = "Product & Service Sales" if inferred_type == "Revenue" else "General Operating Expenses"
            matched_type = inferred_type

        if matched_cat not in aggregated:
            default_budget = existing_map.get(matched_cat, {}).get("Budget", round(abs_amt, 2))
            aggregated[matched_cat] = {
                "Category": matched_cat,
                "Type": matched_type,
                "Budget": default_budget,
                "Actual": 0.0,
            }
        aggregated[matched_cat]["Actual"] = round(aggregated[matched_cat]["Actual"] + abs_amt, 2)

    for cat_name, info in existing_map.items():
        if cat_name not in aggregated:
            aggregated[cat_name] = {
                "Category": cat_name,
                "Type": info["Type"],
                "Budget": info["Budget"],
                "Actual": float(existing_df.loc[existing_df["Category"] == cat_name, "Actual"].iloc[0]),
            }

    for item in aggregated.values():
        if item["Category"] not in existing_map:
            item["Budget"] = round(item["Actual"], 2)

    return pd.DataFrame(list(aggregated.values()))

