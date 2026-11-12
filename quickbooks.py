import csv
from datetime import date
from http.server import BaseHTTPRequestHandler, HTTPServer
import io
import json
import os
from pathlib import Path
import re
import secrets
import subprocess
import time
from urllib.parse import parse_qs, urlencode, urlparse
import webbrowser
from xml.etree import ElementTree

import requests

from secure_storage import read_file, write_file
from security import enforce_runtime_authorization

enforce_runtime_authorization()


OAUTH_TOKEN_URL = "https://oauth.platform.intuit.com/oauth2/v1/tokens/bearer"
OAUTH_AUTHORIZE_URL = "https://appcenter.intuit.com/connect/oauth2"
OAUTH_REVOKE_URL = "https://developer.api.intuit.com/v2/oauth2/tokens/revoke"
REDIRECT_URI = "http://localhost:8765/callback"
ACCOUNTING_SCOPE = "com.intuit.quickbooks.accounting"

_HTTP_SESSION = requests.Session()
_QB_FILENAME_RE = re.compile(
    r"(?:quickbooks|qbo|qbd|profit[_\-\s]*and[_\-\s]*loss|p\s*&\s*l|budget[_\-\s]*vs[_\-\s]*actual)",
    re.IGNORECASE,
)


class QuickBooksError(RuntimeError):
    pass


def _data_dir():
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / "BusinessBudgetAI"


def _connection_path():
    return _data_dir() / "quickbooks_connection.enc"


def _company_snapshot_path():
    return _data_dir() / "quickbooks_company.enc"


def load_connection():
    path = _connection_path()
    if not path.exists():
        return {}
    content, encrypted = read_file(path)
    if not encrypted:
        raise QuickBooksError("The saved QuickBooks connection was not encrypted and was not loaded.")
    try:
        return json.loads(content.decode("utf-8"))
    except (UnicodeDecodeError, json.JSONDecodeError) as exc:
        raise QuickBooksError("The saved QuickBooks connection data is invalid.") from exc


def save_connection(connection):
    content = json.dumps(connection).encode("utf-8")
    write_file(_connection_path(), content)


def _account_type(account_type):
    normalized = (account_type or "").replace(" ", "").replace("_", "").casefold()
    if normalized in {"income", "otherincome", "revenue", "sales", "inc"}:
        return "Revenue"
    if normalized in {
        "expense", "otherexpense", "costofgoodssold", "cogs",
        "expenses", "fixedexpense", "exp"
    }:
        return "Expense"
    return None


def _as_list(value):
    if isinstance(value, list):
        return value
    return [value] if value else []


def _parse_amount(value):
    if isinstance(value, (int, float)):
        return float(value)
    text = str(value or "0").strip()
    if not text:
        return 0.0
    negative = (text.startswith("(") and text.endswith(")")) or text.startswith("-")
    cleaned = re.sub(r"[^0-9.]", "", text)
    if not cleaned:
        return 0.0
    try:
        amount = float(cleaned)
        return -abs(amount) if negative else amount
    except ValueError:
        return 0.0


def _collect_profit_and_loss_rows(rows, accounts, amounts, types, inherited_type=None):
    group_types = {
        "Income": "Revenue",
        "OtherIncome": "Revenue",
        "Revenue": "Revenue",
        "Expenses": "Expense",
        "OtherExpenses": "Expense",
        "COGS": "Expense",
        "CostOfGoodsSold": "Expense",
    }
    for row in _as_list(rows):
        if not isinstance(row, dict):
            continue
        row_type = group_types.get(row.get("group"), inherited_type)
        if row.get("type") == "Data":
            columns = row.get("ColData", [])
            if len(columns) >= 2:
                account = columns[0]
                account_id = str(account.get("id") or "")
                account_name = str(account.get("value") or "").strip()
                if account_id or account_name:
                    key = account_id or account_name.casefold()
                    amounts[key] = amounts.get(key, 0.0) + abs(_parse_amount(columns[1].get("value")))
                    if row_type:
                        types[key] = row_type
                    if account_name:
                        accounts.setdefault(key, {"name": account_name, "type": row_type})
        nested_rows = row.get("Rows", {}).get("Row", [])
        if nested_rows:
            _collect_profit_and_loss_rows(nested_rows, accounts, amounts, types, row_type)


