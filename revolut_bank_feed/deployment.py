"""CLI-only deployment hook; app code must already be present in the custom image.

Call from ONE serialized deployment initializer with the target site selected.
Backups, maintenance mode and traffic/worker ordering belong to the deployment.
Never invoke this from an HTTP handler or a document hook.
"""

import frappe
from frappe.installer import install_app

from .install import check_versions


def ensure_installed():
    if not frappe.local.site or frappe.session.user != "Administrator":
        frappe.throw("Run the deployment initializer as Administrator with an explicit site selected.")
    check_versions()
    installed = frappe.get_installed_apps()
    if "erpnext" not in installed:
        frappe.throw("A matching ERPNext v15 or v16 must already be installed on the target site.")
    if "revolut_bank_feed" not in frappe.get_all_apps():
        frappe.throw("The image's apps.txt must include revolut_bank_feed before site initialization.")
    if "revolut_bank_feed" in installed:
        return {"status": "already_installed"}
    install_app("revolut_bank_feed", verbose=True)
    return {"status": "installed"}
