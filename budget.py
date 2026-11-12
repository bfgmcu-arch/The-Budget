import csv
from datetime import datetime
import html
import io
import math
import re

import pandas as pd

import security
security.ensure_integrity_module()
import integrity
from security import enforce_runtime_authorization

enforce_runtime_authorization()

REQUIRED_COLUMNS = ("Category", "Type", "Budget", "Actual")

COLUMN_ALIASES = {
    "Category": {
        "category", "categories", "account", "accountname", "accounttitle",
        "description", "lineitem", "item", "name", "vendor"
    },
    "Type": {
        "type", "accounttype", "transactiontype", "classification", "kind"
    },
    "Budget": {
        "budget", "budgeted", "budgetamount", "planned", "plannedamount",
        "plan", "forecast", "forecastamount", "target", "expected"
    },
    "Actual": {
        "actual", "actuals", "actualamount", "amount", "value", "spent",
        "received", "total"
    }
}

_NON_ALNUM_RE = re.compile(r"[^a-z0-9]")
_AMOUNT_CLEAN_RE = re.compile(r"[^0-9,.+\-]")


def _sniff_delimiter(sample_bytes):
    try:
        sample_text = sample_bytes[:4096].decode("utf-8-sig", errors="ignore")
        dialect = csv.Sniffer().sniff(sample_text, delimiters=",;\t|")
        return dialect.delimiter
    except Exception:
        return ","


def read_budget_csv(file):
    content = file.getvalue() if hasattr(file, "getvalue") else file.read()
    delimiter = _sniff_delimiter(content)

    for encoding in ("utf-8-sig", "cp1252", "latin-1"):
        try:
            df = pd.read_csv(
                io.BytesIO(content),
                sep=delimiter,
                engine="c",
                encoding=encoding,
                skipinitialspace=True
            )
            if len(df.columns) <= 1 and any(sep in str(df.columns[0]) for sep in (";", "\t", "|")):
                df = pd.read_csv(
                    io.BytesIO(content),
                    sep=None,
                    engine="python",
                    encoding=encoding,
                    skipinitialspace=True
                )
            df.columns = [str(column).strip() for column in df.columns]
            return df
        except (pd.errors.ParserError, UnicodeDecodeError, ValueError):
            try:
                df = pd.read_csv(
                    io.BytesIO(content),
                    sep=None,
                    engine="python",
                    encoding=encoding,
                    skipinitialspace=True
                )
                df.columns = [str(column).strip() for column in df.columns]
                return df
            except (pd.errors.ParserError, UnicodeDecodeError, ValueError):
                continue

    raise ValueError("This CSV could not be read. Check that it is a valid, consistently delimited CSV file.")


def suggest_budget_columns(columns):
    normalized_columns = {
        _NON_ALNUM_RE.sub("", str(column).casefold()): str(column)
        for column in columns
    }
    suggestions = {}

    for field, aliases in COLUMN_ALIASES.items():
        if field in columns:
            suggestions[field] = field
            continue

        for alias in aliases:
            if alias in normalized_columns:
                suggestions[field] = normalized_columns[alias]
                break

    return suggestions


def _parse_amount(value):
    if value is None or pd.isna(value):
        return float("nan")
    if isinstance(value, (int, float)):
        return float(value)

    amount = str(value).strip().replace("\u00a0", "")
    if not amount:
        return float("nan")

    negative = amount.startswith("(") and amount.endswith(")")
    amount = _AMOUNT_CLEAN_RE.sub("", amount)

    if "," in amount and "." in amount:
        decimal_separator = "," if amount.rfind(",") > amount.rfind(".") else "."
        grouping_separator = "." if decimal_separator == "," else ","
        amount = amount.replace(grouping_separator, "")
        amount = amount.replace(decimal_separator, ".")
    elif "," in amount:
        if len(amount.rsplit(",", 1)[1]) in (1, 2):
            amount = amount.replace(".", "").replace(",", ".")
        else:
            amount = amount.replace(",", "")

    try:
        parsed = float(amount)
    except ValueError:
        return float("nan")
    return -abs(parsed) if negative else parsed