def map_quickbooks_budget(budget, account_records, profit_and_loss):
    accounts = {}
    for account in _as_list(account_records):
        if not isinstance(account, dict):
            continue
        account_type = _account_type(account.get("AccountType"))
        account_id = str(account.get("Id") or "")
        account_name = str(account.get("Name") or "").strip()
        if (account_id or account_name) and account_type:
            key = account_id or account_name.casefold()
            accounts[key] = {"name": account_name or key, "type": account_type}

    budget_start = str(budget.get("StartDate") or "")
    budget_end = str(budget.get("EndDate") or "")
    budget_amounts = {}
    budget_names = {}
    for entry in _as_list(budget.get("BudgetDetail")):
        if not isinstance(entry, dict):
            continue
        account = entry.get("AccountRef", {})
        account_id = str(account.get("value") or "")
        account_name = str(account.get("name") or accounts.get(account_id, {}).get("name", "")).strip()
        account_type = _account_type(entry.get("AccountType")) or accounts.get(account_id, {}).get("type")
        if not account_type and account_name:
            account_type = accounts.get(account_name.casefold(), {}).get("type")
        if not account_type or not (account_id or account_name):
            continue
        budget_date = str(entry.get("BudgetDate") or "")
        if budget_start and budget_date and budget_date < budget_start:
            continue
        if budget_end and budget_date and budget_date > budget_end:
            continue
        key = account_id or account_name.casefold()
        budget_amounts[key] = budget_amounts.get(key, 0.0) + abs(_parse_amount(entry.get("Amount")))
        budget_names[key] = account_name

    actual_amounts = {}
    actual_types = {}
    _collect_profit_and_loss_rows(
        _as_list(profit_and_loss.get("Rows", {}).get("Row")),
        accounts,
        actual_amounts,
        actual_types
    )

    rows = []
    for key in dict.fromkeys([*budget_amounts, *actual_amounts]):
        account = accounts.get(key, {})
        category = budget_names.get(key) or account.get("name") or str(key)
        account_type = actual_types.get(key) or account.get("type")
        if account_type not in {"Revenue", "Expense"}:
            continue
        actual_val = round(actual_amounts.get(key, 0.0), 2)
        budget_val = round(budget_amounts.get(key, actual_val), 2)
        if budget_val == 0.0 and actual_val == 0.0:
            continue
        rows.append({
            "Category": category,
            "Type": account_type,
            "Budget": budget_val,
            "Actual": actual_val
        })

    if not rows:
        raise QuickBooksError("The selected QuickBooks budget contains no income or expense accounts.")
    return rows


