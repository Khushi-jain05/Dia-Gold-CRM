"""Sale (2 Oct Session 3 §4.9-4.11, T-03 / T-04 / T-09 / T-10).

Sale ▸ Ready Stock ▸ (Sale, Sale Return, Approval, Approval Return, Ready
Repair Issue, Settings), Sale ▸ Metal, Sale ▸ Stone ▸ …, Sale ▸ Reports -
the legacy Sale menu. Approval lives here, not under Purchase: "purchase me
approval lete nahi" (Session 3 D3).
"""
from __future__ import annotations

from PySide6.QtWidgets import QLabel, QVBoxLayout, QWidget

SUBMENUS: dict[str, list[tuple[str, str]]] = {
    "sale.ready_stock": [
        ("sale", "Sale"), ("sale_return", "Sale Return"), ("approval", "Approval"),
        ("approval_return", "Approval Return"), ("repair_issue", "Ready Repair Issue"),
        ("settings", "Settings"),
    ],
    "sale.stone": [
        ("stone_sale", "Sale"), ("stone_approval", "Approval"),
        ("stone_approval_return", "Approval Return"),
    ],
}
_HEAD = {"sale.ready_stock": "Ready Stock", "sale.stone": "Stone"}

# Screens that are only a note until the client explains them.
PENDING_EXPLANATION = {"settings"}

def _ready(vr_type: str):
    def build(user):
        from diagold.ui.ready_vouchers import ReadyVoucherWidget
        return ReadyVoucherWidget(vr_type, user)
    return build


# key -> builder(user) for the screens that exist.
BUILDERS: dict[str, object] = {
    "sale": _ready("rs_sale"), "sale_return": _ready("rs_sale_return"),
    "approval": _ready("rs_approval"), "approval_return": _ready("rs_approval_return"),
    "repair_issue": _ready("rs_repair_issue"),
    "stone_sale": lambda user: _inv("stone_sale", user),
    "stone_approval": lambda user: _inv("stone_approval", user),
    "stone_approval_return": lambda user: _inv("stone_approval_return", user),
}


def _inv(vr_type: str, user):
    """Metal / stone sale and stone approval are inventory vouchers - stock
    leaves (or comes back to) a location - on the customer's account."""
    from diagold.ui.crud import CrudWidget
    from diagold.ui.inventory import voucher_spec
    return CrudWidget(voucher_spec(vr_type), rights=getattr(user, "rights", None))


def sub_key(parent: str, key: str) -> str:
    return f"{parent}.{key}"


def sub_labels() -> dict[str, str]:
    return {sub_key(p, k): f"{_HEAD[p]} {label}" for p, items in SUBMENUS.items()
            for k, label in items}


def has_screen(menu_key: str) -> bool:
    return menu_key.rsplit(".", 1)[1] in BUILDERS


class _Note(QWidget):
    def __init__(self, title: str, why: str, parent=None):
        super().__init__(parent)
        lay = QVBoxLayout(self)
        lay.setContentsMargins(24, 20, 24, 20)
        h = QLabel(title)
        h.setObjectName("H1")
        lay.addWidget(h)
        t = QLabel(why)
        t.setWordWrap(True)
        t.setObjectName("Muted")
        lay.addWidget(t)
        lay.addStretch(1)


def build_screen(menu_key: str, user=None) -> QWidget:
    parent, key = menu_key.rsplit(".", 1)
    label = f"{_HEAD[parent]} {dict(SUBMENUS[parent])[key]}"
    builder = BUILDERS.get(key)
    if builder is not None:
        return builder(user)
    if key == "settings":
        return _Note(label, "Opened in the legacy Sale ▸ Ready Stock menu on 2 Oct but not "
                            "explained. What it sets is asked in the open-items list; it is "
                            "not built on a guess.")
    return _Note(label, "Being built.")