def load_budget(file, column_mapping=None):
    df = file.copy() if isinstance(file, pd.DataFrame) else read_budget_csv(file)
    df.columns = [str(column).strip() for column in df.columns]

    if column_mapping is None:
        column_mapping = suggest_budget_columns(df.columns)

    missing_columns = [column for column in REQUIRED_COLUMNS if column not in column_mapping]
    if missing_columns:
        raise ValueError(
            "Choose a CSV column for each required field: "
            + ", ".join(missing_columns)
        )

    missing_sources = [
        source for source in column_mapping.values()
        if source not in df.columns
    ]
    if missing_sources:
        raise ValueError("The selected CSV columns are no longer available. Recheck the column mapping.")

    df = df[[column_mapping[field] for field in REQUIRED_COLUMNS]].copy()
    df.columns = list(REQUIRED_COLUMNS)
    df["Category"] = df["Category"].fillna("").astype(str).str.strip()
    df = df[df["Category"] != ""].copy()

    type_values = df["Type"].fillna("").astype(str).str.strip().str.casefold()
    type_aliases = {
        "income": "Revenue", "revenue": "Revenue", "revenues": "Revenue",
        "sales": "Revenue", "expense": "Expense", "expenses": "Expense",
        "cost": "Expense", "costs": "Expense", "expenditure": "Expense",
        "expenditures": "Expense", "cogs": "Expense"
    }
    df["Type"] = type_values.map(type_aliases)
    if df["Type"].isna().any():
        invalid_types = sorted(type_values[df["Type"].isna()].unique())
        raise ValueError("Unrecognized Type values: " + ", ".join(invalid_types))

    for column in ("Budget", "Actual"):
        if pd.api.types.is_numeric_dtype(df[column]):
            df[column] = df[column].astype(float)
        else:
            df[column] = df[column].map(_parse_amount)
        if df[column].isna().any():
            raise ValueError(f"The {column} column contains blank or unrecognized amounts.")

    return df


def analyze_budget(df):
    df = df.copy()
    df["Type"] = df["Type"].astype(str).str.strip().str.title()
    df["Variance"] = df["Actual"] - df["Budget"]
    df["Percent Used"] = (df["Actual"] / df["Budget"] * 100).round(1)
    df["Status"] = "Good"

    expense_mask = df["Type"] == "Expense"
    revenue_mask = df["Type"] == "Revenue"

    df.loc[expense_mask & (df["Percent Used"] >= 90) & (df["Actual"] < df["Budget"]), "Status"] = "Warning"
    df.loc[expense_mask & (df["Actual"] > df["Budget"]), "Status"] = "Over Budget"
    df.loc[revenue_mask & (df["Actual"] < df["Budget"]), "Status"] = "Below Target"
    return df


def totals(df):
    if df.empty:
        return {"Revenue": 0.0, "Expenses": 0.0, "Profit": 0.0}
    type_col = df["Type"]
    actual_col = df["Actual"]
    revenue = float(actual_col[type_col == "Revenue"].sum())
    expenses = float(actual_col[type_col == "Expense"].sum())
    profit = revenue - expenses
    return {
        "Revenue": revenue,
        "Expenses": expenses,
        "Profit": profit
    }


def budget_kpis(df):
    if df.empty:
        return {
            "Revenue": 0.0,
            "Expenses": 0.0,
            "Profit": 0.0,
            "BudgetedRevenue": 0.0,
            "BudgetedExpenses": 0.0,
            "BudgetedProfit": 0.0,
            "ProfitMargin": 0.0,
            "OverBudgetCount": 0,
            "WarningCount": 0,
            "OverspendAmount": 0.0,
        }
    analyzed = analyze_budget(df) if "Status" not in df.columns else df
    rev_mask = analyzed["Type"] == "Revenue"
    exp_mask = analyzed["Type"] == "Expense"

    actual_rev = float(analyzed.loc[rev_mask, "Actual"].sum())
    actual_exp = float(analyzed.loc[exp_mask, "Actual"].sum())
    budget_rev = float(analyzed.loc[rev_mask, "Budget"].sum())
    budget_exp = float(analyzed.loc[exp_mask, "Budget"].sum())
    profit = actual_rev - actual_exp
    margin = (profit / actual_rev * 100.0) if actual_rev > 0 else 0.0

    over_mask = exp_mask & (analyzed["Actual"] > analyzed["Budget"])
    overspend = float((analyzed.loc[over_mask, "Actual"] - analyzed.loc[over_mask, "Budget"]).sum())
    over_count = int((analyzed["Status"] == "Over Budget").sum())
    warn_count = int(analyzed["Status"].isin(("Warning", "Below Target")).sum())

    return {
        "Revenue": actual_rev,
        "Expenses": actual_exp,
        "Profit": profit,
        "BudgetedRevenue": budget_rev,
        "BudgetedExpenses": budget_exp,
        "BudgetedProfit": budget_rev - budget_exp,
        "ProfitMargin": margin,
        "OverBudgetCount": over_count,
        "WarningCount": warn_count,
        "OverspendAmount": overspend,
    }


