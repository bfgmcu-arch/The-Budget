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
import security
security.ensure_integrity_module()
import integrity
from security import enforce_runtime_authorization, is_runtime_authorized, require_launch_authorization

enforce_runtime_authorization()


APP_NAME = "Abel"
ABEL_LOGO_PNG_B64 = "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"
ABEL_ICON_PNG_B64 = "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"
_URL_RE = re.compile(r"https?://[^\s<>]+")
FIELDS = ["Category", "Type", "Budget", "Actual"]
TUTORIAL_PAGES = (
    (
        "Welcome to Abel",
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
        "Saved budgets, chat history, API keys, and exported backups are encrypted using your operating system's secure credential store. Encrypted backups are tied to this account and computer. The AI model runs locally. Product name, specifications, and region are queried across public retail and supplier listings; budget amounts and current price are not sent. QuickBooks imports read budget and Profit & Loss account totals only."
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
    if sys.platform == "darwin":
        base = Path.home() / "Library" / "Application Support"
    elif os.name == "nt":
        base = Path(os.environ.get("LOCALAPPDATA", Path.home() / "AppData" / "Local"))
    else:
        base = Path(os.environ.get("XDG_DATA_HOME", Path.home() / ".local" / "share"))
    target = base / "Abel"
    old = base / "BusinessBudgetAI"
    if old.exists() and not target.exists():
        try:
            old.rename(target)
        except Exception:
            return old / "budget.csv.enc"
    return target / "budget.csv.enc"


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
        try:
            self._app_icon = tk.PhotoImage(data=ABEL_ICON_PNG_B64)
            self.root.iconphoto(True, self._app_icon)
        except Exception:
            pass
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
        ttk.Label(heading, text="Abel", style="Title.TLabel").pack(anchor="w")
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
        dialog.title("Welcome to Abel")
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


def show_splash_screen(root, duration_ms: int = 2200, on_complete=None):
    """Displays a modern splash screen for Abel / Student Led Business Solutions."""
    splash = tk.Toplevel(root)
    splash.overrideredirect(True)
    splash.configure(bg="#18221f")

    width, height = 540, 340
    sw = splash.winfo_screenwidth()
    sh = splash.winfo_screenheight()
    x = max(0, (sw - width) // 2)
    y = max(0, (sh - height) // 2)
    splash.geometry(f"{width}x{height}+{x}+{y}")
    splash.attributes("-topmost", True)

    canvas = tk.Canvas(
        splash,
        bg="#18221f",
        highlightthickness=1,
        highlightbackground="#283833",
        width=width,
        height=height
    )
    canvas.pack(fill="both", expand=True)

    # Center Emblem Logo
    try:
        logo_img = tk.PhotoImage(data=ABEL_LOGO_PNG_B64)
        canvas._logo_img = logo_img
        canvas.create_image(width // 2, 84, image=logo_img, anchor="center")
    except Exception:
        pass

    # Abel Title
    canvas.create_text(
        width // 2,
        158,
        text="Abel",
        font=("Segoe UI", 36, "bold"),
        fill="#ffffff",
        anchor="center"
    )

    # Subtitle: property of Student Led Business Solutions
    canvas.create_text(
        width // 2,
        204,
        text="property of Student Led Business Solutions",
        font=("Segoe UI", 11),
        fill="#8fbdae",
        anchor="center"
    )

    # Accent divider
    canvas.create_line(
        180, 238, 360, 238,
        width=2, fill="#176b52"
    )

    # Status indicator
    canvas.create_text(
        width // 2,
        282,
        text="Starting Abel...",
        font=("Segoe UI", 9),
        fill="#64776f",
        anchor="center"
    )

    dismissed = [False]

    def dismiss(_event=None):
        if dismissed[0]:
            return
        dismissed[0] = True
        try:
            splash.destroy()
        except Exception:
            pass
        if on_complete:
            on_complete()

    # Allow clicking or pressing a key on the splash screen to skip/dismiss
    splash.bind("<Button-1>", dismiss)
    canvas.bind("<Button-1>", dismiss)
    splash.bind("<Key>", dismiss)

    root.after(duration_ms, dismiss)
    splash.update()
    return splash


def main():
    if not require_launch_authorization():
        return
    root = tk.Tk()
    root.withdraw()

    # Center the main window on screen so it reveals gracefully
    win_w, win_h = 1180, 780
    sw = root.winfo_screenwidth()
    sh = root.winfo_screenheight()
    mx = max(0, (sw - win_w) // 2)
    my = max(0, (sh - win_h) // 2)
    root.geometry(f"{win_w}x{win_h}+{mx}+{my}")

    # Build the app behind the splash screen
    BudgetApp(root)

    def reveal_app():
        root.deiconify()
        root.lift()
        root.focus_force()

    show_splash_screen(root, duration_ms=2200, on_complete=reveal_app)
    root.mainloop()


if __name__ == "__main__":
    main()
