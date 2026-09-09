# Sharing Dia Gold CRM with the client (no code, no Python)

The client gets a single app to double-click. Two ways to produce the builds.

---

## Option A — GitHub Actions builds both platforms for you (recommended)

You don't need a Windows machine. Push this project to a GitHub repo and the
included workflow (`.github/workflows/build.yml`) builds all three targets:

| File | For |
|---|---|
| `DiaGoldCRM-Windows-x64.zip` | Windows 10/11 |
| `DiaGoldCRM-macOS-arm64.zip` | Apple Silicon Macs (M1–M4) |
| `DiaGoldCRM-macOS-x64.zip` | Intel Macs |

Steps:

```bash
cd diagold-crm
git init && git add -A && git commit -m "Dia Gold CRM v0.1"
git branch -M main
git remote add origin https://github.com/<you>/diagold-crm.git
git push -u origin main

# tag a version to trigger a build + GitHub Release with the zips attached
git tag v0.1.0
git push origin v0.1.0
```

Open the repo's **Actions** tab (or **Releases**) and download the zips.
`workflow_dispatch` also lets you run it manually without a tag.

---

## Option B — build locally

- **macOS:** `bash packaging/build.sh` → `dist/DiaGoldCRM-macOS-<arch>.zip`
  (builds only for the Mac you're on — Apple Silicon *or* Intel, not both)
- **Windows:** `packaging\build.bat` → `dist\DiaGoldCRM-Windows-x64.zip`
  (must be run on a Windows PC)

The macOS Apple-Silicon build is already done: **`dist/DiaGoldCRM-macOS-arm64.zip`**.

---

## What to tell the client

### Windows

1. Unzip anywhere (e.g. Desktop).
2. Open the `DiaGoldCRM` folder, double-click **`DiaGoldCRM.exe`**.
3. First time, Windows SmartScreen may say *"Windows protected your PC"* —
   click **More info → Run anyway**. (This is because the app isn't code-signed;
   it's expected for an in-house build.)
4. Log in with **`admin` / `admin`**, then change the password from
   **Tools ▸ Change Password**.

### macOS

1. Unzip → you get **`DiaGoldCRM.app`**. Move it to Applications (optional).
2. **Right-click the app → Open → Open** (don't just double-click the first time).
   macOS Gatekeeper blocks unsigned apps on a normal double-click; the
   right-click-Open path lets you approve it once.
   - If it still refuses on newer macOS: **System Settings ▸ Privacy & Security**,
     scroll down, click **Open Anyway** next to the DiaGoldCRM message.
   - Or, once, in Terminal: `xattr -dr com.apple.quarantine /path/to/DiaGoldCRM.app`
3. Log in with **`admin` / `admin`**, then change the password.

### The database

Each install keeps its own SQLite file:

| OS | Location |
|---|---|
| Windows | `%APPDATA%\DiaGoldCRM\diagold.sqlite3` |
| macOS | `~/Library/Application Support/DiaGoldCRM/diagold.sqlite3` |

To pre-load data for the client, build first, run once to generate the DB,
add records, then ship that `.sqlite3` file alongside the app with a note to
drop it into the folder above. For a shared multi-user database, that's the
signal to move to PostgreSQL (see `README.md`).

---

## Removing the Gatekeeper / SmartScreen friction later

- **Windows:** an Authenticode code-signing certificate (~$100–400/yr) signs
  `DiaGoldCRM.exe` so SmartScreen stops warning.
- **macOS:** an Apple Developer account ($99/yr) to sign **and notarize** the
  `.app` so it opens on a normal double-click.

Both can be wired into the GitHub Actions workflow when you're ready.