def simulate_financial_scenario(
    df,
    revenue_change_percent=0.0,
    expense_change_percent=0.0,
    one_time_cost=0.0,
    periods=1
):
    values = (revenue_change_percent, expense_change_percent, one_time_cost)
    if not all(math.isfinite(value) for value in values):
        raise ValueError("Scenario inputs must be finite numbers.")
    if revenue_change_percent <= -100 or expense_change_percent <= -100:
        raise ValueError("Revenue and expense changes must be greater than -100%.")
    if one_time_cost < 0:
        raise ValueError("One-time investment cannot be negative.")
    if isinstance(periods, bool) or not isinstance(periods, int) or not 1 <= periods <= 60:
        raise ValueError("Forecast periods must be a whole number from 1 to 60.")

    baseline = totals(df)
    baseline_profit = baseline["Profit"] * periods
    projected_revenue = baseline["Revenue"] * (1 + revenue_change_percent / 100) * periods
    projected_expenses = baseline["Expenses"] * (1 + expense_change_percent / 100) * periods + one_time_cost
    projected_profit = projected_revenue - projected_expenses
    profit_margin = projected_profit / projected_revenue * 100 if projected_revenue else 0.0

    return {
        "periods": periods,
        "baseline_revenue_per_period": baseline["Revenue"],
        "baseline_expenses_per_period": baseline["Expenses"],
        "baseline_profit_per_period": baseline["Profit"],
        "projected_revenue": projected_revenue,
        "projected_expenses": projected_expenses,
        "projected_profit": projected_profit,
        "baseline_projected_profit": baseline_profit,
        "profit_change": projected_profit - baseline_profit,
        "profit_margin_percent": profit_margin,
        "one_time_cost": one_time_cost
    }


