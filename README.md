# Abel

Abel is a desktop budget and planning tool for small businesses. It helps you track revenue and expenses, compare budgeted and actual results, test planning scenarios, review transactions, and keep an eye on supplier costs.

## Overview

Abel gives you a simple operating view of your financial picture:

- budget tracking by category and type
- comparison of budget to actual performance
- scenario modeling for revenue, expense, and one-time cost changes
- local budget advisor using an Ollama model
- transaction review for duplicate charges and recurring price changes
- supplier and product search support
- QuickBooks import support
- encrypted local backups and protected data storage

## Product name

The application name is now Abel.

This keeps the product branding clear, consistent, and easier to recognize across the app, installer, and local data files.

## Requirements

- Python 3
- Ollama installed and running
- A supported OS credential store for encrypted local data

The default model used by the app is `qwen2.5:0.5b`.

## Installing and running

### From source

```bash
git clone https://github.com/bfgmcu-arch/The-Budget.git
cd The-Budget
python -m pip install -r requirements.txt
python app.py
```

### Windows launcher

A Windows launcher is included in the repository root:

```bat
start_abel.bat
```

This starts the Abel app from the local environment.

### Windows installer

The Windows installer project is under the `installer/` folder.

Main installer files:

- `installer/BusinessBudgetAI.iss`
- `installer/build_windows.ps1`
- `installer/setup_app.ps1`

The installer is designed to set up Python, install the dependencies, download Ollama, and fetch the default model needed for Abel.

## Budget format

The app expects a CSV with these fields:

- Category
- Type
- Budget
- Actual

## Local data and privacy

Abel stores budget data, conversations, and saved settings on the local machine. Where supported, it encrypts this data using the operating system credential store.

## License

See [LICENSE](LICENSE).
