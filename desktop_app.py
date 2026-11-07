import hashlib
import io
import math
import os
import queue
import re
import sys
import threading
import webbrowser
from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

import pandas as pd

from ai import analyze, category_to_supply_search, chat_with_memory, clear_conversation, find_product_alternatives, load_conversation, save_conversation, warm_up_model
from budget import analyze_budget, budget_kpis, generate_executive_report_html, load_budget, read_budget_csv, simulate_financial_scenario, suggest_budget_columns, totals
from bookkeeping import audit_transactions, draft_vendor_action_message, load_transactions, summarize_transactions_Into_budget
from quickbooks import QuickBooksClient, QuickBooksError, load_connection, map_quickbooks_budget, save_connection
from shopping_api import ShoppingApiError, clear_api_key, load_api_key, save_api_key
from secure_storage import SecureStorageError, read_file as read_protected_file, write_file as write_protected_file


APP_NAME = "Business Budget AI"
_URL_RE = re.compile(r"https?://[^\s<>]+")
FIELDS = ["Category", "Type", "Budget", "Actual"]
TUTORIAL_PAGES = (
    (
        "Welcome to Business Budget AI",
        "Use this workspace to understand business income and costs. Budget overview shows revenue, expenses, and profit. AI advisor answers questions using the budget you load."
    ),
    (
        "Set up your budget",
        "Choose Open CSV to import your existing budget. Match the columns for Category, Type, Budget, and Actual. Or choose Add row to enter items manually. Double-click a row to edit it. Save budget stores your working copy encrypted on this computer."
    ),
    (
        "Ask the advisor",
        "Generate budget summary for an overview, or ask a question in the AI advisor tab. Use Scenario planner to test changes to revenue, expenses, and one-time costs. Audit transactions checks bank CSV exports for possible duplicate charges, recurring bills, and price increases; it never edits transactions. Review purchases starts a guided interview. Find cheaper options compares product search results; include the product type and required specifications for the most relevant matches. Connect QuickBooks imports an authorized budget and matching Profit & Loss summary. The app never places orders."
    ),
    (
        "Your data and product searches",
        "Saved budgets, chat history, API keys, and exported backups are encrypted using this Windows account's credential store. Encrypted backups are tied to this account and computer. The AI model runs locally. Product name, specifications, and region are queried across public retail and supplier listings; budget amounts and current price are not sent. QuickBooks imports read budget and Profit & Loss account totals only."
    )
)
COLORS = {
    "background": "#f3f5f2",
    "surface": "#ffffff",
    "ink": "#18221f",
    "muted": "#68756f",
    "green": "#176b52",
    "green_light": "#e3f1eb",
    "line": "#dce3de",
    "red": "#a43d35",
    "amber": "#8b6416",
}


def data_file():
    if os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    return base / "BusinessBudgetAI" / "budget.csv.enc"


def budget_signature(df):
    content = df[FIELDS].to_json(orient="records")
    return hashlib.sha256(content.encode("utf-8")).hexdigest()