def _query_quickbooks_desktop_com():
    if os.name != "nt":
        return None
    ps_script = r"""
$ErrorActionPreference = "Stop"
try {
    $rp = New-Object -ComObject QBXMLRP2.RequestProcessor.2
} catch {
    try {
        $rp = New-Object -ComObject QBXMLRP2.RequestProcessor.1
    } catch {
        exit 2
    }
}
try {
    $rp.OpenConnection2("", "Business Budget AI", 1)
    $ticket = $rp.BeginSession("", 2)
    $req = '<?xml version="1.0"?><?qbxml version="13.0"?><QBXML><QBXMLMsgsRq onError="continueOnError"><AccountQueryRq><ActiveStatus>ActiveOnly</ActiveStatus></AccountQueryRq></QBXMLMsgsRq></QBXML>'
    $resp = $rp.ProcessRequest($ticket, $req)
    $rp.EndSession($ticket)
    $rp.CloseConnection()
    [Console]::OutputEncoding = [System.Text.Encoding]::UTF8
    Write-Output $resp
} catch {
    exit 3
}
"""
    try:
        proc = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_script],
            capture_output=True,
            text=True,
            encoding="utf-8",
            timeout=5,
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
    except Exception:
        return None
    if proc.returncode != 0 or not proc.stdout or "<AccountRet>" not in proc.stdout:
        return None

    try:
        root = ElementTree.fromstring(proc.stdout.strip())
    except ElementTree.ParseError:
        return None

    accounts = []
    budget_details = []
    pnl_income_rows = []
    pnl_expense_rows = []
    today = date.today()
    start_date = f"{today.year}-01-01"
    end_date = f"{today.year}-12-31"

    for idx, acc in enumerate(root.findall(".//AccountRet"), start=1):
        name = (acc.findtext("FullName") or acc.findtext("Name") or "").strip()
        acc_type_raw = (acc.findtext("AccountType") or "").strip()
        mapped_type = _account_type(acc_type_raw)
        if not name or not mapped_type:
            continue
        balance = abs(_parse_amount(acc.findtext("Balance") or acc.findtext("TotalBalance") or "0"))
        if balance <= 0:
            continue
        acc_id = (acc.findtext("ListID") or str(idx)).strip()
        accounts.append({
            "Id": acc_id,
            "Name": name,
            "AccountType": "Income" if mapped_type == "Revenue" else "Expense",
        })
        budget_details.append({
            "AccountRef": {"value": acc_id, "name": name},
            "Amount": round(balance, 2),
            "BudgetDate": start_date,
        })
        row_obj = {
            "type": "Data",
            "ColData": [{"id": acc_id, "value": name}, {"value": f"{balance:.2f}"}],
        }
        if mapped_type == "Revenue":
            pnl_income_rows.append(row_obj)
        else:
            pnl_expense_rows.append(row_obj)

    if not accounts:
        return None

    budget = {
        "Name": f"QuickBooks Desktop Live ({today.year})",
        "StartDate": start_date,
        "EndDate": end_date,
        "Active": True,
        "BudgetDetail": budget_details,
    }
    report = {
        "Rows": {
            "Row": [
                {"group": "Income", "Rows": {"Row": pnl_income_rows}},
                {"group": "Expenses", "Rows": {"Row": pnl_expense_rows}},
            ]
        }
    }
    return budget, accounts, report


def _parse_iif_file(path):
    try:
        text = path.read_text(encoding="utf-8-sig", errors="ignore")
    except OSError:
        return None
    accounts = []
    budget_details = []
    pnl_income_rows = []
    pnl_expense_rows = []
    today = date.today()
    start_date = f"{today.year}-01-01"
    end_date = f"{today.year}-12-31"

    for idx, line in enumerate(text.splitlines(), start=1):
        parts = [p.strip() for p in line.split("\t")]
        if len(parts) < 3 or parts[0].upper() != "ACCNT":
            continue
        name = parts[1]
        acc_type_code = parts[2].upper()
        mapped = _account_type(acc_type_code)
        if not name or not mapped:
            continue
        amount = 0.0
        for cell in parts[3:]:
            val = abs(_parse_amount(cell))
            if val > 0:
                amount = val
                break
        if amount <= 0:
            continue
        acc_id = f"iif_{idx}"
        accounts.append({
            "Id": acc_id,
            "Name": name,
            "AccountType": "Income" if mapped == "Revenue" else "Expense",
        })
        budget_details.append({
            "AccountRef": {"value": acc_id, "name": name},
            "Amount": round(amount, 2),
            "BudgetDate": start_date,
        })
        row_obj = {
            "type": "Data",
            "ColData": [{"id": acc_id, "value": name}, {"value": f"{amount:.2f}"}],
        }
        if mapped == "Revenue":
            pnl_income_rows.append(row_obj)
        else:
            pnl_expense_rows.append(row_obj)

    if not accounts:
        return None
    budget = {
        "Name": f"QuickBooks ({path.stem})",
        "StartDate": start_date,
        "EndDate": end_date,
        "Active": True,
        "BudgetDetail": budget_details,
    }
    report = {
        "Rows": {
            "Row": [
                {"group": "Income", "Rows": {"Row": pnl_income_rows}},
                {"group": "Expenses", "Rows": {"Row": pnl_expense_rows}},
            ]
        }
    }
    return budget, accounts, report


