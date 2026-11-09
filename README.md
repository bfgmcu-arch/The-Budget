# Business Budget AI

Business Budget AI is a desktop app for reviewing a business budget, comparing planned and actual figures, and looking into possible ways to reduce costs. It also includes transaction checks, supplier price comparisons, and QuickBooks import support.

## What it does

- Import a budget from a CSV file or enter budget lines in the app.
- Review revenue, expenses, profit, and differences between budgeted and actual amounts.
- Try simple financial scenarios, such as a change in revenue or expenses.
- Ask a local AI model questions about the figures in the loaded budget.
- Check bank transaction CSV files for possible duplicate charges and price changes.
- Search for lower-priced product listings.
- Import budget information from QuickBooks Online, QuickBooks Desktop on Windows, or certain QuickBooks exports.
- Save budget data and chat history locally.

## Getting started

### Install the Windows app

Download the latest installer from the GitHub Releases page and run the `.exe` file. The installer:

- installs the app to your local `Program Files` folder
- creates a desktop/start-menu shortcut
- sets up the local Python dependencies needed for the app
- starts the app after installation finishes

Release assets are the recommended installation method for most Windows users.

### Requirements

- Windows 10 or newer
- Python 3 (only needed if running from source)
- Ollama, with a supported local model available
- An operating-system credential store supported by the `keyring` package

The default model is `qwen2.5:0.5b`. The app also checks for other local models if the configured model is unavailable.

### Run from source

Clone the repository and install the Python packages:

```bash
git clone https://github.com/bfgmcu-arch/The-Budget.git
cd The-Budget
python -m pip install -r requirements.txt
```

Start the app:

```bash
python app.py
```

On Windows, you can also use `start_budget_ai.bat` after installing the dependencies.

## Working with budgets

Budget files should contain columns for category, type, budget, and actual. When importing a CSV, the app lets you match its columns to those fields. You can also add and edit budget lines in the app itself.

The app saves its working budget on your computer. Use the export option to create an encrypted backup. Encrypted files are tied to the operating-system account and credential store used to create them.

## AI advisor and supplier searches

The advisor uses Ollama to run a model locally and provides budget figures as context for its responses. Supplier searches require an internet connection. Some product-search features may also require additional access or retailer-specific APIs.

Product listings and prices can change. Check the retailer’s page for current price, shipping, pack size, and product details before ordering.

## QuickBooks

QuickBooks Online imports require an Intuit developer app and its credentials. The app uses the local callback address `http://localhost:8765/callback` during authorization.

On Windows, the app can also try to read an open QuickBooks Desktop session. It can look for certain QuickBooks IIF and CSV exports as well. If none of these sources are available, it may load its sample budget data instead.

## Privacy and limitations

Budget files, chat history, saved API keys, and QuickBooks connection details are stored locally. Where supported, the app encrypts saved data using a key held in the operating system’s credential store.

The advisor’s output is general guidance, not accounting, tax, or investment advice. Transaction checks flag items for review; they do not determine whether a charge is fraudulent.

## License

See [LICENSE](LICENSE).
