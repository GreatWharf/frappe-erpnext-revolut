"""Run with bench on an isolated test site, never against production accounting data."""

from copy import deepcopy
from uuid import uuid4

import frappe
from frappe.tests import IntegrationTestCase

from revolut_bank_feed.core import FeedError, identity
from revolut_bank_feed.importer import get_maps, ingest

# Frappe's test-record builder creates ERPNext's standard test Company and COA.
EXTRA_TEST_RECORD_DEPENDENCIES = ["Company"]


class TestBankFeedIntegration(IntegrationTestCase):
    def setUp(self):
        super().setUp()
        frappe.set_user("Administrator")
        suffix = uuid4().hex[:10]
        self.currency = frappe.get_value("Company", "_Test Company", "default_currency")
        parent = frappe.get_value(
            "Account", {"company": "_Test Company", "is_group": 1, "root_type": "Asset"}, "name"
        )
        account = frappe.get_doc(
            {
                "doctype": "Account",
                "account_name": "Feed " + suffix,
                "company": "_Test Company",
                "parent_account": parent,
                "is_group": 0,
                "account_type": "Bank",
                "account_currency": self.currency,
            }
        ).insert()
        bank = frappe.get_doc({"doctype": "Bank", "bank_name": "Feed Bank " + suffix}).insert()
        self.bank = frappe.get_doc(
            {
                "doctype": "Bank Account",
                "account_name": "Feed " + suffix,
                "bank": bank.name,
                "account": account.name,
                "company": "_Test Company",
                "is_company_account": 1,
            }
        ).insert()
        self.connection = frappe.get_doc(
            {
                "doctype": "Revolut Connection",
                "connection_name": "Test " + suffix,
                "company": "_Test Company",
                "environment": "Sandbox",
                "client_id": "synthetic-client",
                "redirect_uri": "https://example.test/consent",
                "issuer": "example.test",
                "historical_from": "2020-01-01",
                "lookback_days": 7,
                "window_days": 7,
                "audit_window_days": 30,
                "audit_enabled": 1,
                "enabled": 0,
            }
        ).insert()
        self.mapping = frappe.get_doc(
            {
                "doctype": "Revolut Account Map",
                "connection": self.connection.name,
                "account_id": "test-account-" + suffix,
                "currency": self.currency,
                "bank_account": self.bank.name,
                "timezone": "UTC",
                "fee_policy": "Review",
                "enabled": 1,
            }
        ).insert()
        self.tx = {
            "id": "test-tx-" + suffix,
            "type": "transfer",
            "state": "completed",
            "created_at": "2026-01-01T12:00:00Z",
            "updated_at": "2026-01-01T12:00:00Z",
            "completed_at": "2026-01-01T12:00:00Z",
            "legs": [
                {
                    "leg_id": "test-leg-" + suffix,
                    "account_id": self.mapping.account_id,
                    "amount": "-12.34",
                    "currency": self.currency,
                }
            ],
        }

    def test_credentials_survive_client_id_and_document_saves(self):
        from unittest.mock import patch

        from revolut_bank_feed.auth import save_tokens, secret
        from revolut_bank_feed.setup import generate_certificate, save_client_id

        # Keep fixture writes in the test transaction; no remote authorization occurs.
        with patch.object(frappe.db, "commit"):
            generate_certificate(self.connection.name)
            private_key = secret(self.connection.name, "private_key")
            self.assertTrue(private_key)
            save_client_id(self.connection.name, "synthetic-client-updated")
            self.assertEqual(secret(self.connection.name, "private_key"), private_key)
            self.connection.reload()
            save_tokens(
                self.connection,
                {
                    "access_token": "synthetic-access",
                    "refresh_token": "synthetic-refresh",
                    "expires_in": 2400,
                },
            )
            self.connection.reload()
            self.connection.save()
            self.assertEqual(secret(self.connection.name, "private_key"), private_key)
            self.assertEqual(secret(self.connection.name, "access_token"), "synthetic-access")
            self.assertEqual(secret(self.connection.name, "refresh_token"), "synthetic-refresh")

    def test_submitted_bank_row_is_idempotent_and_has_no_gl_entries(self):
        gl_count = frappe.db.count("GL Entry")
        self.assertEqual(ingest(self.connection, self.tx)["created"], 1)
        self.assertEqual(ingest(self.connection, deepcopy(self.tx))["created"], 0)
        rows = frappe.get_all("Bank Transaction", filters={"bank_account": self.bank.name}, fields=["*"])
        self.assertEqual(len(rows), 1)
        self.assertEqual(rows[0].docstatus, 1)
        self.assertEqual(rows[0].status, "Unreconciled")
        self.assertAlmostEqual(float(rows[0].unallocated_amount), 12.34)
        self.assertEqual(rows[0].transaction_id, self.tx["id"])
        self.assertEqual(frappe.db.count("GL Entry"), gl_count)
        self.assertTrue(
            frappe.db.exists("Revolut Source Transaction", identity(self.connection.name, self.tx["id"]))
        )

    def test_reversion_requires_review_and_preserves_cancelled_original(self):
        ingest(self.connection, self.tx)
        self.tx.update(state="reverted", updated_at="2026-01-02T00:00:00Z")
        self.assertEqual(ingest(self.connection, self.tx)["review"], 1)
        bank_name = frappe.get_value("Bank Transaction", {"bank_account": self.bank.name}, "name")
        bank = frappe.get_doc("Bank Transaction", bank_name)
        self.assertEqual(bank.docstatus, 1)
        self.assertEqual(bank.custom_revolut_review_required, 1)
        with self.assertRaises(frappe.ValidationError):
            bank.cancel()
        ingest(
            self.connection, self.tx, apply_review=True, review_note="Statement confirms reverted transfer"
        )
        bank.reload()
        self.assertEqual(bank.docstatus, 2)
        self.assertEqual(frappe.db.count("Bank Transaction", {"bank_account": self.bank.name}), 1)

    def test_mapping_currency_must_match_linked_gl_currency(self):
        bad = frappe._dict(self.mapping.as_dict())
        bank = self.bank.as_dict()
        gl = frappe.get_doc("Account", self.bank.account).as_dict()
        from revolut_bank_feed.core import validate_mapping

        bad.currency = "GBP" if self.currency != "GBP" else "USD"
        with self.assertRaises(FeedError):
            validate_mapping(self.connection.company, bad, bank, gl)

    def test_disabled_map_keeps_historical_rows(self):
        ingest(self.connection, self.tx)
        self.mapping.enabled = 0
        self.mapping.save()
        maps = get_maps(self.connection)
        ingest(self.connection, self.tx, maps, apply_review=True, review_note="Paused account")
        self.assertEqual(
            frappe.get_value("Bank Transaction", {"bank_account": self.bank.name}, "docstatus"), 1
        )

    def test_source_identity_cannot_be_changed_by_normal_document_save(self):
        ingest(self.connection, self.tx)
        bank_name = frappe.get_value("Bank Transaction", {"bank_account": self.bank.name}, "name")
        bank = frappe.get_doc("Bank Transaction", bank_name)
        bank.custom_revolut_source_key = "forged"
        with self.assertRaises(frappe.ValidationError):
            bank.save()