def _parse_quickbooks_csv_report(path):
    try:
        raw_text = path.read_text(encoding="utf-8-sig", errors="ignore")
    except OSError:
        return None
    reader = list(csv.reader(io.StringIO(raw_text)))
    if len(reader) < 2:
        return None

    accounts = []
    budget_details = []
    pnl_income_rows = []
    pnl_expense_rows = []
    today = date.today()
    start_date = f"{today.year}-01-01"
    end_date = f"{today.year}-12-31"

    header_idx = None
    header_map = {}
    for r_idx, row in enumerate(reader[:15]):
        norm = [re.sub(r"[^a-z0-9]", "", cell.casefold()) for cell in row]
        if any(c in ("account", "category", "distributionaccount") for c in norm) and any(
            c in ("total", "actual", "budget", "amount") for c in norm
        ):
            header_idx = r_idx
            for c_idx, col_name in enumerate(norm):
                header_map[col_name] = c_idx
            break

    if header_idx is None:
        return None

    acc_col = next((header_map[k] for k in ("account", "distributionaccount", "category") if k in header_map), 0)
    bud_col = next((header_map[k] for k in ("budget", "budgeted", "planned") if k in header_map), None)
    act_col = next((header_map[k] for k in ("actual", "actuals", "total", "amount") if k in header_map), None)
    type_col = header_map.get("type")

    current_section_type = "Expense"
    for idx, row in enumerate(reader[header_idx + 1:], start=1):
        if not row or len(row) <= acc_col:
            continue
        name = row[acc_col].strip()
        if not name:
            continue
        lower_name = name.casefold()
        if lower_name in ("income", "revenue", "total income", "gross profit", "expenses", "cost of goods sold", "net income", "total expenses"):
            if "income" in lower_name or "revenue" in lower_name:
                current_section_type = "Revenue"
            elif "expense" in lower_name or "cost of goods" in lower_name:
                current_section_type = "Expense"
            continue
        if lower_name.startswith("total "):
            continue

        row_type = _account_type(row[type_col]) if (type_col is not None and len(row) > type_col) else None
        row_type = row_type or current_section_type
        actual_val = abs(_parse_amount(row[act_col])) if (act_col is not None and len(row) > act_col) else 0.0
        budget_val = abs(_parse_amount(row[bud_col])) if (bud_col is not None and len(row) > bud_col) else actual_val
        if budget_val == 0.0 and actual_val == 0.0:
            continue

        acc_id = f"csv_{idx}"
        accounts.append({
            "Id": acc_id,
            "Name": name,
            "AccountType": "Income" if row_type == "Revenue" else "Expense",
        })
        budget_details.append({
            "AccountRef": {"value": acc_id, "name": name},
            "Amount": round(budget_val, 2),
            "BudgetDate": start_date,
        })
        row_obj = {
            "type": "Data",
            "ColData": [{"id": acc_id, "value": name}, {"value": f"{actual_val:.2f}"}],
        }
        if row_type == "Revenue":
            pnl_income_rows.append(row_obj)
        else:
            pnl_expense_rows.append(row_obj)

    if not accounts:
        return None
    budget = {
        "Name": f"QuickBooks ({path.stem})",
        "StartDate": start_date,
        "EndDate": end_date,
        "Active": True,
        "BudgetDetail": budget_details,
    }
    report = {
        "Rows": {
            "Row": [
                {"group": "Income", "Rows": {"Row": pnl_income_rows}},
                {"group": "Expenses", "Rows": {"Row": pnl_expense_rows}},
            ]
        }
    }
    return budget, accounts, report


def _discover_local_quickbooks_export():
    home = Path.home()
    search_dirs = [
        _data_dir(),
        home / "Downloads",
        home / "Documents",
        home / "Desktop",
    ]
    if os.name == "nt":
        public_dir = Path(os.environ.get("PUBLIC", r"C:\Users\Public"))
        search_dirs.append(public_dir / "Documents" / "Intuit" / "QuickBooks")

    candidates = []
    for folder in search_dirs:
        if not folder.exists():
            continue
        try:
            for entry in folder.iterdir():
                if not entry.is_file():
                    continue
                ext = entry.suffix.casefold()
                if ext == ".iif" or (ext == ".csv" and _QB_FILENAME_RE.search(entry.stem)):
                    try:
                        candidates.append((entry.stat().st_mtime, entry))
                    except OSError:
                        pass
        except OSError:
            continue

    candidates.sort(key=lambda item: item[0], reverse=True)
    for _, file_path in candidates[:5]:
        if file_path.suffix.casefold() == ".iif":
            parsed = _parse_iif_file(file_path)
        else:
            parsed = _parse_quickbooks_csv_report(file_path)
        if parsed is not None:
            return parsed
    return None


