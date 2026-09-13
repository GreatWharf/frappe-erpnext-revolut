import frappe
from frappe.custom.doctype.custom_field.custom_field import create_custom_fields

FIELDS = [
    dict(
        fieldname="custom_revolut_source_key",
        fieldtype="Data",
        label="Revolut Source Key",
        read_only=1,
        no_copy=1,
        insert_after="transaction_id",
        search_index=1,
    ),
    dict(
        fieldname="custom_revolut_entry_key",
        fieldtype="Data",
        label="Revolut Entry Key",
        read_only=1,
        no_copy=1,
        unique=1,
        hidden=1,
        insert_after="custom_revolut_source_key",
    ),
    dict(
        fieldname="custom_revolut_review_required",
        fieldtype="Check",
        label="Revolut Review Required",
        read_only=1,
        no_copy=1,
        allow_on_submit=1,
        insert_after="custom_revolut_entry_key",
    ),
    dict(
        fieldname="custom_revolut_fee",
        fieldtype="Data",
        label="Revolut Reported Fee",
        read_only=1,
        no_copy=1,
        insert_after="custom_revolut_review_required",
    ),
]

for key, label in [
    ("bill_amount", "Revolut Original Bill Amount"),
    ("bill_currency", "Revolut Original Bill Currency"),
    ("effective_bill_rate", "Effective Bill Rate (Bill Currency per Account Currency)"),
]:
    FIELDS.append(
        dict(
            fieldname="custom_revolut_" + key,
            fieldtype="Data",
            label=label,
            read_only=1,
            no_copy=1,
            allow_on_submit=1,
            insert_after="custom_revolut_fee",
        )
    )


def check_versions():
    import erpnext

    if frappe.__version__.split(".")[0] != "16" or erpnext.__version__.split(".")[0] != "16":
        frappe.throw(
            "Revolut Bank Feed requires Frappe and ERPNext v16. Other major versions need validation."
        )
    if frappe.db.db_type != "mariadb":
        frappe.throw("This release supports MariaDB-backed sites.")


def after_migrate():
    check_versions()
    create_custom_fields({"Bank Transaction": FIELDS}, update=True)
    frappe.db.sql(
        "UPDATE `tabRevolut Connection` SET poll_overlap_minutes=60 WHERE poll_overlap_minutes IS NULL OR poll_overlap_minutes=0"
    )
    frappe.db.add_index(
        "Revolut Expense", ["connection", "upstream_state", "last_seen_at"], "revolut_expense_recheck"
    )
    frappe.db.add_index(
        "Revolut Source Transaction",
        ["connection", "upstream_state", "last_checked"],
        "revolut_pending_check",
    )
    frappe.db.add_index(
        "Revolut Webhook Event", ["connection", "status", "next_attempt_at"], "revolut_inbox_due"
    )

    from revolut_bank_feed.navigation import ensure_navigation

    ensure_navigation()


def before_uninstall():
    if frappe.db.count("Revolut Connection", {"enabled": 1}):
        frappe.throw("Disable all Revolut Connections and drain their background jobs before uninstalling.")
    if frappe.db.count("Revolut Source Transaction", {"needs_review": 1}):
        frappe.throw(
            "Resolve outstanding Revolut source reviews before uninstalling; export the audit records first."
        )
    # Custom fields intentionally survive to retain provenance/deduplication evidence.
    # Frappe removes app DocTypes during uninstall. Standard Bank Transactions remain.
