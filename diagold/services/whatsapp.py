"""WhatsApp dispatch notification (9 Oct Session 5 A4, T-08 / TR6).

"Customer ke paas maal dispatch ho jaata hai, to notification chali jaaye ki
aapka maal hamare end se nikal chuka hai, expected is time tak pahunch jaayega."

When a sale is dispatched (Ship Date and Ship By filled - T-07) a message goes
to the customer's WhatsApp number, if the customer has opted in on the
Account master. The provider sits behind one function so the business number
/ BSP can be chosen later (Q12):

* ``sandbox`` (default) - nothing leaves the PC; the message is logged with
  status "sandbox" so the office can see exactly what would be sent.
* ``meta``    - WhatsApp Cloud API (graph.facebook.com), phone number id and
  access token in Tools ▸ Option ▸ Others. Business-initiated messages need an
  approved template: its name and language are settings; the template's body
  variables are filled in the order of TEMPLATE_VARS.

Sending never blocks saving the voucher: a failure is logged ("failed", with
the reason) and can be retried or resent. Delivered / read receipts arrive by
webhook, which needs a server - until then a message shows as "sent".
TEXT, TRIGGER AND NUMBER ARE UNCONFIRMED (9 Oct C-05 / Q12).
"""
from __future__ import annotations

import json
import re
import urllib.error
import urllib.request
from datetime import date, datetime
from typing import Any

from sqlalchemy import select
from sqlalchemy.orm import Session

from diagold.db.models import Account, ReadyVoucher, WhatsAppMessage
from diagold.services import settings

ENABLED = "whatsapp.enabled"
PROVIDER = "whatsapp.provider"
PHONE_ID = "whatsapp.phone_number_id"
TOKEN = "whatsapp.token"
TEMPLATE = "whatsapp.template_name"
LANGUAGE = "whatsapp.language"
TEXT = "whatsapp.dispatch_text"
TEST_NO = "whatsapp.test_number"
DEFAULT_TEXT = ("Dear {party}, your goods (Invoice {vrno}, {pcs} pcs) have been dispatched "
                "from Dia Gold on {ship_date} via {ship_by}{tracking}. Expected delivery: "
                "{expected_date}.")
TEMPLATE_VARS = ("party", "vrno", "pcs", "ship_date", "ship_by", "tracking_no",
                 "expected_date")
GRAPH = "https://graph.facebook.com/v20.0/{phone_id}/messages"


def _opt(session: Session, key: str) -> str:
    return settings.opt(key, session)


def normalise(number: str) -> str:
    """Digits only with the country code - a 10-digit Indian mobile gets 91."""
    digits = re.sub(r"\D", "", number or "")
    if len(digits) == 10:
        digits = "91" + digits
    return digits


def _d(v: date | None) -> str:
    return v.strftime("%d-%m-%Y") if v else "-"


def dispatch_values(session: Session, v: ReadyVoucher) -> dict[str, str]:
    acct = session.get(Account, v.account_id) if v.account_id else None
    pcs = sum(int(l.pcs or 0) for l in v.lines)
    return {"party": acct.name if acct else "", "vrno": str(v.vr_no), "pcs": str(pcs),
            "ship_date": _d(v.ship_date), "ship_by": v.ship_by or "-",
            "tracking_no": v.ship_no or "-",
            "tracking": f", tracking {v.ship_no}" if v.ship_no else "",
            "expected_date": _d(v.expected_date)}


def dispatch_text(session: Session, v: ReadyVoucher) -> str:
    text = _opt(session, TEXT) or DEFAULT_TEXT
    vals = dispatch_values(session, v)
    try:
        return text.format(**vals)
    except (KeyError, IndexError, ValueError):
        return DEFAULT_TEXT.format(**vals)


# --------------------------------------------------------------------------
# Providers
# --------------------------------------------------------------------------
class SendError(Exception):
    pass


