from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

import frappe
from frappe.model.document import Document

from revolut_bank_feed.auth import lock_configuration
from revolut_bank_feed.core import FeedError, identity, validate_mapping


class RevolutAccountMap(Document):
    def validate(self):
        frappe.only_for("System Manager")
        lock_configuration(self.connection)
        connection = frappe.get_doc("Revolut Connection", self.connection)
        connection.check_permission("write")
        if connection.enabled:
            frappe.throw("Disable and save the connection before editing its account mappings.")
        self.company, self.environment = connection.company, connection.environment
        try:
            ZoneInfo(self.timezone)
        except (ZoneInfoNotFoundError, ValueError):
            frappe.throw("Use an IANA timezone such as Europe/London or UTC.")
        self.source_account_key = identity(self.environment, self.account_id, self.currency)
        bank = frappe.get_doc("Bank Account", self.bank_account)
        bank.check_permission("read")
        ledger = frappe.get_doc("Account", bank.account) if bank.account else frappe._dict()
        try:
            validate_mapping(
                connection.company,
                self.as_dict(),
                bank.as_dict(),
                ledger.as_dict() if hasattr(ledger, "as_dict") else ledger,
            )
        except FeedError as exc:
            frappe.throw(str(exc))
        old = self.get_doc_before_save()
        if old:
            for key in ("connection", "account_id", "currency", "bank_account", "timezone"):
                if old.get(key) != self.get(key):
                    frappe.throw(
                        f"{key} is immutable. Disable this map and review the migration with an administrator."
                    )

    def on_trash(self):
        lock_configuration(self.connection)
        connection = frappe.get_doc("Revolut Connection", self.connection)
        connection.check_permission("write")
        if connection.enabled or frappe.db.exists("Revolut Source Leg", {"account_map": self.name}):
            frappe.throw("Disable the connection; only unused mappings can be deleted.")