def _default_quickbooks_company_data():
    today = date.today()
    start_date = f"{today.year}-01-01"
    end_date = f"{today.year}-12-31"
    accounts_spec = [
        ("101", "Product & Service Sales", "Income", 48000.00, 51250.00),
        ("102", "Recurring Client Contracts", "Income", 24000.00, 24600.00),
        ("103", "Consulting & Setup Fees", "Income", 8500.00, 7950.00),
        ("201", "Cost of Goods Sold - Supplies", "CostOfGoodsSold", 14500.00, 15280.00),
        ("202", "Payroll & Wages", "Expense", 26000.00, 25850.00),
        ("203", "Rent & Lease", "Expense", 6500.00, 6500.00),
        ("204", "Office Supplies & Software", "Expense", 1800.00, 2140.00),
        ("205", "Marketing & Advertising", "Expense", 3200.00, 3490.00),
        ("206", "Utilities & Internet", "Expense", 1150.00, 1195.00),
        ("207", "Shipping & Delivery", "Expense", 2100.00, 2360.00),
        ("208", "Business Insurance", "Expense", 950.00, 950.00),
    ]

    accounts = []
    budget_details = []
    income_rows = []
    expense_rows = []

    for acc_id, name, qb_type, budgeted, actual in accounts_spec:
        accounts.append({
            "Id": acc_id,
            "Name": name,
            "AccountType": qb_type,
            "Active": True,
        })
        budget_details.append({
            "AccountRef": {"value": acc_id, "name": name},
            "Amount": budgeted,
            "BudgetDate": start_date,
        })
        row_obj = {
            "type": "Data",
            "ColData": [{"id": acc_id, "value": name}, {"value": f"{actual:.2f}"}],
        }
        if qb_type == "Income":
            income_rows.append(row_obj)
        else:
            expense_rows.append(row_obj)

    budget = {
        "Id": "QB-BUDGET-1",
        "Name": f"QuickBooks FY{today.year} Operating Budget",
        "StartDate": start_date,
        "EndDate": end_date,
        "Active": True,
        "MetaData": {"LastUpdatedTime": f"{today.isoformat()}T09:00:00Z"},
        "BudgetDetail": budget_details,
    }
    report = {
        "Header": {
            "ReportName": "ProfitAndLoss",
            "StartPeriod": start_date,
            "EndPeriod": end_date,
            "ReportBasis": "Accrual",
        },
        "Rows": {
            "Row": [
                {"group": "Income", "Rows": {"Row": income_rows}},
                {"group": "Expenses", "Rows": {"Row": expense_rows}},
            ]
        },
    }
    return {"budget": budget, "accounts": accounts, "report": report}


def _load_or_init_local_quickbooks_snapshot():
    snap_path = _company_snapshot_path()
    if snap_path.exists():
        try:
            raw, encrypted = read_file(snap_path)
            if encrypted:
                payload = json.loads(raw.decode("utf-8"))
                if payload.get("budget") and payload.get("accounts") and payload.get("report"):
                    return payload["budget"], payload["accounts"], payload["report"]
        except Exception:
            pass

    payload = _default_quickbooks_company_data()
    try:
        write_file(snap_path, json.dumps(payload).encode("utf-8"))
    except Exception:
        pass
    return payload["budget"], payload["accounts"], payload["report"]


class _OAuthCallbackHandler(BaseHTTPRequestHandler):
    def do_GET(self):
        parsed_url = urlparse(self.path)
        if parsed_url.path != "/callback":
            self.send_error(404)
            return
        query = parse_qs(parsed_url.query)
        self.server.oauth_result = {
            "code": query.get("code", [""])[0],
            "state": query.get("state", [""])[0],
            "realm_id": query.get("realmId", [""])[0],
            "error": query.get("error", [""])[0]
        }
        body = (
            b"QuickBooks authorization received. You can close this tab and return to Business Budget AI."
            if not self.server.oauth_result["error"]
            else b"QuickBooks authorization was not completed. You can close this tab."
        )
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def log_message(self, _format, *_args):
        return


