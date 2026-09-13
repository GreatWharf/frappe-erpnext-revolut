import frappe


def has_app_permission():
    """v16 app navigation hook must return an explicit boolean."""
    return "System Manager" in frappe.get_roles()
