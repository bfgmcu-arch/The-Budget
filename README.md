# Abel

**Property of Student Led Business Solutions**

Abel is an intelligent financial and budget management workspace designed for businesses to plan, monitor, and optimize cash flow. It includes revenue and expense analytics, scenario planning, local AI guidance, duplicate transaction auditing, supplier price comparisons, and QuickBooks integrations.

---

## Key Features

- **Budget Management:** Import budgets from CSV or enter line items interactively with automatic KPI and variance tracking.
- **Scenario Planner:** Simulate revenue shifts, operational cost increases, or one-time expenses with real-time net profit projections.
- **Local AI Financial Advisor:** Ask questions about your financial numbers powered by a local, private on-device model (`qwen2.5:0.5b` via Ollama).
- **Transaction Auditing:** Detect possible duplicate charges, recurring subscription bills, and vendor price spikes from bank CSV exports.
- **Vendor & Supply Price Search:** Search public retail and supply catalogs for lower-cost alternatives.
- **QuickBooks Integration:** Connect QuickBooks Online or QuickBooks Desktop to import real-time charts of accounts and P&L statements.
- **Encrypted Local Storage:** All budgets, keys, and chat history are encrypted using your operating system's native secure credential store.

---

## Installation & Getting Started

> **Notice:** Repository cloning and source-code redistribution are strictly prohibited under the [EULA](EULA.md) and [LICENSE](LICENSE). End users are licensed exclusively to download and run the official installers.

### Windows (Official Installer)
1. Download **[AbelSetup.exe](https://github.com/bfgmcu-arch/The-Budget/releases)** from GitHub Releases.
2. Run `AbelSetup.exe`. The installer automatically configures the environment, pulls the local AI model, and creates Desktop/Start Menu shortcuts.
3. Launch Abel from your Desktop or Start Menu.

### Apple / macOS (Official Installer)
1. Download **[Abel-macOS-Installer.zip](https://github.com/bfgmcu-arch/The-Budget/releases)** from GitHub Releases.
2. Unzip the archive.
3. Double-click **`Install_Abel.command`** (or drag `Abel.app` into your `/Applications` folder).
4. Launch Abel from Launchpad, Applications, or Spotlight.

---

## System Requirements

- **Windows:** Windows 10 or Windows 11 (64-bit).
- **macOS (Apple):** macOS 11 (Big Sur) or newer. Fully supported on Apple Silicon (M1, M2, M3, M4) and Intel Macs.
- **Local AI:** Ollama running locally with `qwen2.5:0.5b` (automatically configured by the installers).
- **Security:** Supported credential store (Windows Credential Manager on Windows, Apple Keychain on macOS).

---

## License & Terms of Use

This software is proprietary. Repository cloning and source redistribution are strictly prohibited. End users are licensed solely to download and run the official installers. See [LICENSE](LICENSE) and [EULA.md](EULA.md).  
Copyright © 2026 Student Led Business Solutions. All Rights Reserved.
