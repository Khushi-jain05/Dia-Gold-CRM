"""Product photos from the client's image folder (17 Nov T-07).

The legacy app keeps each SKU's photo as ``<SKU>.jpg`` in one folder -
``\\\\Server2\\d\\JewelleryER_25\\Images`` (the 2025 install; the 2026 data has
none) - and the import brought only the file name (``BANG-366.jpg``). A photo
is found here by:

1. the path stored on the SKU, when that file exists;
2. else the stored file name, or ``<SKU>.jpg`` / ``.jpeg`` / ``.png``, in the
   image folders of Tools > Option (several, ``;``-separated), any case.

The folders are listed once, on a background thread, so a slow or missing
network share never holds up a screen; until the list is ready a photo is
simply not shown.
"""
from __future__ import annotations

import os
import shutil
import threading
import time
from pathlib import Path

ROOTS_SETTING = "img.roots"
DEFAULT_ROOTS = r"\\Server2\d\JewelleryER_25\Images"
EXTS = (".jpg", ".jpeg", ".png", ".bmp")
_REFRESH = 600                       # seconds before the folders are listed again

_index: dict[str, str] = {}          # lower-case file name -> full path
_built_at = 0.0
_building = False
_lock = threading.Lock()


def roots() -> list[str]:
    from diagold.services import settings
    text = settings.opt(ROOTS_SETTING) or ""
    return [r.strip() for r in text.split(";") if r.strip()]


def _build(folders: list[str]) -> None:
    global _index, _built_at, _building
    found: dict[str, str] = {}
    for folder in folders:
        try:
            with os.scandir(folder) as it:
                for e in it:
                    if e.is_file() and e.name.lower().endswith(EXTS):
                        found.setdefault(e.name.lower(), e.path)
        except OSError:
            continue                 # not reachable from this PC: no photos from it
    with _lock:
        _index, _built_at, _building = found, time.monotonic(), False


def refresh(wait: bool = False) -> None:
    """List the image folders again (in the background unless ``wait``)."""
    global _building
    with _lock:
        if _building:
            return
        _building = True
    folders = roots()
    if wait:
        _build(folders)
    else:
        threading.Thread(target=_build, args=(folders,), daemon=True).start()


def _lookup(name: str) -> str:
    if not _built_at or time.monotonic() - _built_at > _REFRESH:
        refresh()
    with _lock:
        return _index.get(name.lower(), "")


def find(stored: str, sku_code: str = "") -> str:
    """The photo file for a SKU: its stored path if that exists, else found
    in the image folders by the stored name or the SKU code. "" if none."""
    stored = (stored or "").strip()
    if stored and os.path.isabs(stored) and os.path.isfile(stored):
        return stored
    names = [Path(stored.replace("\\", "/")).name] if stored else []
    code = (sku_code or "").strip()
    if code:
        names += [code + ext for ext in EXTS]
    for name in names:
        hit = _lookup(name)
        if hit:
            return hit
    return ""


def photo(sku) -> str:
    """The photo of a ProductSku (finished, else design), or ""."""
    if sku is None:
        return ""
    return find(sku.image_finished or sku.image_design or "", sku.sku_code or "")


def store(src: str, sku_code: str) -> str:
    """Copy a picked photo into the first reachable image folder as ``<SKU><ext>``
    (legacy naming) and return its path; the picked path when no folder is
    set or it cannot be written."""
    folders = [f for f in roots() if os.path.isdir(f)]
    if not src or not sku_code or not folders or not os.path.isfile(src):
        return src
    ext = Path(src).suffix.lower() or ".jpg"
    dest = os.path.join(folders[0], f"{sku_code}{ext}")
    try:
        if os.path.abspath(src) != os.path.abspath(dest):
            shutil.copyfile(src, dest)
    except OSError:
        return src
    with _lock:
        _index[os.path.basename(dest).lower()] = dest
    return dest


def count_in(folder: str) -> int | None:
    """Photos in one folder; None when this PC cannot read it."""
    try:
        with os.scandir(folder) as it:
            return sum(1 for e in it if e.is_file() and e.name.lower().endswith(EXTS))
    except OSError:
        return None


def check() -> list[tuple[str, int | None]]:
    """Tools > Option 'Check': each folder and how many photos it holds
    (None = not reachable)."""
    return [(folder, count_in(folder)) for folder in roots()]
