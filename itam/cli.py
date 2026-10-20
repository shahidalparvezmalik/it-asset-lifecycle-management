"""Command-line interface for the ITAM proof of concept."""
from __future__ import annotations

import argparse
import json
from datetime import date
from pathlib import Path

from itam.assessment import assess_assets, executive_summary, load_assets, write_csv


def main() -> int:
    parser = argparse.ArgumentParser(description="Assess synthetic IT asset lifecycle records.")
    parser.add_argument("--input", default="data/assets.csv", help="Input asset CSV")
    parser.add_argument("--output-dir", default="reports", help="Directory for generated reports")
    parser.add_argument("--as-of", help="Assessment date YYYY-MM-DD (defaults to today)")
    args = parser.parse_args()

    try:
        as_of = date.fromisoformat(args.as_of) if args.as_of else date.today()
    except ValueError:
        parser.error("--as-of must be YYYY-MM-DD")

    assets = load_assets(args.input)
    assessments, issues = assess_assets(assets, as_of)
    out = Path(args.output_dir)
    out.mkdir(parents=True, exist_ok=True)
    write_csv(out / "asset_assessment.csv", assessments)
    write_csv(out / "data_quality_issues.csv", issues,
              ["asset_id", "source_row", "issue_code", "detail"])
    summary = executive_summary(assessments, issues, as_of)
    (out / "executive_summary.json").write_text(
        json.dumps(summary, indent=2) + "\n", encoding="utf-8"
    )
    print(f"Assessed {len(assets)} assets as of {as_of.isoformat()}.")
    print(f"Data-quality issues: {len(issues)}")
    print(f"Reports written to: {out.resolve()}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
