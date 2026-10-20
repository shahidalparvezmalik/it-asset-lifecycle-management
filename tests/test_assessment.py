import unittest
from datetime import date

from itam.assessment import assess_assets, executive_summary


def sample(**overrides):
    row = {
        "asset_id": "AST-1", "asset_type": "Laptop", "manufacturer": "Example",
        "model": "Model X", "serial_number": "SYN-1", "assigned_to": "user-1",
        "owner": "IT", "business_unit": "Finance", "location": "HQ",
        "purchase_date": "2022-01-01", "warranty_end": "2027-12-31",
        "planned_refresh_date": "2027-01-01", "lifecycle_status": "IN_SERVICE",
        "criticality": "MEDIUM", "condition": "GOOD",
        "vendor_support_status": "SUPPORTED", "replacement_cost_estimate": "1000",
    }
    row.update(overrides)
    return row


class AssessmentTests(unittest.TestCase):
    def test_healthy_asset_is_low_risk(self):
        result, issues = assess_assets([sample()], date(2026, 10, 20))
        self.assertEqual(result[0]["risk_band"], "LOW")
        self.assertEqual(result[0]["risk_score"], 0)
        self.assertEqual(issues, [])

    def test_critical_unsupported_poor_overdue_asset_is_high(self):
        row = sample(
            criticality="HIGH", vendor_support_status="ENDED", condition="POOR",
            warranty_end="2024-01-01", planned_refresh_date="2024-01-01",
        )
        result, _ = assess_assets([row], date(2026, 10, 20))
        self.assertEqual(result[0]["risk_band"], "HIGH")
        self.assertGreaterEqual(result[0]["risk_score"], 50)

    def test_duplicate_ids_are_flagged(self):
        _, issues = assess_assets([sample(), sample()])
        self.assertEqual(sum(i["issue_code"] == "DUPLICATE_ASSET_ID" for i in issues), 2)

    def test_missing_owner_is_flagged_and_scored(self):
        result, issues = assess_assets([sample(owner="")], date(2026, 10, 20))
        self.assertTrue(any(i["issue_code"] == "MISSING_OWNER" for i in issues))
        self.assertGreater(result[0]["risk_score"], 0)

    def test_summary_counts_assets_and_issues(self):
        rows, issues = assess_assets([sample(), sample(asset_id="AST-2", lifecycle_status="RETIRED")],
                                     date(2026, 10, 20))
        summary = executive_summary(rows, issues, date(2026, 10, 20))
        self.assertEqual(summary["assets_assessed"], 2)
        self.assertEqual(summary["active_assets"], 1)
        self.assertEqual(summary["retired_assets"], 1)


if __name__ == "__main__":
    unittest.main()
