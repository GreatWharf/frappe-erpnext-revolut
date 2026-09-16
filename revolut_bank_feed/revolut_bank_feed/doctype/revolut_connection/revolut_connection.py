import secrets
from urllib.parse import urlparse

import frappe
from frappe.model.document import Document
from frappe.utils import get_url, getdate, today

from revolut_bank_feed.auth import lock_configuration


class RevolutConnection(Document):
    def validate(self):
        frappe.only_for("System Manager")
        if not self.is_new() and not frappe.flags.revolut_configuration_locked:
            lock_configuration(self.name)
        parsed = urlparse(self.redirect_uri or "")
        if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
            frappe.throw("Redirect URI must be an HTTPS URL without credentials.")
        if self.issuer != parsed.hostname:
            frappe.throw("Issuer must exactly match the redirect URI hostname.")
        if self.enabled and not self.authorized:
            frappe.throw("Exchange an authorization code before enabling this connection.")
        if getdate(self.historical_from) > getdate(today()):
            frappe.throw("Historical From cannot be in the future.")
        for key, low, high in [
            ("lookback_days", 1, 90),
            ("poll_overlap_minutes", 1, 1440),
            ("window_days", 1, 31),
            ("audit_window_days", 1, 366),
        ]:
            if not low <= int(self.get(key) or 0) <= high:
                frappe.throw(f"{key} must be between {low} and {high}.")
        old = self.get_doc_before_save()
        protected = [
            f.fieldname
            for f in frappe.get_meta(self.doctype).fields
            if f.read_only and f.fieldname not in ("webhook_url", "webhook_key")
        ]
        if old:
            if any(old.get(key) != self.get(key) for key in protected):
                frappe.throw("Connection sync and token state can only be changed by the connector.")
            writable = [
                f.fieldname
                for f in frappe.get_meta(self.doctype).fields
                if not f.read_only and f.fieldname != "enabled"
            ]
            if old.enabled and any(old.get(key) != self.get(key) for key in writable):
                frappe.throw("Disable and save the connection before changing configuration.")
            for key in ("company", "environment"):
                if old.get(key) != self.get(key):
                    frappe.throw(f"{key} cannot be changed; create a separate connection.")
            if old.enabled and any(
                old.get(k) != self.get(k) for k in ("client_id", "issuer", "redirect_uri", "private_key")
            ):
                frappe.throw("Disable and save the connection before changing authorization settings.")
        elif any(self.get(key) for key in protected):
            frappe.throw("Do not supply initial sync or token state.")
        if old and old.webhook_key != self.webhook_key:
            frappe.throw("Webhook routing identity is immutable.")
        if not self.webhook_key:
            self.webhook_key = secrets.token_urlsafe(32)
        self.webhook_url = (
            get_url("/api/method/revolut_bank_feed.webhooks.receive") + "?key=" + self.webhook_key
        )
        if self.webhook_enabled and not self.get_password("webhook_secret", raise_exception=False):
            frappe.throw("Set the webhook signing secret before enabling the webhook.")