def _send_meta(session: Session, to: str, body: str, values: dict[str, str]) -> str:
    phone_id, token = _opt(session, PHONE_ID).strip(), _opt(session, TOKEN).strip()
    if not phone_id or not token:
        raise SendError("WhatsApp phone number id / access token not set (Tools ▸ Option).")
    template = _opt(session, TEMPLATE).strip()
    if template:
        payload: dict[str, Any] = {
            "messaging_product": "whatsapp", "to": to, "type": "template",
            "template": {"name": template,
                         "language": {"code": _opt(session, LANGUAGE) or "en"},
                         "components": [{"type": "body", "parameters": [
                             {"type": "text", "text": values[k]} for k in TEMPLATE_VARS]}]}}
    else:
        # Free text is accepted only inside a 24-hour customer-service window.
        payload = {"messaging_product": "whatsapp", "to": to, "type": "text",
                   "text": {"body": body}}
    req = urllib.request.Request(GRAPH.format(phone_id=phone_id),
                                 data=json.dumps(payload).encode(), method="POST",
                                 headers={"Authorization": f"Bearer {token}",
                                          "Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            data = json.loads(resp.read().decode() or "{}")
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode(errors="replace")[:200]
        raise SendError(f"HTTP {exc.code}: {detail}") from exc
    except (urllib.error.URLError, TimeoutError, OSError) as exc:
        raise SendError(f"No connection: {exc}") from exc
    msgs = data.get("messages") or []
    return (msgs[0].get("id") if msgs else "") or ""


def _deliver(session: Session, msg: WhatsAppMessage, values: dict[str, str]) -> None:
    msg.attempts = int(msg.attempts or 0) + 1
    provider = msg.provider
    try:
        if provider == "meta":
            msg.provider_id = _send_meta(session, msg.to_number, msg.body, values)
            msg.status, msg.error = "sent", ""
        else:
            msg.status, msg.error = "sandbox", ""
        msg.sent_at = datetime.now()
    except SendError as exc:
        msg.status, msg.error = "failed", str(exc)[:300]
    session.flush()


# --------------------------------------------------------------------------
# Public
# --------------------------------------------------------------------------
def notify_dispatch(session: Session, v: ReadyVoucher, *, user_id: int | None = None,
                    force: bool = False) -> WhatsAppMessage | None:
    """Send (or log) the dispatch message for a sale. Never raises. Returns
    the log row, or None when WhatsApp is switched off."""
    if _opt(session, ENABLED) != "1" and not force:
        return None
    acct = session.get(Account, v.account_id) if v.account_id else None
    test_no = normalise(_opt(session, TEST_NO))
    to = test_no or normalise(acct.whatsapp_no or acct.phone if acct else "")
    msg = WhatsAppMessage(account_id=v.account_id, ref_kind=v.vr_type, ref_no=v.vr_no,
                          to_number=to, body=dispatch_text(session, v),
                          provider=_opt(session, PROVIDER) or "sandbox", user_id=user_id)
    session.add(msg)
    session.flush()
    if not to:
        msg.status, msg.error = "skipped", "No WhatsApp number on the account."
    elif acct is not None and not acct.whatsapp_opt_in and not test_no:
        msg.status, msg.error = "skipped", "The customer has not opted in (Account master)."
    else:
        _deliver(session, msg, dispatch_values(session, v))
    session.flush()
    return msg


def retry(session: Session, msg: WhatsAppMessage) -> WhatsAppMessage:
    """Try a failed message again with the same text."""
    v = session.scalar(select(ReadyVoucher).where(ReadyVoucher.vr_type == msg.ref_kind,
                                                  ReadyVoucher.vr_no == msg.ref_no))
    _deliver(session, msg, dispatch_values(session, v) if v else {k: "" for k in TEMPLATE_VARS})
    return msg


def retry_failed(session: Session) -> int:
    n = 0
    for msg in session.scalars(select(WhatsAppMessage).where(WhatsAppMessage.status == "failed")):
        retry(session, msg)
        n += 1
    return n


def message_log(session: Session, date_from: date, date_to: date) -> list[dict[str, Any]]:
    rows = []
    q = (select(WhatsAppMessage).where(
        WhatsAppMessage.created_at >= datetime.combine(date_from, datetime.min.time()),
        WhatsAppMessage.created_at <= datetime.combine(date_to, datetime.max.time()))
         .order_by(WhatsAppMessage.created_at.desc()))
    for m in session.scalars(q):
        acct = session.get(Account, m.account_id) if m.account_id else None
        rows.append({"time": m.created_at.strftime("%d-%m-%Y %H:%M"), "party":
                     acct.name if acct else "", "voucher": f"Sale {m.ref_no}" if m.ref_no else "",
                     "number": m.to_number, "status": m.status, "attempts": m.attempts,
                     "provider": m.provider, "error": m.error, "body": m.body, "_id": m.id,
                     "_negative": m.status == "failed"})
    return rows
