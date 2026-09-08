# Dia Gold CRM

Cross-platform (macOS + Windows) desktop ERP/CRM for **Dia Gold**, a jewellery
manufacturer. Built with **PySide6** (Qt) and **SQLAlchemy** on **SQLite**
(swappable to PostgreSQL later).

The menu structure is taken directly from the client design workbook
`HEADING OR SUB HEADING.xlsx` — 14 main headings, each with its sub-tabs.

---

## What works in this build (v0.1)

| Area | Status |
|---|---|
| Login (ID / Password) | ✅ Working — first run: `admin` / `admin` |
| Master ▸ Company, Currency, Account, Metal, Location, Parts/Mould, SKU Info, Family/Category, Colour, Stone Info, Setting Type, Manufacturing, Other | ✅ Full add / edit / delete / search |
| Master ▸ Findings, Voucher Type | ⬜ Dropped — the client confirmed they are unused, so they are hidden from the menu |
| Master ▸ User Right | ✅ Users + Roles + permission matrix (view / edit per module) |
| SKU ▸ Stone SKU/Packet No, Product SKU Master | ✅ Full add / edit / delete / search |
| SKU ▸ SKU View | ⬜ Placeholder |
| Quotation, MRP, Production Planning, Manufacturing, Purchase, Inventory, Sale, Account, Tools, Reports | ⬜ Menu + placeholders (scaffolded, screens not built) |
| Tools ▸ Change Password | ✅ Working |
| Window ▸ Cascade / Tile / Close All | ✅ Working |

Every menu item from the workbook is present. Items without a screen yet open a
"coming soon" page and are marked in the menu.

---

## Setup

Requires **Python 3.10+**.

```bash
cd diagold-crm
python -m venv .venv
# macOS / Linux:
source .venv/bin/activate
# Windows (PowerShell):
# .venv\Scripts\Activate.ps1

pip install -r requirements.txt
python main.py
```

First launch creates the database and seeds:

- `admin` / `admin` superuser (change the password from **Tools ▸ Change Password**)
- Base currencies (INR, USD, AED, EUR)
- All 26 metal heads from the client's live master, each with its
  purity/fineness and Mining Metal Ratio rows (which must total 100.00)
- Starter stone types, manufacturing processes, and SKU categories
- The client's 17 material-custody locations, 14 setting types,
  2 jewellery families and 3 gold colours

### Where the data lives

A single SQLite file in the per-user app-data folder:

| OS | Path |
|---|---|
| macOS | `~/Library/Application Support/DiaGoldCRM/diagold.sqlite3` |
| Windows | `%APPDATA%\DiaGoldCRM\diagold.sqlite3` |

Override with the `DIAGOLD_DATA_DIR` environment variable (useful for testing or
keeping the DB on a shared drive). Set `DIAGOLD_SQL_ECHO=1` to log SQL.

---

## Project layout

```
diagold-crm/
├─ main.py                     entry point (login loop → main window)
├─ requirements.txt
└─ diagold/
   ├─ config.py                paths, DB URL, platform detection
   ├─ menu.py                  the 14 headings + sub-tabs (mirrors the Excel)
   ├─ db/
   │  ├─ session.py            engine / session / init_db()
   │  └─ models/               ORM models
   │     ├─ auth.py            User, Role, RolePermission (+ PBKDF2 hashing)
   │     ├─ master.py          Company, Currency, Account, Metal, …
   │     └─ sku.py             StonePacket, ProductSku, ProductSkuStone
   ├─ services/
   │  ├─ auth.py               authenticate(), permission checks
   │  └─ seed.py               first-run data
   └─ ui/
      ├─ login.py              login dialog
      ├─ main_window.py        QMainWindow + menu bar + MDI tabs
      ├─ crud.py               generic spec-driven CRUD screen + form dialog
      ├─ specs.py              field specs for every Master / SKU screen
      ├─ permissions.py        User Right screen (users + rights matrix)
      ├─ registry.py           menu key → screen
      └─ placeholder.py        "coming soon" screen
```

## Adding a new master screen

1. Add the model in `diagold/db/models/`.
2. Export it from `diagold/db/models/__init__.py`.
3. Add a `CrudSpec` in `diagold/ui/specs.py` keyed by its menu key.

That's it — the generic `CrudWidget` renders the list, search, and add/edit form,
and permissions are enforced automatically from the menu key.

## Roadmap (next modules)

1. **Quotation** → **Order** front-office flow (uses Account + Product SKU masters)
2. **MRP** & **Purchase Order**
3. **Production Planning** (Job Card) → **Manufacturing** (Issue / Receive / Costing)
4. **Inventory** (Metal / Stone / Parts ledgers)
5. **Sale** & **Account** (vouchers, ledger, trial balance)
6. **Reports** across all modules

## Moving to PostgreSQL later

Change `DATABASE_URL` in `diagold/config.py` (or via env var) to a
`postgresql+psycopg://…` URL and `pip install psycopg[binary]`. Models are
backend-agnostic; use Alembic for migrations once the schema stabilises.

## Packaging to a native app (optional)

```bash
pip install pyinstaller
pyinstaller --name "DiaGoldCRM" --windowed --onefile main.py
```

Produces `dist/DiaGoldCRM.app` (macOS) or `dist\DiaGoldCRM.exe` (Windows).
