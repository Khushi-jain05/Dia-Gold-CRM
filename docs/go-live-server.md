# Go-live on the office SQL Server

What has to happen on the client's side, and the steps we run, to move Dia
Gold CRM from the local test file to the shared database on SERVER2.

## 1. On SERVER2 (client IT, once)

1. In SQL Server Management Studio on `SERVER2\ERP`, create an empty database
   **`DiaGoldCRM`**. Leave `Diagold26` alone; the legacy system keeps running
   during the parallel run.
2. Create a SQL login **`diagold_app`** with a strong password. Make it
   `db_owner` of `DiaGoldCRM` (it creates the tables on the first start) and
   give it read access to `Diagold26` (only the import reads it).
3. Make sure the office PCs can reach the server: SQL Server Browser running
   (for the `\ERP` instance name) or a fixed TCP port, and the firewall open
   for it inside the office network only. Never open it to the internet; use a
   VPN for anyone outside.
4. Add `DiaGoldCRM` to the server's daily backup plan.

## 2. Each PC

1. Unzip `DiaGoldCRM-Windows-x64.zip` (v0.11.0 or later).
2. Copy `packaging/server.ini.example` next to `DiaGoldCRM.exe` as
   **`server.ini`** and fill in the login:

   ```ini
   [Database]
   Server=SERVER2\ERP
   Port=
   DatabaseName=DiaGoldCRM
   UID=diagold_app
   PWD=<the password>
   ```

3. Start the app. The status bar shows `DB: SERVER2\ERP/DiaGoldCRM`. If it
   cannot reach the server, it says so and changes nothing.

The first PC to start creates every table and loads the masters from the
client's sheets. The worked examples (sample SKU ER-1337, the sample jobs) are
NOT loaded on the server.

## 3. Import from the legacy database (we run this)

Masters and SKUs, any time before cut-over (safe to repeat):

```bash
python scripts/import_legacy.py --server "SERVER2\ERP" --database Diagold26 \
    --user diagold_app --password ... --dry-run     # look at the report first
python scripts/import_legacy.py --server "SERVER2\ERP" --database Diagold26 \
    --user diagold_app --password ...
```

On cut-over day, on the backup taken that day, add the opening stock:

```bash
python scripts/import_legacy.py ... --openings 01-12-2026
```

Each run saves its report as `legacy_import_<date>.txt` in the data folder.
It lists what was added, what was already there, every value where ours and
the legacy differ, and every row not loaded and why.

| Legacy | Here | Notes |
|---|---|---|
| CompanyMaster, CurrencyMaster, ColorMaster | Company, Currency, Colour | |
| MetalMaster + MetalRatio + BaseMetalMaster | Metal + ratios | legacy purity replaces ours (ours was read off the name) |
| LocationMaster | Location | |
| StoneGroup / Shape / Quality / Type / Size / StoneMaster | stone masters | |
| StoneSkuMaster + StoneSkuSizeDetail | Stone SKU with its sizes | BasePrice = cost, Price = sale |
| SettingTypeMaster, ProcessMaster, FamilyMaster, ItemMaster, MouldMaster | same | process short codes from the legacy (route string) |
| GroupMaster, 999999911 | Account groups, Accounts | negative IDs are legacy system ledgers, skipped |
| U00000001 | Users | old password, no rights |
| 999999991 + 999999992 | Product SKU + stones | 10,517 SKUs, 34,813 lines |
| 888888811/12/13 + ReadyIds | Opening Stock - Ready Items | `--openings`; legacy Stock ID kept as Stock No |
| StoneBalanceClosing | Opening stone stock | `--openings`; negative / Breakage / Loss listed, not loaded |
| MetalBalanceClosing | Metal Opening Stock | `--openings`; negative / Dust listed, not loaded |
| ClientBalance | - | party balances listed for checking only (Q69) |
| 999999996, ManualPrice | - | not loaded, asked (Q139) |

Not carried: the legacy screen layout tables (ColumnWidth, TagSetting,
SlideOption...), temporary tables (TEMP099, ReadyIds copies), user rights by
form number (U00000002).

## Testing on a Mac

```bash
brew install colima docker
colima start --arch aarch64 --vm-type=vz --vz-rosetta --memory 4
docker run -d --platform linux/amd64 --name diagold-mssql -e ACCEPT_EULA=Y \
  -e 'MSSQL_SA_PASSWORD=...' -p 1433:1433 -v ~/diagold-mssql/backup:/backup \
  mcr.microsoft.com/mssql/server:2022-latest
# RESTORE DATABASE Diagold26 FROM DISK='/backup/dg_new.bak'
#   WITH MOVE 'LH10_Data' TO '/var/opt/mssql/data/Diagold26.mdf',
#        MOVE 'LH10_Log'  TO '/var/opt/mssql/data/Diagold26.ldf'
```

Point `DIAGOLD_SERVER_INI` at an ini for that server and every test suite
runs against it unchanged (`SampleData=Yes` in the ini for the suites that
use the worked examples).