def generate_executive_report_html(df, analysis_text="", scenario_tuple=None, messages=None):
    analyzed = analyze_budget(df) if not df.empty else df.copy()
    kpis = budget_kpis(analyzed)
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M")

    rows_html = []
    for row in analyzed.to_dict("records"):
        status = str(row.get("Status", "Good"))
        badge_color = (
            "#a43d35" if status == "Over Budget"
            else "#8b6416" if status in ("Warning", "Below Target")
            else "#176b52"
        )
        badge_bg = (
            "#fdeceb" if status == "Over Budget"
            else "#fef6e6" if status in ("Warning", "Below Target")
            else "#e3f1eb"
        )
        pct = row.get("Percent Used", float("nan"))
        pct_text = f"{pct:.1f}%" if pd.notna(pct) and math.isfinite(float(pct)) else "N/A"
        rows_html.append(
            f"<tr>"
            f"<td><strong>{html.escape(str(row['Category']))}</strong></td>"
            f"<td>{html.escape(str(row['Type']))}</td>"
            f"<td class='num'>${float(row['Budget']):,.2f}</td>"
            f"<td class='num'>${float(row['Actual']):,.2f}</td>"
            f"<td class='num'>${float(row['Variance']):+,.2f}</td>"
            f"<td class='num'>{pct_text}</td>"
            f"<td><span class='badge' style='color:{badge_color};background:{badge_bg}'>{html.escape(status)}</span></td>"
            f"</tr>"
        )

    scenario_section = ""
    if scenario_tuple:
        res, rev_chg, exp_chg = scenario_tuple
        scenario_section = f"""
        <div class="card" style="margin-top:20px;">
            <h2>Scenario Forecast ({res['periods']} Period{'s' if res['periods'] != 1 else ''}: Revenue {rev_chg:+.1f}%, Expenses {exp_chg:+.1f}%)</h2>
            <div class="grid">
                <div><div class="label">PROJECTED REVENUE</div><div class="val">${res['projected_revenue']:,.2f}</div></div>
                <div><div class="label">PROJECTED EXPENSES</div><div class="val">${res['projected_expenses']:,.2f}</div></div>
                <div><div class="label">PROJECTED PROFIT</div><div class="val">${res['projected_profit']:,.2f}</div></div>
                <div><div class="label">VS. BASELINE</div><div class="val">${res['profit_change']:+,.2f} ({res['profit_margin_percent']:.1f}% margin)</div></div>
            </div>
        </div>
        """

    advisor_section = ""
    if analysis_text and analysis_text.strip():
        escaped_analysis = html.escape(analysis_text.strip()).replace("\n", "<br>")
        advisor_section = f"""
        <div class="card" style="margin-top:20px;">
            <h2>AI Executive Summary & Recommendations</h2>
            <div style="line-height:1.6;font-size:14px;">{escaped_analysis}</div>
        </div>
        """

    research_section = ""
    if messages:
        ai_notes = [msg for sender, msg in messages if sender == "AI" and ("http://" in msg or "https://" in msg or "savings" in msg.lower())]
        if ai_notes:
            latest_note = html.escape(ai_notes[-1]).replace("\n", "<br>")
            latest_note = re.sub(
                r"(https?://[^\s<&]+)",
                r'<a href="\1" target="_blank" style="color:#176b52;">\1</a>',
                latest_note,
            )
            research_section = f"""
            <div class="card" style="margin-top:20px;">
                <h2>Latest Cost-Reduction & Supplier Research</h2>
                <div style="line-height:1.6;font-size:13.5px;">{latest_note}</div>
            </div>
            """

    profit_color = "#176b52" if kpis["Profit"] >= 0 else "#a43d35"
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<title>Executive Financial Report — Business Budget AI</title>
<style>
  body {{ font-family: 'Segoe UI', system-ui, sans-serif; background: #f3f5f2; color: #18221f; margin: 0; padding: 32px; }}
  .container {{ max-width: 1060px; margin: 0 auto; }}
  .header {{ display: flex; justify-content: space-between; align-items: baseline; margin-bottom: 20px; }}
  h1 {{ margin: 0; font-size: 26px; }}
  h2 {{ margin: 0 0 14px 0; font-size: 17px; color: #18221f; }}
  .sub {{ color: #68756f; font-size: 13px; }}
  .grid {{ display: grid; grid-template-columns: repeat(4, 1fr); gap: 14px; margin-bottom: 20px; }}
  .card {{ background: #ffffff; border-radius: 6px; padding: 18px 20px; box-shadow: 0 1px 3px rgba(0,0,0,0.05); }}
  .label {{ font-size: 11px; color: #68756f; font-weight: 600; letter-spacing: 0.4px; }}
  .val {{ font-size: 22px; font-weight: 600; margin-top: 6px; }}
  table {{ width: 100%; border-collapse: collapse; font-size: 13.5px; }}
  th {{ text-align: left; background: #edf1ed; color: #68756f; padding: 10px 12px; font-weight: 600; }}
  td {{ padding: 10px 12px; border-bottom: 1px solid #dce3de; }}
  .num {{ text-align: right; font-variant-numeric: tabular-nums; }}
  .badge {{ padding: 3px 8px; border-radius: 4px; font-size: 12px; font-weight: 600; }}
  @media print {{ body {{ background: #fff; padding: 0; }} .card {{ box-shadow: none; border: 1px solid #dce3de; }} }}
</style>
</head>
<body>
<div class="container">
  <div class="header">
    <div>
      <h1>Business Budget AI — Executive Financial Report</h1>
      <div class="sub">Generated locally on {timestamp}</div>
    </div>
    <button onclick="window.print()" style="background:#176b52;color:#fff;border:none;padding:8px 16px;border-radius:4px;cursor:pointer;font-weight:600;">Print / Save PDF</button>
  </div>
  <div class="grid">
    <div class="card"><div class="label">ACTUAL REVENUE</div><div class="val">${kpis['Revenue']:,.2f}</div><div class="sub">Budget: ${kpis['BudgetedRevenue']:,.2f}</div></div>
    <div class="card"><div class="label">ACTUAL EXPENSES</div><div class="val">${kpis['Expenses']:,.2f}</div><div class="sub">Budget: ${kpis['BudgetedExpenses']:,.2f}</div></div>
    <div class="card"><div class="label">NET PROFIT</div><div class="val" style="color:{profit_color}">${kpis['Profit']:,.2f}</div><div class="sub">Margin: {kpis['ProfitMargin']:.1f}%</div></div>
    <div class="card"><div class="label">ATTENTION NEEDED</div><div class="val" style="color:{'#a43d35' if kpis['OverBudgetCount'] else '#176b52'}">{kpis['OverBudgetCount']} Over Budget</div><div class="sub">Overspend: ${kpis['OverspendAmount']:,.2f}</div></div>
  </div>
  <div class="card">
    <h2>Budget vs. Actual by Category</h2>
    <table>
      <thead><tr><th>Category</th><th>Type</th><th class="num">Budget</th><th class="num">Actual</th><th class="num">Variance</th><th class="num">% Used</th><th>Status</th></tr></thead>
      <tbody>{''.join(rows_html)}</tbody>
    </table>
  </div>
  {scenario_section}
  {advisor_section}
  {research_section}
</div>
</body>
</html>"""
