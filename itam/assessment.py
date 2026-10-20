"""Deterministic IT asset quality and lifecycle assessment rules."""
from __future__ import annotations

import csv
from datetime import date, datetime
from pathlib import Path
from typing import Iterable

DATE_FIELDS = ("purchase_date", "warranty_end", "planned_refresh_date")
REQUIRED_FIELDS = (
    "asset_id", "asset_type", "manufacturer", "model", "serial_number",
    "owner", "business_unit", "location", "lifecycle_status", "criticality",
    "condition", "vendor_support_status", "replacement_cost_estimate",
)
VALID_STATES = {"REQUESTED", "ORDERED", "RECEIVED", "IN_SERVICE", "REPAIR", "RETIRED"}
VALID_CRITICALITY = {"LOW", "MEDIUM", "HIGH"}
VALID_CONDITION = {"GOOD", "FAIR", "POOR"}
VALID_SUPPORT = {"SUPPORTED", "ENDED"}


def parse_date(value: str) -> date | None:
    """Parse an ISO date; blank values return None."""
    if not value or not value.strip():
        return None
    return datetime.strptime(value.strip(), "%Y-%m-%d").date()


def load_assets(path: str | Path) -> list[dict[str, str]]:
    with Path(path).open(newline="", encoding="utf-8-sig") as handle:
        return list(csv.DictReader(handle))


def assess_assets(assets: Iterable[dict[str, str]], as_of: date | None = None
                  ) -> tuple[list[dict[str, object]], list[dict[str, str]]]:
    """Return asset assessments and register-level data quality exceptions."""
    today = as_of or date.today()
    rows = list(assets)
    counts: dict[str, int] = {}
    for row in rows:
        key = row.get("asset_id", "").strip()
        if key:
            counts[key] = counts.get(key, 0) + 1

    assessments: list[dict[str, object]] = []
    issues: list[dict[str, str]] = []

    for index, row in enumerate(rows, start=2):
        asset_id = row.get("asset_id", "").strip() or f"ROW-{index}"
        local_issues: list[str] = []
        for field in REQUIRED_FIELDS:
            if not row.get(field, "").strip():
                local_issues.append(f"MISSING_{field.upper()}")
        if row.get("asset_id", "").strip() and counts.get(asset_id, 0) > 1:
            local_issues.append("DUPLICATE_ASSET_ID")

        state = row.get("lifecycle_status", "").strip().upper()
        criticality = row.get("criticality", "").strip().upper()
        condition = row.get("condition", "").strip().upper()
        support = row.get("vendor_support_status", "").strip().upper()

        if state and state not in VALID_STATES:
            local_issues.append("INVALID_LIFECYCLE_STATUS")
        if criticality and criticality not in VALID_CRITICALITY:
            local_issues.append("INVALID_CRITICALITY")
        if condition and condition not in VALID_CONDITION:
            local_issues.append("INVALID_CONDITION")
        if support and support not in VALID_SUPPORT:
            local_issues.append("INVALID_VENDOR_SUPPORT_STATUS")

        dates: dict[str, date | None] = {}
        for field in DATE_FIELDS:
            try:
                dates[field] = parse_date(row.get(field, ""))
            except ValueError:
                dates[field] = None
                local_issues.append(f"INVALID_{field.upper()}")

        for issue in sorted(set(local_issues)):
            issues.append({
                "asset_id": asset_id,
                "source_row": str(index),
                "issue_code": issue,
                "detail": issue.replace("_", " ").title(),
            })

        score = 0
        factors: list[str] = []
        warranty_end = dates["warranty_end"]
        refresh_date = dates["planned_refresh_date"]
        purchase_date = dates["purchase_date"]

        if support == "ENDED":
            points = 30 if criticality == "HIGH" else 20
            score += points
            factors.append(f"Vendor support ended (+{points})")
        if warranty_end:
            days = (warranty_end - today).days
            if days < 0:
                score += 20
                factors.append("Warranty expired (+20)")
            elif days <= 90:
                score += 10
                factors.append("Warranty expires within 90 days (+10)")
        if refresh_date and refresh_date < today and state not in {"RETIRED", "REQUESTED", "ORDERED"}:
            score += 20
            factors.append("Planned refresh date passed (+20)")
        if condition == "POOR":
            score += 15
            factors.append("Condition marked poor (+15)")
        if criticality == "HIGH":
            score += 10
            factors.append("High business criticality (+10)")
        if not row.get("owner", "").strip() and state not in {"RETIRED", "REQUESTED"}:
            score += 10
            factors.append("Missing accountable owner (+10)")
        if state == "RETIRED":
            if row.get("assigned_to", "").strip():
                score += 15
                factors.append("Retired asset still has assigned user (+15)")
        age_years = round((today - purchase_date).days / 365.25, 1) if purchase_date and purchase_date <= today else None

        band = "HIGH" if score >= 50 else "MEDIUM" if score >= 25 else "LOW"
        if band == "HIGH":
            recommendation = "Prioritize owner review; validate support, warranty, service impact and refresh/disposal options."
        elif band == "MEDIUM":
            recommendation = "Review in the next lifecycle planning cycle and confirm dates, ownership and support status."
        elif local_issues:
            recommendation = "Resolve asset-register data-quality exceptions before relying on this assessment."
        else:
            recommendation = "Continue routine lifecycle monitoring and periodic record reconciliation."

        cost_text = row.get("replacement_cost_estimate", "").strip()
        try:
            cost = float(cost_text) if cost_text else 0.0
            if cost < 0:
                raise ValueError
        except ValueError:
            cost = 0.0
            if "INVALID_REPLACEMENT_COST_ESTIMATE" not in local_issues:
                issues.append({
                    "asset_id": asset_id, "source_row": str(index),
                    "issue_code": "INVALID_REPLACEMENT_COST_ESTIMATE",
                    "detail": "Replacement cost estimate must be a non-negative number",
                })

        assessments.append({
            **row,
            "age_years": age_years if age_years is not None else "",
            "risk_score": score,
            "risk_band": band,
            "risk_factors": "; ".join(factors) if factors else "No scoring factors triggered",
            "data_quality_issue_count": len(set(local_issues)),
            "recommendation": recommendation,
            "replacement_cost_estimate": f"{cost:.2f}",
        })

    return assessments, issues