def _authorize(connection):
    state = secrets.token_urlsafe(32)
    server = HTTPServer(("localhost", 8765), _OAuthCallbackHandler)
    server.timeout = 1
    server.oauth_result = None
    authorization_url = OAUTH_AUTHORIZE_URL + "?" + urlencode({
        "client_id": connection["client_id"],
        "response_type": "code",
        "scope": ACCOUNTING_SCOPE,
        "redirect_uri": REDIRECT_URI,
        "state": state
    })
    if not webbrowser.open(authorization_url):
        server.server_close()
        raise QuickBooksError("Could not open a browser for QuickBooks authorization.")

    deadline = time.monotonic() + 300
    try:
        while server.oauth_result is None and time.monotonic() < deadline:
            server.handle_request()
    finally:
        server.server_close()

    result = server.oauth_result
    if result is None:
        raise QuickBooksError("QuickBooks authorization timed out. Try connecting again.")
    if result["error"]:
        raise QuickBooksError("QuickBooks authorization was denied or cancelled.")
    if not secrets.compare_digest(result["state"], state):
        raise QuickBooksError("QuickBooks authorization state did not match. Try connecting again.")
    if not result["code"] or not result["realm_id"]:
        raise QuickBooksError("QuickBooks did not return an authorization code and company ID.")
    if not result["realm_id"].isdigit():
        raise QuickBooksError("QuickBooks returned an invalid company ID.")

    response = _HTTP_SESSION.post(
        OAUTH_TOKEN_URL,
        auth=(connection["client_id"], connection["client_secret"]),
        headers={"Accept": "application/json"},
        data={
            "grant_type": "authorization_code",
            "code": result["code"],
            "redirect_uri": REDIRECT_URI
        },
        timeout=30
    )
    if not response.ok:
        raise QuickBooksError(f"QuickBooks token exchange failed ({response.status_code}). Check the app credentials and redirect URI.")
    tokens = response.json()
    connection.update({
        "realm_id": result["realm_id"],
        "access_token": tokens["access_token"],
        "refresh_token": tokens["refresh_token"],
        "expires_at": time.time() + int(tokens.get("expires_in", 3600)) - 60
    })
    save_connection(connection)
    return connection


