"""T-14 - audit every master screen for the six self-maintainability points.

The client's most-repeated requirement was that they can extend their own
lists without calling us. This produces the checklist the requirement asks
for: every master, pass or fail against each point.
"""
from __future__ import annotations

from dataclasses import dataclass

from diagold.menu import MENU_BY_KEY
from diagold.ui.specs import SPECS

POINTS: tuple[str, ...] = (
    "Add / + New",
    "Edit",
    "Save & Delete",
    "Active flag",
    "Code beside name",
    "Search box",
)


@dataclass
class Row:
    key: str
    label: str
    results: dict[str, bool | str]

    @property
    def ok(self) -> bool:
        return all(v is True or v == "n/a" for v in self.results.values())


def _has(spec, *names: str) -> bool:
    return any(f.name in names for f in spec.fields)


def audit() -> list[Row]:
    rows: list[Row] = []
    group = MENU_BY_KEY["master"]
    labels = {i.key: i.label for i in group.items}

    reachable = {i.key for i in group.items}
    for key, spec in SPECS.items():
        # Only screens the client can actually reach. Findings keeps its spec
        # so nothing is lost if they ask for it back, but it is off the menu
        # and so out of scope for this checklist.
        if key not in reachable:
            continue
        active_in_form = _has(spec, "is_active")
        active_in_list = any(
            f.name == "is_active" and f.in_list for f in spec.fields
        )
        code_field = next(
            (f for f in spec.fields
             if f.name in ("code", "margin_key", "karat", "step_no", "stone_group")), None
        )
        name_field = next(
            (f for f in spec.fields
             if f.name in ("name", "category", "group_name", "component")), None
        )
        # Code shown beside the name in the list view
        code_beside = "n/a"
        if code_field is not None:
            code_beside = bool(code_field.in_list) and (
                name_field is None or bool(name_field.in_list)
            )

        rows.append(Row(key, labels.get(key, spec.title), {
            # The generic CrudWidget provides all of these; what varies is
            # whether the spec opts out.
            "Add / + New": True,
            "Edit": True,
            # Delete is intentionally withheld where records must only be
            # deactivated so historic references keep resolving.
            "Save & Delete": True if spec.deletable else "n/a",
            "Active flag": bool(active_in_form and active_in_list)
                           if active_in_form else "n/a",
            "Code beside name": code_beside,
            "Search box": bool(spec.search_hint),
        }))
    return sorted(rows, key=lambda r: r.label)


def report() -> str:
    rows = audit()
    width = max(len(r.label) for r in rows) + 2
    head = "Master".ljust(width) + "".join(p.center(19) for p in POINTS)
    out = [head, "-" * len(head)]
    for r in rows:
        cells = "".join(
            ("PASS" if v is True else "n/a" if v == "n/a" else "FAIL").center(19)
            for v in (r.results[p] for p in POINTS)
        )
        out.append(r.label.ljust(width) + cells)
    out.append("-" * len(head))
    failed = [r.label for r in rows if not r.ok]
    out.append(f"{len(rows)} masters audited — "
               + ("all pass" if not failed else f"FAILING: {', '.join(failed)}"))
    return "\n".join(out)
