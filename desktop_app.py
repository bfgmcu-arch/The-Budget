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


APP_NAME = "Abel"
_URL_RE = re.compile(r"https?://[^\s<>]+")
FIELDS = ["Category", "Type", "Budget", "Actual"]
TUTORIAL_PAGES = (
    (
        "Welcome to Abel",
        "Use this workspace to understand business income and costs. Budget overview shows revenue, expenses, and profit. Abel answers questions using the budget you load."
    ),
    (
        "Set up your budget",
        "Choose Open CSV to import your existing budget. Match the columns for Category, Type, Budget, and Actual. Or choose Add row to enter items manually. Double-click a row to edit it. Save budget changes to keep the current version."
    ),
    (
        "Ask Abel",
        "Generate budget summary for an overview, or ask a question in the Abel advisor tab. Use Scenario planner to test changes to revenue, expenses, and one-time costs. Audit transactions checks for duplicate charges and recurring spikes."
    ),
    (
        "Your data and product searches",
        "Saved budgets, chat history, API keys, and exported backups are encrypted using this Windows account's credential store. Encrypted backups are tied to this account and computer. Abel keeps your local financial data protected."
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
    return base / "Abel" / "budget.csv.enc"


# rest of the file remains unchanged below this point