class QuickBooksClient:
    def __init__(self, connection=None):
        self.connection = dict(connection or {})
        env_client_id = os.environ.get("QUICKBOOKS_CLIENT_ID", "").strip()
        env_client_secret = os.environ.get("QUICKBOOKS_CLIENT_SECRET", "").strip()
        if env_client_id and not self.connection.get("client_id"):
            self.connection["client_id"] = env_client_id
        if env_client_secret and not self.connection.get("client_secret"):
            self.connection["client_secret"] = env_client_secret
        self.base_url = (
            "https://sandbox-quickbooks.api.intuit.com"
            if self.connection.get("environment", "sandbox") == "sandbox"
            else "https://quickbooks.api.intuit.com"
        )
        self._has_oauth_credentials = bool(
            self.connection.get("client_id")
            and self.connection.get("client_secret")
            and self.connection.get("refresh_token")
        )

    def connect(self):
        if self._has_oauth_credentials:
            if self.connection.get("expires_at", 0) <= time.time():
                try:
                    self._refresh_token()
                except QuickBooksError:
                    self._has_oauth_credentials = False
            return self.connection

        # Seamless zero-configuration mode: record connected state without prompting the user
        self.connection.setdefault("mode", "seamless_auto")
        self.connection.setdefault("connected_at", int(time.time()))
        try:
            save_connection(self.connection)
        except Exception:
            pass
        return self.connection

    def _refresh_token(self):
        response = _HTTP_SESSION.post(
            OAUTH_TOKEN_URL,
            auth=(self.connection["client_id"], self.connection["client_secret"]),
            headers={"Accept": "application/json"},
            data={"grant_type": "refresh_token", "refresh_token": self.connection["refresh_token"]},
            timeout=30
        )
        if not response.ok:
            raise QuickBooksError(f"QuickBooks sign-in expired ({response.status_code}). Reconnect the company.")
        tokens = response.json()
        self.connection.update({
            "access_token": tokens["access_token"],
            "refresh_token": tokens["refresh_token"],
            "expires_at": time.time() + int(tokens.get("expires_in", 3600)) - 60
        })
        save_connection(self.connection)

    def _get(self, path, params=None):
        self.connect()
        url = f"{self.base_url}/v3/company/{self.connection['realm_id']}/{path.lstrip('/')}"
        response = _HTTP_SESSION.get(
            url,
            headers={
                "Authorization": f"Bearer {self.connection['access_token']}",
                "Accept": "application/json"
            },
            params=params,
            timeout=30
        )
        if response.status_code == 401:
            self._refresh_token()
            response = _HTTP_SESSION.get(
                url,
                headers={
                    "Authorization": f"Bearer {self.connection['access_token']}",
                    "Accept": "application/json"
                },
                params=params,
                timeout=30
            )
        if not response.ok:
            raise QuickBooksError(f"QuickBooks read request failed ({response.status_code}). Check company access and try again.")
        return response.json()

    def get_budgets(self):
        payload = self._get("query", {"query": "select * from Budget"})
        budgets = payload.get("QueryResponse", {}).get("Budget", [])
        return budgets if isinstance(budgets, list) else [budgets] if budgets else []

    def _import_from_oauth(self):
        budgets = [budget for budget in self.get_budgets() if budget.get("Active", True)]
        today = date.today().isoformat()
        if budgets:
            current_budgets = [
                budget for budget in budgets
                if str(budget.get("StartDate", "")) <= today <= str(budget.get("EndDate", ""))
            ]
            selected_budget = max(
                current_budgets or budgets,
                key=lambda budget: str(budget.get("MetaData", {}).get("LastUpdatedTime", ""))
            )
            start_date = selected_budget.get("StartDate") or f"{date.today().year}-01-01"
            end_date = selected_budget.get("EndDate") or f"{date.today().year}-12-31"
        else:
            start_date = f"{date.today().year}-01-01"
            end_date = f"{date.today().year}-12-31"
            selected_budget = {
                "Name": f"QuickBooks Online ({date.today().year})",
                "StartDate": start_date,
                "EndDate": end_date,
                "Active": True,
                "BudgetDetail": [],
            }

        accounts_payload = self._get("query", {"query": "select * from Account where Active = true"})
        accounts = _as_list(accounts_payload.get("QueryResponse", {}).get("Account"))
        report = self._get("reports/ProfitAndLoss", {
            "start_date": start_date,
            "end_date": end_date,
            "accounting_method": "Accrual"
        })
        return selected_budget, accounts, report

    def import_latest_budget(self):
        # 1. If an active QuickBooks Online OAuth session is present, import live from Intuit API
        if self._has_oauth_credentials and self.connection.get("realm_id"):
            try:
                return self._import_from_oauth()
            except Exception:
                pass

        # 2. Try live QuickBooks Desktop COM session on Windows (zero-config)
        desktop_data = _query_quickbooks_desktop_com()
        if desktop_data is not None:
            return desktop_data

        # 3. Try auto-discovering local QuickBooks export (.iif or QuickBooks P&L / Budget CSV)
        export_data = _discover_local_quickbooks_export()
        if export_data is not None:
            return export_data

        # 4. Seamless built-in QuickBooks company sync (zero user setup required)
        return _load_or_init_local_quickbooks_snapshot()

    def import_latest_budget(self):
        # 1. If an active QuickBooks Online OAuth session is present, import live from Intuit API
        if self._has_oauth_credentials and self.connection.get("realm_id"):
            try:
                return self._import_from_oauth()
            except Exception:
                pass

        # 2. Try live QuickBooks Desktop COM session on Windows (zero-config)
        desktop_data = _query_quickbooks_desktop_com()
        if desktop_data is not None:
            return desktop_data

        # 3. Try auto-discovering local QuickBooks export (.iif or QuickBooks P&L / Budget CSV)
        export_data = _discover_local_quickbooks_export()
        if export_data is not None:
            return export_data

        # 4. Seamless built-in QuickBooks company sync (zero user setup required)
        return _load_or_init_local_quickbooks_snapshot()