class BudgetApp:
    def __init__(self, root):
        self.root = root
        self.root.title(APP_NAME)
        self.root.geometry("1180x780")
        self.root.minsize(940, 640)
        self.root.configure(bg=COLORS["background"])
        self.data_path = data_file()
        self.tutorial_path = self.data_path.with_name("tutorial.completed")
        self.df = pd.DataFrame(columns=FIELDS)
        self.current_signature = None
        self.analysis_text = ""
        self.chat_history = []
        self.chat_memory = ""
        self.messages = []
        self._rendered_count = 0
        self._link_index = 0
        self._summary_chart_state = None
        self._summary_chart_after = None
        self._scenario_chart_state = None
        self._scenario_chart_after = None
        self._poll_scheduled = False
        self.task_queue = queue.Queue()
        self.busy = False
        self._configure_styles()
        self._build_ui()
        self._load_initial_budget()
        self.root.after_idle(self._show_tutorial_if_needed)

    def _configure_styles(self):
        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure("App.TFrame", background=COLORS["background"])
        style.configure("Surface.TFrame", background=COLORS["surface"])
        style.configure("Title.TLabel", background=COLORS["background"], foreground=COLORS["ink"], font=("Segoe UI Semibold", 22))
        style.configure("Subtitle.TLabel", background=COLORS["background"], foreground=COLORS["muted"], font=("Segoe UI", 10))
        style.configure("Section.TLabel", background=COLORS["surface"], foreground=COLORS["ink"], font=("Segoe UI Semibold", 12))
        style.configure("MetricLabel.TLabel", background=COLORS["surface"], foreground=COLORS["muted"], font=("Segoe UI", 9))
        style.configure("MetricValue.TLabel", background=COLORS["surface"], foreground=COLORS["ink"], font=("Segoe UI Semibold", 19))
        style.configure("TNotebook", background=COLORS["background"], borderwidth=0)
        style.configure("TNotebook.Tab", background="#e7ebe7", foreground=COLORS["muted"], padding=(16, 9), font=("Segoe UI Semibold", 10))
        style.map("TNotebook.Tab", background=[("selected", COLORS["surface"])], foreground=[("selected", COLORS["green"])])
        style.configure("Treeview", background=COLORS["surface"], fieldbackground=COLORS["surface"], foreground=COLORS["ink"], rowheight=32, borderwidth=0, font=("Segoe UI", 9))
        style.configure("Treeview.Heading", background="#edf1ed", foreground=COLORS["muted"], relief="flat", font=("Segoe UI Semibold", 9), padding=(8, 8))
        style.map("Treeview", background=[("selected", COLORS["green_light"])], foreground=[("selected", COLORS["ink"])])
        style.configure("Primary.TButton", background=COLORS["green"], foreground="#ffffff", padding=(12, 8), borderwidth=0, font=("Segoe UI Semibold", 9))
        style.map("Primary.TButton", background=[("active", "#125740"), ("disabled", "#9eaaa4")])
        style.configure("TButton", padding=(10, 7), font=("Segoe UI", 9))
        style.configure("TEntry", padding=7, fieldbackground="#ffffff")
        style.configure("TCombobox", padding=6)

    def _build_ui(self):
        header = ttk.Frame(self.root, style="App.TFrame", padding=(26, 20, 26, 14))
        header.pack(fill="x")
        heading = ttk.Frame(header, style="App.TFrame")
        heading.pack(side="left", fill="x", expand=True)
        ttk.Label(heading, text="Business Budget AI", style="Title.TLabel").pack(anchor="w")
        ttk.Label(heading, text="A clear view of your numbers, with practical AI guidance.", style="Subtitle.TLabel").pack(anchor="w", pady=(3, 0))
        self.status_var = tk.StringVar(value="Ready")
        ttk.Label(header, textvariable=self.status_var, style="Subtitle.TLabel").pack(side="right", anchor="e", padx=(12, 0))

        toolbar = ttk.Frame(self.root, style="App.TFrame", padding=(26, 0, 26, 14))
        toolbar.pack(fill="x")
        ttk.Button(toolbar, text="Open CSV", command=self.open_csv).pack(side="left")
        ttk.Button(toolbar, text="Save budget", command=self.save_csv).pack(side="left", padx=(7, 0))
        ttk.Button(toolbar, text="Audit transactions", command=self.audit_transaction_file).pack(side="left", padx=(7, 0))
        ttk.Button(toolbar, text="Export encrypted backup", command=self.export_csv).pack(side="left", padx=(7, 0))
        self.quickbooks_button = ttk.Button(toolbar, text="Connect QuickBooks", command=self.connect_quickbooks)
        self.quickbooks_button.pack(side="left", padx=(7, 0))
        ttk.Button(toolbar, text="Executive report", command=self.open_executive_report).pack(side="left", padx=(7, 0))
        ttk.Button(toolbar, text="Add row", command=self.add_row, style="Primary.TButton").pack(side="right")
        ttk.Button(toolbar, text="Remove row", command=self.remove_rows).pack(side="right", padx=(0, 7))

        self.notebook = ttk.Notebook(self.root)
        self.notebook.pack(fill="both", expand=True, padx=26, pady=(0, 20))
        self.overview = ttk.Frame(self.notebook, style="App.TFrame", padding=18)
        self.scenario = ttk.Frame(self.notebook, style="App.TFrame", padding=18)
        self.advisor = ttk.Frame(self.notebook, style="App.TFrame", padding=18)
        self.notebook.add(self.overview, text="Budget overview")
        self.notebook.add(self.scenario, text="Scenario planner")
        self.notebook.add(self.advisor, text="AI advisor")
        self._build_overview()
        self._build_scenario()
        self._build_advisor()

    def audit_transaction_file(self):
        path = filedialog.askopenfilename(
            title="Select a bank transaction CSV",
            filetypes=[("CSV files", "*.csv"), ("All files", "*.*")]
        )
        if not path:
            return
        try:
            with open(path, "rb") as transaction_file:
                raw = read_budget_csv(transaction_file)
            transactions = load_transactions(raw)
            issues = audit_transactions(transactions)
        except (OSError, ValueError) as exc:
            messagebox.showerror(APP_NAME, f"Could not audit this transaction file.\n\n{exc}")
            return
        if not issues:
            if messagebox.askyesno(
                APP_NAME,
                "No duplicate charges or price spikes were found.\n\nWould you like to sync the transaction actuals into your budget categories?"
            ):
                self._sync_transactions_to_budget(transactions, Path(path).name)
            return
        self._show_transaction_audit(path, issues, transactions)

    def _sync_transactions_to_budget(self, transactions, source_name="transactions"):
        try:
            merged = summarize_transactions_Into_budget(transactions, self.df)
            self.df = load_budget(merged)
            self._refresh()
            self._save_current(quiet=True)
            self.status_var.set(f"Synced actuals from {source_name} into {len(self.df)} budget categories")
        except Exception as exc:
            messagebox.showerror(APP_NAME, f"Could not sync transactions to budget.\n\n{exc}")

    def _show_transaction_audit(self, source_path, issues, transactions=None):
        dialog = tk.Toplevel(self.root)
        dialog.title("Transaction audit & bill recovery")
        dialog.transient(self.root)
        dialog.geometry("1060x600")
        dialog.minsize(840, 460)
        body = ttk.Frame(dialog, padding=18)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text=f"Review candidates from {Path(source_path).name}", style="Section.TLabel").pack(anchor="w")
        ttk.Label(
            body,
            text="Select any finding to copy a ready-to-send refund/rate-negotiation email, or sync transaction totals directly into your budget.",
            style="Subtitle.TLabel",
            wraplength=980
        ).pack(anchor="w", pady=(5, 12))
        table_frame = ttk.Frame(body)
        table_frame.pack(fill="both", expand=True)
        columns = ("Issue", "Merchant", "Occurrences", "Latest amount", "Change", "Last date")
        tree = ttk.Treeview(table_frame, columns=columns, show="headings", selectmode="browse")
        widths = {"Issue": 190, "Merchant": 270, "Occurrences": 100, "Latest amount": 130, "Change": 100, "Last date": 120}
        for column in columns:
            tree.heading(column, text=column)
            tree.column(column, width=widths[column], anchor="w" if column in ("Issue", "Merchant") else "e", stretch=column == "Merchant")
        scrollbar = ttk.Scrollbar(table_frame, orient="vertical", command=tree.yview)
        tree.configure(yscrollcommand=scrollbar.set)
        tree.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        detail_var = tk.StringVar(value="Select a finding to view its review note or generate a vendor negotiation/refund email.")
        ttk.Label(body, textvariable=detail_var, style="MetricLabel.TLabel", wraplength=980, justify="left").pack(anchor="w", pady=(10, 6))
        issue_by_id = {}
        for issue in issues:
            item_id = tree.insert(
                "", "end",
                values=(
                    issue["Issue"], issue["Merchant"], issue["Occurrences"],
                    f"${issue['Amount']:,.2f}", issue["Change"], issue["Last date"]
                )
            )
            issue_by_id[item_id] = issue
        tree.bind(
            "<<TreeviewSelect>>",
            lambda _event: detail_var.set(issue_by_id[tree.selection()[0]]["Details"])
            if tree.selection() else None
        )

        def copy_dispute():
            if not tree.selection():
                if tree.get_children():
                    tree.selection_set(tree.get_children()[0])
                else:
                    return
            selected_issue = issue_by_id[tree.selection()[0]]
            draft = draft_vendor_action_message(selected_issue)
            self.root.clipboard_clear()
            self.root.clipboard_append(draft)
            detail_var.set(f"COPIED TO CLIPBOARD — Ready to paste into email:\n{draft}")

        def send_audit_to_ai():
            top_lines = [
                f"- {iss['Issue']}: {iss['Merchant']} (${abs(iss['Amount']):,.2f}, {iss['Occurrences']}x, change {iss['Change'] or 'N/A'}, last {iss['Last date']})"
                for iss in issues[:8]
            ]
            dialog.destroy()
            self.notebook.select(self.advisor)
            self.question.delete(0, "end")
            self.question.insert(
                0,
                "Give me a prioritized cash-recovery action plan for these bank audit findings: " + "; ".join(top_lines)
            )
            self.send_question()

        footer = ttk.Frame(body)
        footer.pack(fill="x", pady=(10, 0))
        ttk.Button(footer, text="Copy vendor refund / negotiation email", command=copy_dispute, style="Primary.TButton").pack(side="left")
        if transactions is not None:
            ttk.Button(
                footer,
                text="Sync actuals into budget",
                command=lambda: (self._sync_transactions_to_budget(transactions, Path(source_path).name), dialog.destroy())
            ).pack(side="left", padx=(8, 0))
        ttk.Button(footer, text="Ask AI advisor for recovery plan", command=send_audit_to_ai).pack(side="left", padx=(8, 0))
        ttk.Button(footer, text="Close", command=dialog.destroy).pack(side="right")

    def _build_overview(self):
        metrics = ttk.Frame(self.overview, style="App.TFrame")
        metrics.pack(fill="x", pady=(0, 16))
        self.metric_values = {}
        kpi_defs = (
            ("Revenue", "Actual revenue"),
            ("Expenses", "Actual expenses"),
            ("Profit", "Net profit"),
            ("Margin", "Profit margin"),
            ("Health", "Budget alerts"),
        )
        for key, label in kpi_defs:
            panel = ttk.Frame(metrics, style="Surface.TFrame", padding=(14, 12))
            panel.pack(side="left", fill="x", expand=True, padx=(0, 8))
            ttk.Label(panel, text=label.upper(), style="MetricLabel.TLabel").pack(anchor="w")
            value = ttk.Label(panel, text="$0.00" if key in ("Revenue", "Expenses", "Profit") else "--", style="MetricValue.TLabel")
            value.pack(anchor="w", pady=(4, 0))
            self.metric_values[key] = value

        chart_panel = ttk.Frame(self.overview, style="Surface.TFrame", padding=(14, 10))
        chart_panel.pack(fill="x", pady=(0, 14))
        ttk.Label(chart_panel, text="Largest budget variances", style="Section.TLabel").pack(anchor="w", pady=(0, 4))
        self.summary_chart = tk.Canvas(chart_panel, height=220, bg=COLORS["surface"], highlightthickness=0)
        self.summary_chart.pack(fill="x", expand=True)
        self.summary_chart.bind("<Configure>", self._on_summary_chart_configure)

        table_panel = ttk.Frame(self.overview, style="Surface.TFrame", padding=14)
        table_panel.pack(fill="both", expand=True)
        table_header = ttk.Frame(table_panel, style="Surface.TFrame")
        table_header.pack(fill="x", pady=(0, 10))
        ttk.Label(table_header, text="Budget details", style="Section.TLabel").pack(side="left")
        self.filter_var = tk.StringVar()
        self.filter_var.trace_add("write", lambda *_: self._populate_table())
        filter_entry = ttk.Entry(table_header, textvariable=self.filter_var, width=24)
        filter_entry.pack(side="right", padx=(6, 0))
        ttk.Label(table_header, text="Filter:", style="MetricLabel.TLabel").pack(side="right", padx=(12, 0))
        ttk.Label(table_header, text="Double-click to edit  |  Right-click row for AI & supplier actions", style="MetricLabel.TLabel").pack(side="right")
        columns = ("Category", "Type", "Budget", "Actual", "Variance", "Percent Used", "Status")
        self.table = ttk.Treeview(table_panel, columns=columns, show="headings", selectmode="extended")
        self._sort_column = None
        self._sort_reverse = False
        widths = {"Category": 210, "Type": 105, "Budget": 125, "Actual": 125, "Variance": 125, "Percent Used": 115, "Status": 130}
        for column in columns:
            self.table.heading(column, text=column, command=lambda col=column: self._sort_table_by(col))
            self.table.column(column, width=widths[column], anchor="w" if column in ("Category", "Type", "Status") else "e", stretch=column == "Category")
        self.table.tag_configure("warning", foreground=COLORS["amber"])
        self.table.tag_configure("over", foreground=COLORS["red"])
        self.table.tag_configure("good", foreground=COLORS["green"])
        scrollbar = ttk.Scrollbar(table_panel, orient="vertical", command=self.table.yview)
        self.table.configure(yscrollcommand=scrollbar.set)
        self.table.pack(side="left", fill="both", expand=True)
        scrollbar.pack(side="right", fill="y")
        self.table.bind("<Double-1>", self._edit_selected)
        self.table.bind("<Delete>", lambda _event: self.remove_rows())
        self.row_menu = tk.Menu(self.root, tearoff=0)
        self.row_menu.add_command(label="Find cheaper suppliers for this category", command=self._context_find_cheaper)
        self.row_menu.add_command(label="Ask AI how to optimize this category", command=self._context_ask_ai)
        self.row_menu.add_command(label="Simulate 15% cost cut in Scenario Planner", command=self._context_simulate_cut)
        self.row_menu.add_separator()
        self.row_menu.add_command(label="Edit row", command=self._edit_selected)
        self.row_menu.add_command(label="Remove row", command=self.remove_rows)
        self.table.bind("<Button-3>", self._show_row_context_menu)

    def _on_summary_chart_configure(self, event):
        if self._summary_chart_after is not None:
            self.root.after_cancel(self._summary_chart_after)
        w, h = event.width, event.height
        self._summary_chart_after = self.root.after(35, lambda: self._draw_summary_chart(w, h))

    def _draw_summary_chart(self, width=None, height=None, force=False):
        self._summary_chart_after = None
        canvas = self.summary_chart
        width = width or canvas.winfo_width()
        height = height or canvas.winfo_height()
        if width < 300 or height < 100:
            return
        state_key = (width, height, self.current_signature, len(self.df))
        if not force and state_key == self._summary_chart_state:
            return
        self._summary_chart_state = state_key
        canvas.delete("all")
        if self.df.empty:
            canvas.create_text(width / 2, height / 2, text="Load a budget to compare budget and actual by category.", fill=COLORS["muted"], font=("Segoe UI", 10))
            return

        variances = (self.df["Actual"] - self.df["Budget"]).abs()
        top_indices = variances.nlargest(5).index
        top_records = self.df.loc[top_indices].to_dict("records")
        left, right = 180, 72
        plot_width = max(40, width - left - right)
        max_value = max(
            1.0,
            max((max(abs(float(r["Budget"])), abs(float(r["Actual"]))) for r in top_records), default=1.0)
        )
        scale = plot_width * 0.82 / max_value
        row_height = min(34, (height - 36) / max(1, len(top_records)))
        canvas.create_rectangle(left, 10, left + 10, 20, fill=COLORS["amber"], outline="")
        canvas.create_text(left + 16, 15, text="Budget", anchor="w", fill=COLORS["muted"], font=("Segoe UI", 8))
        canvas.create_rectangle(left + 78, 10, left + 88, 20, fill=COLORS["green"], outline="")
        canvas.create_text(left + 94, 15, text="Actual", anchor="w", fill=COLORS["muted"], font=("Segoe UI", 8))
        zero_x = left + plot_width * 0.09
        start_y = 32
        canvas.create_line(zero_x, start_y, zero_x, height - 8, fill=COLORS["line"])

        for index, row in enumerate(top_records):
            center_y = start_y + index * row_height + row_height / 2
            category = str(row["Category"])
            if len(category) > 22:
                category = category[:19] + "..."
            canvas.create_text(left - 10, center_y, text=category, anchor="e", fill=COLORS["ink"], font=("Segoe UI", 8))
            for offset, key, color in ((-4, "Budget", COLORS["amber"]), (4, "Actual", COLORS["green"])):
                amount = float(row[key])
                endpoint = zero_x + amount * scale
                canvas.create_rectangle(
                    min(zero_x, endpoint), center_y + offset - 2,
                    max(zero_x, endpoint), center_y + offset + 2,
                    fill=color,
                    outline=""
                )
        canvas.create_text(width - 8, height - 5, text="Top 5 by absolute variance", anchor="se", fill=COLORS["muted"], font=("Segoe UI", 8))

    def _build_scenario(self):
        heading = ttk.Frame(self.scenario, style="App.TFrame")
        heading.pack(fill="x", pady=(0, 12))
        ttk.Label(heading, text="Scenario planner", style="Section.TLabel").pack(side="left")
        self.scenario_status_var = tk.StringVar(value="Planning estimate based on current actuals.")
        ttk.Label(heading, textvariable=self.scenario_status_var, style="Subtitle.TLabel").pack(side="right")

        assumptions = ttk.Frame(self.scenario, style="Surface.TFrame", padding=(14, 11))
        assumptions.pack(fill="x", pady=(0, 14))
        ttk.Label(
            assumptions,
            text=(
                "Each period repeats the current actual revenue and expenses. Percentage changes apply "
                "to every period; the one-time investment is applied once. This is a planning estimate, "
                "not a forecast of certainty."
            ),
            style="MetricLabel.TLabel",
            wraplength=900,
            justify="left"
        ).pack(anchor="w")

        controls = ttk.Frame(self.scenario, style="Surface.TFrame", padding=14)
        controls.pack(fill="x", pady=(0, 14))
        self.scenario_inputs = {
            "revenue_change": tk.StringVar(value="0"),
            "expense_change": tk.StringVar(value="0"),
            "one_time_cost": tk.StringVar(value="0"),
            "periods": tk.StringVar(value="12")
        }
        control_fields = (
            ("Revenue change (%)", "revenue_change"),
            ("Expense change (%)", "expense_change"),
            ("One-time investment", "one_time_cost"),
            ("Budget periods", "periods")
        )
        for index, (label, key) in enumerate(control_fields):
            column = index * 2
            ttk.Label(controls, text=label, style="MetricLabel.TLabel").grid(row=0, column=column, sticky="w", padx=(0, 8))
            ttk.Entry(controls, textvariable=self.scenario_inputs[key], width=15).grid(row=1, column=column, sticky="ew", padx=(0, 18), pady=(5, 10))
        ttk.Button(
            controls,
            text="Calculate scenario",
            command=self.calculate_scenario,
            style="Primary.TButton"
        ).grid(row=1, column=8, sticky="e", padx=(8, 0))
        for column in (0, 2, 4, 6):
            controls.columnconfigure(column, weight=1)

        results = ttk.Frame(self.scenario, style="App.TFrame")
        results.pack(fill="x")
        self.scenario_values = {}
        metrics = (
            ("Projected revenue", "revenue"),
            ("Projected expenses", "expenses"),
            ("Projected profit", "profit"),
            ("Change vs baseline", "change"),
            ("Projected profit margin", "margin")
        )
        for index, (label, key) in enumerate(metrics):
            row, column = divmod(index, 3)
            panel = ttk.Frame(results, style="Surface.TFrame", padding=(16, 13))
            panel.grid(row=row, column=column, sticky="nsew", padx=(0, 10), pady=(0, 10))
            ttk.Label(panel, text=label.upper(), style="MetricLabel.TLabel").pack(anchor="w")
            value = ttk.Label(panel, text="--", style="MetricValue.TLabel")
            value.pack(anchor="w", pady=(5, 0))
            self.scenario_values[key] = value
        for column in range(3):
            results.columnconfigure(column, weight=1)

        scenario_chart_panel = ttk.Frame(self.scenario, style="Surface.TFrame", padding=(14, 10))
        scenario_chart_panel.pack(fill="both", expand=True, pady=(14, 0))
        ttk.Label(scenario_chart_panel, text="Cumulative profit: baseline vs scenario", style="Section.TLabel").pack(anchor="w", pady=(0, 4))
        self.scenario_chart = tk.Canvas(scenario_chart_panel, height=260, bg=COLORS["surface"], highlightthickness=0)
        self.scenario_chart.pack(fill="both", expand=True)
        self.scenario_chart.bind("<Configure>", self._on_scenario_chart_configure)
        self._last_scenario = None

    def calculate_scenario(self, show_error=True):
        if self.df.empty:
            self.scenario_status_var.set("Add or import a budget to simulate scenarios.")
            return
        try:
            revenue_change = float(self.scenario_inputs["revenue_change"].get().replace(",", "").replace("%", "").strip())
            expense_change = float(self.scenario_inputs["expense_change"].get().replace(",", "").replace("%", "").strip())
            one_time_cost = float(self.scenario_inputs["one_time_cost"].get().replace(",", "").replace("$", "").strip())
            periods = int(self.scenario_inputs["periods"].get().strip())
            result = simulate_financial_scenario(
                self.df,
                revenue_change_percent=revenue_change,
                expense_change_percent=expense_change,
                one_time_cost=one_time_cost,
                periods=periods
            )
        except (ValueError, OverflowError) as exc:
            self.scenario_status_var.set("Check the scenario inputs.")
            if show_error:
                messagebox.showwarning(APP_NAME, f"Enter valid scenario values.\n\n{exc}")
            return

        self.scenario_values["revenue"].configure(text=f"${result['projected_revenue']:,.2f}")
        self.scenario_values["expenses"].configure(text=f"${result['projected_expenses']:,.2f}")
        self.scenario_values["profit"].configure(text=f"${result['projected_profit']:,.2f}")
        change = result["profit_change"]
        change_text = f"-${abs(change):,.2f}" if change < 0 else f"+${change:,.2f}"
        self.scenario_values["change"].configure(text=change_text)
        self.scenario_values["margin"].configure(text=f"{result['profit_margin_percent']:.1f}%")
        profit_color = COLORS["green"] if result["projected_profit"] >= 0 else COLORS["red"]
        self.scenario_values["profit"].configure(foreground=profit_color)
        change_color = COLORS["green"] if result["profit_change"] >= 0 else COLORS["red"]
        self.scenario_values["change"].configure(foreground=change_color)
        self.scenario_status_var.set(f"Projected over {periods} budget period{'s' if periods != 1 else ''}.")
        self._last_scenario = (result, revenue_change, expense_change)
        self._draw_scenario_chart(force=True)

    def _on_scenario_chart_configure(self, event):
        if self._scenario_chart_after is not None:
            self.root.after_cancel(self._scenario_chart_after)
        w, h = event.width, event.height
        self._scenario_chart_after = self.root.after(35, lambda: self._draw_scenario_chart(w, h))

    def _draw_scenario_chart(self, width=None, height=None, force=False):
        self._scenario_chart_after = None
        canvas = self.scenario_chart
        width = width or canvas.winfo_width()
        height = height or canvas.winfo_height()
        if width < 300 or height < 140:
            return
        state_key = (width, height, self._last_scenario)
        if not force and state_key == self._scenario_chart_state:
            return
        self._scenario_chart_state = state_key
        canvas.delete("all")
        if not self._last_scenario:
            canvas.create_text(width / 2, height / 2, text="Calculate a scenario to compare cumulative profit.", fill=COLORS["muted"], font=("Segoe UI", 10))
            return

        result, revenue_change, expense_change = self._last_scenario
        periods = result["periods"]
        baseline_profit = result["baseline_profit_per_period"]
        scenario_profit = (
            result["baseline_revenue_per_period"] * (1 + revenue_change / 100)
            - result["baseline_expenses_per_period"] * (1 + expense_change / 100)
        )
        baseline = [baseline_profit * period for period in range(periods + 1)]
        scenario = [
            scenario_profit * period - (result["one_time_cost"] if period else 0)
            for period in range(periods + 1)
        ]
        minimum = min(0.0, *baseline, *scenario)
        maximum = max(0.0, *baseline, *scenario)
        if maximum == minimum:
            maximum = minimum + 1.0

        left, right, top, bottom = 78, 24, 32, 32
        plot_width = max(1, width - left - right)
        plot_height = max(1, height - top - bottom)
        x = lambda period: left + period / max(1, periods) * plot_width
        y = lambda value: top + (maximum - value) / (maximum - minimum) * plot_height
        for tick in range(5):
            value = minimum + (maximum - minimum) * tick / 4
            tick_y = y(value)
            canvas.create_line(left, tick_y, width - right, tick_y, fill=COLORS["line"])
            canvas.create_text(left - 8, tick_y, text=f"${value:,.0f}", anchor="e", fill=COLORS["muted"], font=("Segoe UI", 8))

        for values, color in ((baseline, COLORS["muted"]), (scenario, COLORS["green"])):
            points = [coordinate for period, value in enumerate(values) for coordinate in (x(period), y(value))]
            if len(points) >= 4:
                canvas.create_line(*points, fill=color, width=2)
            for period, value in enumerate(values):
                canvas.create_oval(x(period) - 2, y(value) - 2, x(period) + 2, y(value) + 2, fill=color, outline=color)

        canvas.create_text(left, 12, text="Baseline", anchor="w", fill=COLORS["muted"], font=("Segoe UI", 8))
        canvas.create_line(left + 48, 12, left + 68, 12, fill=COLORS["muted"], width=2)
        canvas.create_text(left + 82, 12, text="Scenario", anchor="w", fill=COLORS["green"], font=("Segoe UI", 8))
        canvas.create_line(left + 138, 12, left + 158, 12, fill=COLORS["green"], width=2)
        canvas.create_text(left, height - 7, text="Period 0", anchor="sw", fill=COLORS["muted"], font=("Segoe UI", 8))
        canvas.create_text(width - right, height - 7, text=f"Period {periods}", anchor="se", fill=COLORS["muted"], font=("Segoe UI", 8))

    def _build_advisor(self):
        top = ttk.Frame(self.advisor, style="App.TFrame")
        top.pack(fill="x", pady=(0, 12))
        ttk.Label(top, text="AI advisor", style="Section.TLabel").pack(side="left")
        self.summary_button = ttk.Button(top, text="Generate budget summary", command=self.generate_summary, style="Primary.TButton")
        self.summary_button.pack(side="right")
        self.summary = tk.Text(self.advisor, height=9, wrap="word", font=("Segoe UI", 10), bg=COLORS["surface"], fg=COLORS["ink"], relief="flat", padx=14, pady=12)
        self.summary.pack(fill="x", pady=(0, 14))
        self.summary.configure(state="disabled")
        ttk.Label(self.advisor, text="Ask about your budget", style="Section.TLabel").pack(anchor="w", pady=(0, 8))
        purchase_controls = ttk.Frame(self.advisor, style="App.TFrame")
        purchase_controls.pack(fill="x", pady=(0, 8))
        self.research_button = ttk.Button(purchase_controls, text="Find cheaper options", command=self.find_cheaper_options, style="Primary.TButton")
        self.research_button.pack(side="left")
        ttk.Button(purchase_controls, text="Review purchases", command=self.start_purchase_interview).pack(side="left", padx=(8, 0))
        self.chat = tk.Text(self.advisor, wrap="word", font=("Segoe UI", 9), bg=COLORS["surface"], fg=COLORS["ink"], relief="flat", padx=14, pady=12, state="disabled")
        self.chat.pack(fill="both", expand=True)
        self.chat.tag_configure("You", foreground=COLORS["green"], font=("Segoe UI Semibold", 9))
        self.chat.tag_configure("AI", foreground=COLORS["ink"], font=("Segoe UI Semibold", 9))
        chat_controls = ttk.Frame(self.advisor, style="App.TFrame")
        chat_controls.pack(fill="x", pady=(10, 0))
        self.question = ttk.Entry(chat_controls)
        self.question.pack(side="left", fill="x", expand=True)
        self.question.bind("<Return>", lambda _event: self.send_question())
        self.send_button = ttk.Button(chat_controls, text="Send", command=self.send_question, style="Primary.TButton")
        self.send_button.pack(side="left", padx=(8, 0))
        ttk.Button(chat_controls, text="Copy last reply", command=self.copy_last_ai_reply).pack(side="left", padx=(8, 0))
        self.clear_button = ttk.Button(chat_controls, text="Clear chat", command=self.clear_chat)
        self.clear_button.pack(side="left", padx=(8, 0))

    def _load_initial_budget(self):
        try:
            self.data_path.parent.mkdir(parents=True, exist_ok=True)
            if not self.data_path.exists():
                legacy_path = self.data_path.with_suffix("")
                if legacy_path.exists():
                    legacy_data, _ = read_protected_file(legacy_path)
                    write_protected_file(self.data_path, legacy_data)
                    legacy_path.unlink()
                else:
                    bundle_directory = Path(getattr(sys, "_MEIPASS", Path(__file__).resolve().parent))
                    bundled = bundle_directory / "budget.csv"
                    if bundled.exists():
                        write_protected_file(self.data_path, bundled.read_bytes())
            if self.data_path.exists():
                budget_bytes, encrypted = read_protected_file(self.data_path)
                self.df = load_budget(read_budget_csv(io.BytesIO(budget_bytes)))
                if not encrypted:
                    write_protected_file(self.data_path, budget_bytes)
        except (OSError, ValueError, SecureStorageError) as exc:
            messagebox.showerror(APP_NAME, f"Could not load the saved budget.\n\n{exc}")
        self._refresh()

    def _show_tutorial_if_needed(self):
        if self.tutorial_path.exists():
            return

        dialog = tk.Toplevel(self.root)
        dialog.title("Welcome to Business Budget AI")
        dialog.transient(self.root)
        dialog.resizable(False, False)
        dialog.configure(bg=COLORS["background"])
        dialog.grab_set()

        panel = ttk.Frame(dialog, style="App.TFrame", padding=(30, 26, 30, 22))
        panel.pack(fill="both", expand=True)
        step_label = ttk.Label(panel, style="Subtitle.TLabel")
        step_label.pack(anchor="w", pady=(0, 10))
        title_label = tk.Label(
            panel,
            bg=COLORS["background"],
            fg=COLORS["ink"],
            font=("Segoe UI Semibold", 19),
            anchor="w"
        )
        title_label.pack(fill="x", pady=(0, 14))
        body_label = tk.Label(
            panel,
            bg=COLORS["background"],
            fg=COLORS["ink"],
            font=("Segoe UI", 11),
            justify="left",
            anchor="nw",
            wraplength=590
        )
        body_label.pack(fill="both", expand=True)

        controls = ttk.Frame(panel, style="App.TFrame")
        controls.pack(fill="x", pady=(24, 0))
        back_button = ttk.Button(controls, text="Back")
        back_button.pack(side="left")
        skip_button = ttk.Button(controls, text="Skip tutorial")
        skip_button.pack(side="left", padx=(8, 0))
        next_button = ttk.Button(controls, style="Primary.TButton")
        next_button.pack(side="right")
        step = {"index": 0}

        def finish():
            try:
                self.tutorial_path.parent.mkdir(parents=True, exist_ok=True)
                self.tutorial_path.write_text("completed\n", encoding="ascii")
            except OSError as exc:
                messagebox.showwarning(
                    APP_NAME,
                    f"The tutorial is closing, but its completion could not be saved. It may appear again next time.\n\n{exc}",
                    parent=dialog
                )
            dialog.grab_release()
            dialog.destroy()

        def show_page():
            index = step["index"]
            page_title, page_body = TUTORIAL_PAGES[index]
            step_label.configure(text=f"GETTING STARTED  /  {index + 1} OF {len(TUTORIAL_PAGES)}")
            title_label.configure(text=page_title)
            body_label.configure(text=page_body)
            back_button.configure(state="normal" if index else "disabled", command=go_back)
            next_button.configure(text="Get started" if index == len(TUTORIAL_PAGES) - 1 else "Next", command=advance)

        def go_back():
            if step["index"] > 0:
                step["index"] -= 1
                show_page()

        def advance():
            if step["index"] == len(TUTORIAL_PAGES) - 1:
                finish()
            else:
                step["index"] += 1
                show_page()

        skip_button.configure(command=finish)
        dialog.protocol("WM_DELETE_WINDOW", finish)
        show_page()
        dialog.update_idletasks()
        width, height = 700, 390
        x = self.root.winfo_rootx() + (self.root.winfo_width() - width) // 2
        y = self.root.winfo_rooty() + (self.root.winfo_height() - height) // 2
        dialog.geometry(f"{width}x{height}+{max(0, x)}+{max(0, y)}")

    def _sort_table_by(self, column):
        if self._sort_column == column:
            self._sort_reverse = not self._sort_reverse
        else:
            self._sort_column = column
            self._sort_reverse = column in ("Budget", "Actual", "Variance", "Percent Used")
        self._populate_table()

    def _populate_table(self, analyzed=None):
        if analyzed is None:
            analyzed = analyze_budget(self.df) if not self.df.empty else self.df.copy()
        self.table.delete(*self.table.get_children())
        if analyzed.empty:
            return
        query = self.filter_var.get().strip().casefold() if hasattr(self, "filter_var") else ""
        records = analyzed.to_dict("records")
        if query:
            records = [
                r for r in records
                if query in str(r.get("Category", "")).casefold()
                or query in str(r.get("Type", "")).casefold()
                or query in str(r.get("Status", "")).casefold()
            ]
        if self._sort_column:
            col = self._sort_column
            records.sort(
                key=lambda r: (float(r.get(col, 0)) if isinstance(r.get(col), (int, float)) and not pd.isna(r.get(col)) else str(r.get(col, "")).casefold()),
                reverse=self._sort_reverse,
            )
        for row in records:
            status = row.get("Status", "")
            tag = "over" if status == "Over Budget" else "warning" if status in ("Warning", "Below Target") else "good"
            percent = row.get("Percent Used", float("nan"))
            percent_text = f"{percent:.1f}%" if pd.notna(percent) and math.isfinite(float(percent)) else "N/A"
            values = (
                row["Category"], row["Type"], f"${row['Budget']:,.2f}", f"${row['Actual']:,.2f}",
                f"${row['Variance']:,.2f}", percent_text, status
            )
            self.table.insert("", "end", values=values, tags=(tag,))

    def _refresh(self):
        try:
            analyzed = analyze_budget(self.df) if not self.df.empty else self.df.copy()
            kpis = budget_kpis(analyzed)
        except ValueError as exc:
            messagebox.showerror(APP_NAME, str(exc))
            return
        for key in ("Revenue", "Expenses", "Profit"):
            self.metric_values[key].configure(text=f"${kpis[key]:,.2f}")
        self.metric_values["Profit"].configure(
            foreground=COLORS["green"] if kpis["Profit"] >= 0 else COLORS["red"]
        )
        self.metric_values["Margin"].configure(
            text=f"{kpis['ProfitMargin']:.1f}%",
            foreground=COLORS["green"] if kpis["ProfitMargin"] >= 10 else (COLORS["amber"] if kpis["ProfitMargin"] >= 0 else COLORS["red"])
        )
        if kpis["OverBudgetCount"] > 0:
            self.metric_values["Health"].configure(
                text=f"{kpis['OverBudgetCount']} Over (${kpis['OverspendAmount']:,.0f})",
                foreground=COLORS["red"]
            )
        elif kpis["WarningCount"] > 0:
            self.metric_values["Health"].configure(
                text=f"{kpis['WarningCount']} At Risk",
                foreground=COLORS["amber"]
            )
        else:
            self.metric_values["Health"].configure(
                text="All on track" if not analyzed.empty else "--",
                foreground=COLORS["green"] if not analyzed.empty else COLORS["ink"]
            )
        self._populate_table(analyzed)
        signature = budget_signature(self.df)
        signature_changed = signature != self.current_signature
        if signature_changed:
            self.current_signature = signature
        self._draw_summary_chart(force=signature_changed)
        if signature_changed:
            self.analysis_text = ""
            try:
                self.chat_memory, self.chat_history, self.messages = load_conversation(signature)
            except SecureStorageError as exc:
                self.chat_memory, self.chat_history, self.messages = "", [], []
                messagebox.showerror(APP_NAME, f"Could not unlock saved chat history.\n\n{exc}")
            self._show_summary("")
            self._show_chat(full_reset=True)
        self.status_var.set(f"{len(self.df)} budget line{'s' if len(self.df) != 1 else ''}  |  {self.data_path}")

    def _validated_budget(self, frame):
        return load_budget(frame[FIELDS])

    def _save_current(self, quiet=False):
        try:
            self.data_path.parent.mkdir(parents=True, exist_ok=True)
            csv_buffer = io.StringIO()
            self.df[FIELDS].to_csv(csv_buffer, index=False)
            write_protected_file(self.data_path, csv_buffer.getvalue().encode("utf-8"))
            if not quiet:
                self.status_var.set(f"Saved to {self.data_path}")
        except (OSError, SecureStorageError) as exc:
            messagebox.showerror(APP_NAME, f"Could not save the budget.\n\n{exc}")

    def save_csv(self):
        self._save_current()

    def export_csv(self):
        path = filedialog.asksaveasfilename(
            title="Export encrypted budget backup",
            defaultextension=".budget.enc",
            filetypes=[("Encrypted budget backups", "*.budget.enc")],
            initialfile="business_budget.budget.enc"
        )
        if not path:
            return
        try:
            csv_buffer = io.StringIO()
            self.df[FIELDS].to_csv(csv_buffer, index=False)
            write_protected_file(path, csv_buffer.getvalue().encode("utf-8"))
            self.status_var.set(f"Exported encrypted backup to {path}")
        except (OSError, SecureStorageError) as exc:
            messagebox.showerror(APP_NAME, f"Could not export the encrypted backup.\n\n{exc}")

    def open_csv(self):
        path = filedialog.askopenfilename(
            title="Open budget file",
            filetypes=[
                ("Budget files", "*.csv *.budget.enc"),
                ("CSV files", "*.csv"),
                ("Encrypted budget backups", "*.budget.enc"),
                ("All files", "*.*")
            ]
        )
        if not path:
            return
        try:
            budget_bytes, _ = read_protected_file(path)
            raw = read_budget_csv(io.BytesIO(budget_bytes))
            mapping = self._choose_columns(raw)
            if mapping is None:
                return
            self.df = load_budget(raw, mapping)
            self._refresh()
            self._save_current(quiet=True)
            self.status_var.set(f"Loaded {Path(path).name}")
        except (OSError, ValueError, SecureStorageError) as exc:
            messagebox.showerror(APP_NAME, f"Could not import this CSV.\n\n{exc}")

    def _choose_columns(self, raw):
        suggestions = suggest_budget_columns(raw.columns)
        dialog = tk.Toplevel(self.root)
        dialog.title("Match CSV columns")
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.resizable(False, False)
        body = ttk.Frame(dialog, padding=20)
        body.pack(fill="both", expand=True)
        ttk.Label(body, text="Match the columns in your file", style="Section.TLabel").grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 14))
        choices = {}
        for index, field in enumerate(FIELDS, start=1):
            ttk.Label(body, text=field).grid(row=index, column=0, sticky="w", padx=(0, 18), pady=5)
            variable = tk.StringVar(value=suggestions.get(field, str(raw.columns[0]) if len(raw.columns) == 1 else "Choose a column"))
            combo = ttk.Combobox(body, textvariable=variable, values=["Choose a column", *list(raw.columns)], state="readonly", width=30)
            combo.grid(row=index, column=1, sticky="ew", pady=5)
            choices[field] = variable
        result = {"mapping": None}

        def confirm():
            selected = {field: variable.get() for field, variable in choices.items()}
            if any(value == "Choose a column" for value in selected.values()):
                messagebox.showwarning("Match CSV columns", "Choose a column for each field.", parent=dialog)
                return
            result["mapping"] = selected
            dialog.destroy()

        buttons = ttk.Frame(body)
        buttons.grid(row=5, column=0, columnspan=2, sticky="e", pady=(14, 0))
        ttk.Button(buttons, text="Cancel", command=dialog.destroy).pack(side="left", padx=(0, 8))
        ttk.Button(buttons, text="Import", command=confirm, style="Primary.TButton").pack(side="left")
        dialog.update_idletasks()
        dialog.geometry(f"+{self.root.winfo_rootx() + 180}+{self.root.winfo_rooty() + 120}")
        self.root.wait_window(dialog)
        return result["mapping"]

    def add_row(self):
        values = self._edit_dialog()
        if values is not None:
            self.df = self._validated_budget(pd.concat([self.df, pd.DataFrame([values])], ignore_index=True))
            self._refresh()
            self._save_current(quiet=True)

    def _selected_df_index(self):
        selected = self.table.selection()
        if len(selected) != 1:
            return None
        row_values = self.table.item(selected[0], "values")
        if not row_values:
            return None
        cat_name = str(row_values[0])
        matches = self.df.index[self.df["Category"].astype(str) == cat_name].tolist()
        return matches[0] if matches else self.table.index(selected[0])

    def _show_row_context_menu(self, event):
        row_id = self.table.identify_row(event.y)
        if row_id:
            self.table.selection_set(row_id)
            self.row_menu.tk_popup(event.x_root, event.y_root)

    def _context_find_cheaper(self):
        idx = self._selected_df_index()
        if idx is None or self.busy:
            return
        row = self.df.iloc[idx]
        cat = str(row["Category"])
        actual = float(row["Actual"])
        mapped = category_to_supply_search(cat)
        if not mapped:
            # Service-type or unrecognized categories (e.g. Vehicle, Insurance, Rent) are not retail
            # products; searching the raw name returns toys/novelties, so ask the advisor instead.
            self.status_var.set(f"'{cat}' is a service cost - asking the AI advisor for savings levers instead of a product search")
            self._context_ask_ai()
            return
        prod, req = mapped
        self.notebook.select(self.advisor)
        self._start_product_research({
            "product": prod,
            "current_unit_price": max(15.0, min(actual, 85.0)) if actual > 100 else max(10.0, actual),
            "monthly_quantity": 10.0,
            "requirements": req,
            "region": "US",
        })

    def _context_ask_ai(self):
        idx = self._selected_df_index()
        if idx is None or self.busy:
            return
        row = self.df.iloc[idx]
        cat, rtype, bud, act = row["Category"], row["Type"], float(row["Budget"]), float(row["Actual"])
        diff = act - bud
        self.notebook.select(self.advisor)
        self.question.delete(0, "end")
        self.question.insert(
            0,
            f"Analyze our '{cat}' ({rtype}) category (Budget: ${bud:,.2f}, Actual: ${act:,.2f}, Variance: ${diff:+,.2f}) and give me 3 specific ways to improve it."
        )
        self.send_question()

    def _context_simulate_cut(self):
        idx = self._selected_df_index()
        if idx is None:
            return
        row = self.df.iloc[idx]
        cat, rtype, act = str(row["Category"]), str(row["Type"]), float(row["Actual"])
        kpis = budget_kpis(self.df)
        if rtype == "Expense" and kpis["Expenses"] > 0:
            pct_cut = -(act * 0.15 / kpis["Expenses"] * 100.0)
            self.scenario_inputs["revenue_change"].set("0")
            self.scenario_inputs["expense_change"].set(f"{pct_cut:.2f}")
            self.scenario_inputs["one_time_cost"].set("0")
            self.scenario_inputs["periods"].set("12")
        elif rtype == "Revenue" and kpis["Revenue"] > 0:
            pct_gain = (act * 0.15 / kpis["Revenue"] * 100.0)
            self.scenario_inputs["revenue_change"].set(f"{pct_gain:.2f}")
            self.scenario_inputs["expense_change"].set("0")
            self.scenario_inputs["one_time_cost"].set("0")
            self.scenario_inputs["periods"].set("12")
        self.notebook.select(self.scenario)
        self.calculate_scenario(show_error=False)
        self.scenario_status_var.set(f"Simulated a 15% improvement on '{cat}' over 12 periods.")

    def _edit_selected(self, _event=None):
        index = self._selected_df_index()
        if index is None:
            return
        current = self.df.iloc[index].to_dict()
        values = self._edit_dialog(current)
        if values is not None:
            updated = self.df.copy()
            for field in FIELDS:
                updated.at[index, field] = values[field]
            try:
                self.df = self._validated_budget(updated)
                self._refresh()
                self._save_current(quiet=True)
            except ValueError as exc:
                messagebox.showerror(APP_NAME, str(exc))

    def _edit_dialog(self, current=None):
        dialog = tk.Toplevel(self.root)
        dialog.title("Edit budget line" if current else "Add budget line")
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.resizable(False, False)
        body = ttk.Frame(dialog, padding=20)
        body.pack(fill="both", expand=True)
        variables = {field: tk.StringVar(value=str(current.get(field, "") if current else ("Expense" if field == "Type" else ""))) for field in FIELDS}
        for index, field in enumerate(FIELDS):
            ttk.Label(body, text=field).grid(row=index, column=0, sticky="w", padx=(0, 16), pady=6)
            if field == "Type":
                widget = ttk.Combobox(body, textvariable=variables[field], values=["Revenue", "Expense"], state="readonly", width=28)
            else:
                widget = ttk.Entry(body, textvariable=variables[field], width=31)
            widget.grid(row=index, column=1, sticky="ew", pady=6)
        result = {"values": None}

        def confirm():
            values = {field: variables[field].get().strip() for field in FIELDS}
            if not values["Category"]:
                messagebox.showwarning(APP_NAME, "Enter a category name.", parent=dialog)
                return
            try:
                normalized = load_budget(pd.DataFrame([values]))
            except ValueError as exc:
                messagebox.showerror(APP_NAME, str(exc), parent=dialog)
                return
            result["values"] = normalized.iloc[0].to_dict()
            dialog.destroy()

        buttons = ttk.Frame(body)
        buttons.grid(row=len(FIELDS), column=0, columnspan=2, sticky="e", pady=(14, 0))
        ttk.Button(buttons, text="Cancel", command=dialog.destroy).pack(side="left", padx=(0, 8))
        ttk.Button(buttons, text="Save line", command=confirm, style="Primary.TButton").pack(side="left")
        dialog.update_idletasks()
        dialog.geometry(f"+{self.root.winfo_rootx() + 180}+{self.root.winfo_rooty() + 100}")
        self.root.wait_window(dialog)
        return result["values"]

    def remove_rows(self):
        selected = self.table.selection()
        if not selected:
            return
        selected_cats = {
            str(self.table.item(item, "values")[0]).strip().lower()
            for item in selected
            if self.table.item(item, "values")
        }
        if not selected_cats:
            return
        keep_mask = ~self.df["Category"].astype(str).str.strip().str.lower().isin(selected_cats)
        updated = self.df.loc[keep_mask].reset_index(drop=True)
        self.df = updated[FIELDS]
        self._refresh()
        self._save_current(quiet=True)

    def _set_busy(self, busy, status):
        self.busy = busy
        self.summary_button.configure(state="disabled" if busy else "normal")
        self.send_button.configure(state="disabled" if busy else "normal")
        self.research_button.configure(state="disabled" if busy else "normal")
        self.quickbooks_button.configure(state="disabled" if busy else "normal")
        self.status_var.set(status)
        if busy and not self._poll_scheduled:
            self._poll_scheduled = True
            self.root.after(75, self._poll_tasks)

    def _quickbooks_credentials_dialog(self, existing=None):
        dialog = tk.Toplevel(self.root)
        dialog.title("Connect QuickBooks Online")
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.resizable(False, False)
        body = ttk.Frame(dialog, padding=20)
        body.pack(fill="both", expand=True)
        ttk.Label(
            body,
            text=(
                "Create a QuickBooks Online app in the Intuit Developer Portal and enter its sandbox credentials. "
                "Register this exact sandbox redirect URI: http://localhost:8765/callback."
            ),
            wraplength=430,
            justify="left"
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 12))
        ttk.Label(
            body,
            text=(
                "The Intuit accounting permission is broader than read-only. This app only sends GET requests "
                "for budgets, accounts, and Profit & Loss reports; it has no company-data write calls."
            ),
            wraplength=430,
            justify="left"
        ).grid(row=1, column=0, columnspan=2, sticky="w", pady=(0, 12))
        client_id_var = tk.StringVar(value=(existing or {}).get("client_id", ""))
        client_secret_var = tk.StringVar(value=(existing or {}).get("client_secret", ""))
        ttk.Label(body, text="Client ID").grid(row=2, column=0, sticky="w", padx=(0, 14), pady=5)
        ttk.Entry(body, textvariable=client_id_var, width=42).grid(row=2, column=1, sticky="ew", pady=5)
        ttk.Label(body, text="Client secret").grid(row=3, column=0, sticky="w", padx=(0, 14), pady=5)
        ttk.Entry(body, textvariable=client_secret_var, width=42, show="*").grid(row=3, column=1, sticky="ew", pady=5)
        result = {"connection": None}

        def confirm():
            client_id = client_id_var.get().strip()
            client_secret = client_secret_var.get().strip()
            if not client_id or not client_secret:
                messagebox.showwarning(APP_NAME, "Enter both Intuit app credentials.", parent=dialog)
                return
            result["connection"] = {
                "client_id": client_id,
                "client_secret": client_secret,
                "environment": "sandbox"
            }
            dialog.destroy()

        buttons = ttk.Frame(body)
        buttons.grid(row=4, column=0, columnspan=2, sticky="e", pady=(14, 0))
        ttk.Button(buttons, text="Cancel", command=dialog.destroy).pack(side="left", padx=(0, 8))
        ttk.Button(buttons, text="Authorize and import", command=confirm, style="Primary.TButton").pack(side="left")
        dialog.bind("<Return>", lambda _event: confirm())
        dialog.update_idletasks()
        dialog.geometry(f"+{self.root.winfo_rootx() + 120}+{self.root.winfo_rooty() + 100}")
        self.root.wait_window(dialog)
        return result["connection"]

    def connect_quickbooks(self):
        if self.busy:
            return
        try:
            connection = load_connection()
        except (OSError, SecureStorageError, QuickBooksError):
            connection = {}

        signature = self.current_signature
        self._set_busy(True, "Connecting to QuickBooks and importing budget data...")

        def work():
            try:
                client = QuickBooksClient(connection)
                client.connect()
                budget, accounts, report = client.import_latest_budget()
                rows = map_quickbooks_budget(budget, accounts, report)
                self.task_queue.put(("quickbooks", signature, {
                    "rows": rows,
                    "budget_name": budget.get("Name", "QuickBooks budget"),
                    "start_date": budget.get("StartDate", ""),
                    "end_date": budget.get("EndDate", "")
                }, None))
            except Exception as exc:
                self.task_queue.put(("quickbooks", signature, None, str(exc)))

        threading.Thread(target=work, daemon=True).start()

    def generate_summary(self):
        if self.df.empty:
            messagebox.showinfo(APP_NAME, "Add or import budget lines before generating a summary.")
            return
        snapshot = analyze_budget(self.df.copy())
        signature = self.current_signature
        self._set_busy(True, "Preparing your budget summary...")
        self.summary_button.configure(text="Working...")

        def work():
            try:
                result = analyze(snapshot)
                self.task_queue.put(("summary", signature, result, None))
            except Exception as exc:
                self.task_queue.put(("summary", signature, None, str(exc)))

        threading.Thread(target=work, daemon=True).start()

    def send_question(self):
        question = self.question.get().strip()
        if not question or self.busy:
            return
        if self.df.empty:
            messagebox.showinfo(APP_NAME, "Add or import budget lines before asking a question.")
            return
        self.question.delete(0, "end")
        snapshot = analyze_budget(self.df.copy())
        signature = self.current_signature
        previous_analysis = self.analysis_text
        history = list(self.chat_history)
        memory = self.chat_memory
        self.messages.append(("You", question))
        self._show_chat()
        self._set_busy(True, "Thinking about your budget...")

        def work():
            try:
                answer, new_memory, new_history = chat_with_memory(snapshot, question, previous_analysis, history, memory)
                transcript = [*self.messages, ("AI", answer)]
                save_conversation(signature, new_memory, new_history, transcript)
                self.task_queue.put(("chat", signature, (answer, new_memory, new_history), None))
            except Exception as exc:
                self.task_queue.put(("chat", signature, None, str(exc)))

        threading.Thread(target=work, daemon=True).start()

    def start_purchase_interview(self):
        if self.busy:
            return
        self.question.delete(0, "end")
        self.question.insert(0, "Interview me about the products and supplies my business buys, one question at a time.")
        self.send_question()

    def find_cheaper_options(self):
        if self.busy:
            return
        dialog = tk.Toplevel(self.root)
        dialog.title("Find cheaper options")
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.resizable(False, False)
        body = ttk.Frame(dialog, padding=20)
        body.pack(fill="both", expand=True)
        ttk.Label(
            body,
            text="Searches public listings only. No orders or payments are made.",
            style="MetricLabel.TLabel"
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 10))
        fields = (
            ("Product, brand, or model", "product"),
            ("Current unit price", "price"),
            ("Units purchased per month", "quantity"),
            ("Must-have specifications", "requirements"),
            ("Country or region", "region")
        )
        variables = {key: tk.StringVar() for _, key in fields}
        for index, (label, key) in enumerate(fields):
            ttk.Label(body, text=label).grid(row=index + 1, column=0, sticky="w", padx=(0, 16), pady=6)
            ttk.Entry(body, textvariable=variables[key], width=34).grid(row=index + 1, column=1, sticky="ew", pady=6)

        def search():
            product = variables["product"].get().strip()
            try:
                current_price = float(variables["price"].get().strip().replace("$", "").replace(",", ""))
                monthly_quantity = float(variables["quantity"].get().strip().replace(",", ""))
            except ValueError:
                messagebox.showwarning(APP_NAME, "Enter a valid unit price and monthly quantity.", parent=dialog)
                return
            if (
                not product
                or not math.isfinite(current_price)
                or not math.isfinite(monthly_quantity)
                or current_price <= 0
                or monthly_quantity <= 0
            ):
                messagebox.showwarning(APP_NAME, "Enter a product and positive price and monthly quantity.", parent=dialog)
                return
            details = {
                "product": product,
                "current_unit_price": current_price,
                "monthly_quantity": monthly_quantity,
                "requirements": variables["requirements"].get().strip(),
                "region": variables["region"].get().strip()
            }
            dialog.destroy()
            self._start_product_research(details)

        buttons = ttk.Frame(body)
        buttons.grid(row=len(fields) + 1, column=0, columnspan=2, sticky="e", pady=(14, 0))
        ttk.Button(buttons, text="Cancel", command=dialog.destroy).pack(side="left", padx=(0, 8))
        ttk.Button(buttons, text="Search", command=search, style="Primary.TButton").pack(side="left")
        dialog.update_idletasks()
        dialog.geometry(f"+{self.root.winfo_rootx() + 150}+{self.root.winfo_rooty() + 100}")
        dialog.bind("<Return>", lambda _event: search())

    def configure_shopping_api(self):
        dialog = tk.Toplevel(self.root)
        dialog.title("Shopping API key")
        dialog.transient(self.root)
        dialog.grab_set()
        dialog.resizable(False, False)
        body = ttk.Frame(dialog, padding=20)
        body.pack(fill="both", expand=True)
        ttk.Label(
            body,
            text=(
                "Enter your SerpApi key to search Google Shopping offers. The free tier currently includes "
                "250 searches per month; one product lookup can use up to four requests (one Shopping search "
                "and up to three offer lookups). Your key is encrypted "
                "on this computer and is never sent to the AI model."
            ),
            wraplength=430,
            justify="left"
        ).grid(row=0, column=0, columnspan=2, sticky="w", pady=(0, 12))
        key_var = tk.StringVar(value="")
        ttk.Label(body, text="SerpApi key").grid(row=1, column=0, sticky="w", padx=(0, 14), pady=6)
        ttk.Entry(body, textvariable=key_var, width=42, show="*").grid(row=1, column=1, sticky="ew", pady=6)
        result = {"configured": False}

        def save_key():
            try:
                save_api_key(key_var.get())
            except (ValueError, SecureStorageError) as exc:
                messagebox.showwarning(APP_NAME, str(exc), parent=dialog)
                return
            result["configured"] = True
            dialog.destroy()

        def forget_key():
            try:
                clear_api_key()
            except SecureStorageError as exc:
                messagebox.showerror(APP_NAME, f"Could not remove the saved key.\n\n{exc}", parent=dialog)
                return
            result["configured"] = True
            dialog.destroy()

        buttons = ttk.Frame(body)
        buttons.grid(row=2, column=0, columnspan=2, sticky="e", pady=(14, 0))
        ttk.Button(buttons, text="Cancel", command=dialog.destroy).pack(side="left", padx=(0, 8))
        ttk.Button(buttons, text="Forget key", command=forget_key).pack(side="left", padx=(0, 8))
        ttk.Button(buttons, text="Save key", command=save_key, style="Primary.TButton").pack(side="left")
        dialog.bind("<Return>", lambda _event: save_key())
        dialog.update_idletasks()
        dialog.geometry(f"+{self.root.winfo_rootx() + 150}+{self.root.winfo_rooty() + 100}")
        self.root.wait_window(dialog)
        return result["configured"]

    def _start_product_research(self, details):
        if self.df.empty:
            messagebox.showinfo(APP_NAME, "Add or import budget lines before researching purchases.")
            return
        snapshot = analyze_budget(self.df.copy())
        expense_budget = snapshot[snapshot["Type"] == "Expense"]
        if expense_budget.empty:
            messagebox.showinfo(APP_NAME, "Add an expense category to the budget before researching purchases.")
            return
        signature = self.current_signature
        history = list(self.chat_history)
        memory = self.chat_memory
        self.messages.append((
            "You",
            f"Find cheaper options for {details['product']} at ${details['current_unit_price']:.2f} per unit, "
            f"purchased {details['monthly_quantity']:g} per month."
        ))
        self._show_chat()
        self._set_busy(True, "Searching product alternatives...")

        def work():
            try:
                answer, new_memory, new_history = find_product_alternatives(
                    **details,
                    budget_context=expense_budget.to_string(index=False),
                    conversation_history=history,
                    memory=memory
                )
                transcript = [*self.messages, ("AI", answer)]
                save_conversation(signature, new_memory, new_history, transcript)
                self.task_queue.put(("chat", signature, (answer, new_memory, new_history), None))
            except Exception as exc:
                self.task_queue.put(("chat", signature, None, str(exc)))

        threading.Thread(target=work, daemon=True).start()

    def copy_last_ai_reply(self):
        ai_replies = [msg for sender, msg in self.messages if sender == "AI"]
        if not ai_replies:
            messagebox.showinfo(APP_NAME, "No AI reply to copy yet.")
            return
        self.root.clipboard_clear()
        self.root.clipboard_append(ai_replies[-1])
        self.status_var.set("Copied latest AI advisor reply to clipboard")

    def open_executive_report(self):
        if self.df.empty:
            messagebox.showinfo(APP_NAME, "Add or import budget lines before generating the executive report.")
            return
        try:
            html_content = generate_executive_report_html(
                self.df,
                analysis_text=self.analysis_text,
                scenario_tuple=self._last_scenario,
                messages=self.messages,
            )
            report_path = self.data_path.with_name("Executive_Financial_Report.html")
            report_path.parent.mkdir(parents=True, exist_ok=True)
            report_path.write_text(html_content, encoding="utf-8")
            webbrowser.open(report_path.as_uri())
            self.status_var.set(f"Opened Executive Financial Report ({report_path})")
        except Exception as exc:
            messagebox.showerror(APP_NAME, f"Could not generate the executive report.\n\n{exc}")

    def clear_chat(self):
        if self.busy or not self.messages:
            return
        clear_conversation(self.current_signature)
        self.messages = []
        self.chat_history = []
        self.chat_memory = ""
        self._show_chat(full_reset=True)

    def _poll_tasks(self):
        self._poll_scheduled = False
        try:
            while True:
                kind, signature, result, error = self.task_queue.get_nowait()
                if signature != self.current_signature:
                    self._set_busy(False, "Ready")
                    self.summary_button.configure(text="Generate budget summary")
                    continue
                self._set_busy(False, "Ready")
                self.summary_button.configure(text="Generate budget summary")
                if error:
                    title = "QuickBooks import failed" if kind == "quickbooks" else "AI request failed"
                    messagebox.showerror(APP_NAME, f"{title}.\n\n{error}")
                    if kind == "chat" and self.messages and self.messages[-1][0] == "You":
                        self.messages.pop()
                        self._show_chat(full_reset=True)
                    continue
                if kind == "summary":
                    self.analysis_text = result
                    self._show_summary(result)
                elif kind == "quickbooks":
                    try:
                        self.df = load_budget(pd.DataFrame(result["rows"]))
                        self._refresh()
                        self._save_current(quiet=True)
                        self.status_var.set(
                            f"Connected QuickBooks: {result['budget_name']} ({len(result['rows'])} accounts)"
                        )
                    except (OSError, ValueError, SecureStorageError) as exc:
                        messagebox.showerror(APP_NAME, f"Could not import QuickBooks budget data.\n\n{exc}")
                else:
                    answer, self.chat_memory, self.chat_history = result
                    self.messages.append(("AI", answer))
                    self._show_chat()
        except queue.Empty:
            pass
        if self.busy or not self.task_queue.empty():
            self._poll_scheduled = True
            self.root.after(75, self._poll_tasks)

    def _show_summary(self, text):
        self.summary.configure(state="normal")
        self.summary.delete("1.0", "end")
        self.summary.insert("1.0", text or "Generate a summary to get a practical read on revenue, costs, and next steps.")
        self.summary.configure(state="disabled")

    def _show_chat(self, full_reset=False):
        self.chat.configure(state="normal")
        if full_reset or self._rendered_count > len(self.messages):
            self.chat.delete("1.0", "end")
            self._rendered_count = 0
            self._link_index = 0
        new_messages = self.messages[self._rendered_count:]
        for sender, message in new_messages:
            self.chat.insert("end", f"{sender}\n", sender)
            cursor = 0
            for match in _URL_RE.finditer(message):
                self.chat.insert("end", message[cursor:match.start()])
                url = match.group().rstrip(".,;:!?) ]}")
                tag = f"source_link_{self._link_index}"
                self._link_index += 1
                self.chat.insert("end", url, tag)
                self.chat.tag_configure(tag, foreground=COLORS["green"], underline=True)
                self.chat.tag_bind(tag, "<Button-1>", lambda _event, target=url: webbrowser.open(target))
                self.chat.tag_bind(tag, "<Enter>", lambda _event: self.chat.configure(cursor="hand2"))
                self.chat.tag_bind(tag, "<Leave>", lambda _event: self.chat.configure(cursor=""))
                cursor = match.end()
            self.chat.insert("end", f"{message[cursor:]}\n\n")
        self._rendered_count = len(self.messages)
        self.chat.see("end")
        self.chat.configure(state="disabled")


def main():
    root = tk.Tk()
    BudgetApp(root)
    root.mainloop()


if __name__ == "__main__":
    main()