def executive_summary(assessments: list[dict[str, object]],
                      issues: list[dict[str, str]], as_of: date) -> dict[str, object]:
    active = [r for r in assessments if str(r.get("lifecycle_status", "")).upper() != "RETIRED"]
    high = [r for r in active if r["risk_band"] == "HIGH"]
    medium = [r for r in active if r["risk_band"] == "MEDIUM"]
    overdue = [
        r for r in active
        if str(r.get("planned_refresh_date", "")) and
        _date_before(str(r["planned_refresh_date"]), as_of)
    ]
    expiring = []
    for row in active:
        warranty = parse_date(str(row.get("warranty_end", "")))
        if warranty and 0 <= (warranty - as_of).days <= 90:
            expiring.append(row)
    costs = sum(float(r.get("replacement_cost_estimate", 0) or 0) for r in high + medium)
    return {
        "as_of": as_of.isoformat(),
        "assets_assessed": len(assessments),
        "active_assets": len(active),
        "retired_assets": len(assessments) - len(active),
        "high_priority_active_assets": len(high),
        "medium_priority_active_assets": len(medium),
        "assets_past_planned_refresh_date": len(overdue),
        "warranties_expiring_within_90_days": len(expiring),
        "register_data_quality_issues": len(issues),
        "estimated_replacement_cost_for_high_and_medium_priority_assets": round(costs, 2),
        "currency": "as supplied in synthetic sample data; not an approved budget",
        "scoring_note": "Rules-based review priority only; not a failure probability.",
    }


def _date_before(value: str, today: date) -> bool:
    try:
        parsed = parse_date(value)
        return parsed is not None and parsed < today
    except ValueError:
        return False


def write_csv(path: str | Path, rows: list[dict[str, object]], fieldnames: list[str] | None = None) -> None:
    destination = Path(path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    if fieldnames is None:
        fieldnames = list(rows[0].keys()) if rows else []
    with destination.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)
