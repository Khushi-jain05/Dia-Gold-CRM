"""Attach Doc: documents kept with a voucher (28 Sept §4.4 receipt, §4.12
purchase). Each file is copied into the data folder under the voucher, so a
moved or deleted original does not lose it."""
from __future__ import annotations

import shutil
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.orm import Session

from diagold.config import DATA_DIR
from diagold.db.models import VoucherAttachment

ATTACH_DIR = DATA_DIR / "attachments"


def list_for(session: Session, ref_kind: str, ref_no: int) -> list[VoucherAttachment]:
    return list(session.scalars(select(VoucherAttachment).where(
        VoucherAttachment.ref_kind == ref_kind, VoucherAttachment.ref_no == ref_no)
        .order_by(VoucherAttachment.id)))


def add(session: Session, ref_kind: str, ref_no: int, source: str | Path, *,
        user_id: int | None = None) -> VoucherAttachment:
    src = Path(source)
    if not src.is_file():
        raise FileNotFoundError(f"{src} is not a file.")
    folder = ATTACH_DIR / ref_kind / str(ref_no)
    folder.mkdir(parents=True, exist_ok=True)
    dest = folder / src.name
    n = 1
    while dest.exists():
        dest = folder / f"{src.stem} ({n}){src.suffix}"
        n += 1
    shutil.copy2(src, dest)
    a = VoucherAttachment(ref_kind=ref_kind, ref_no=ref_no, file_name=src.name,
                          stored_path=str(dest), user_id=user_id)
    session.add(a)
    session.flush()
    return a


def remove(session: Session, attachment: VoucherAttachment) -> None:
    path = Path(attachment.stored_path)
    session.delete(attachment)
    session.flush()
    if path.is_file() and ATTACH_DIR in path.parents:
        path.unlink()
