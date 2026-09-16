"""Explicit, validated ERPNext prerequisites for isolated bank-feed test sites."""


def setup_test_company(company_name, company_abbr):
    """Commit only the reusable Company/COA baseline; test methods roll back their rows.

    Do not invoke ERPNext's test-record dependency generator: Company traverses
    unrelated stock/selling fixtures. The normal setup stages install presets
    (including Warehouse Type Transit) before creating the real Company and COA.
    """
    from datetime import date

    import frappe

    if not frappe.flags.in_test or not company_name.startswith("_Test "):
        raise RuntimeError("Company fixtures may only be initialized in an isolated test context.")

    created = not frappe.db.exists("Company", company_name)
    if created:
        from erpnext.setup.setup_wizard.setup_wizard import setup_complete

        year = date.today().year
        setup_complete(
            frappe._dict(
                {
                    "company_name": company_name,
                    "company_abbr": company_abbr,
                    "currency": "USD",
                    "country": "United States",
                    "chart_of_accounts": "Standard",
                    "fy_start_date": f"{year}-01-01",
                    "fy_end_date": f"{year}-12-31",
                }
            )
        )

    # The upstream preset loader logs some insert failures instead of raising.
    # Fail the suite explicitly rather than continuing with missing prerequisites.
    if not frappe.db.exists("Company", company_name) or not frappe.db.exists(
        "Account", {"company": company_name, "is_group": 1, "root_type": "Asset"}
    ):
        raise RuntimeError("ERPNext test Company/chart of accounts initialization failed.")
    if created:
        frappe.db.commit()
