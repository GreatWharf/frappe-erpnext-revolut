import frappe


def has_app_permission():
    """The v15/v16 apps-screen hook must return an explicit boolean."""
    return "System Manager" in frappe.get_roles()


def ensure_navigation():
    """Add entry points after standard navigation sync; preserve existing customizations."""
    import json

    from revolut_bank_feed.navigation_data import merge_home_icon, workspace_document

    if frappe.__version__.split(".")[0] == "15":
        # v15's legacy Desktop Icon is not the v16 launcher; its Desk uses Workspace.
        if not frappe.db.exists("Workspace", "Revolut Bank Feed"):
            frappe.get_doc(workspace_document()).insert(ignore_permissions=True)
        frappe.cache.delete_key("bootinfo")
        return

    # after_install runs before Frappe's standard navigation sync on a fresh site.
    for kind, doctype in (("workspace_sidebar", "Workspace Sidebar"), ("desktop_icon", "Desktop Icon")):
        if not frappe.db.exists(doctype, "Revolut Bank Feed"):
            path = frappe.get_app_path("revolut_bank_feed", kind, "revolut_bank_feed.json")
            with open(path) as source:
                frappe.get_doc(json.load(source)).insert(ignore_permissions=True)

    if frappe.db.exists("Workspace Sidebar", "Banking"):
        sidebar = frappe.get_doc("Workspace Sidebar", "Banking")
        changed = False
        for item in [
            {
                "type": "Link",
                "label": "Connect Revolut",
                "link_type": "Page",
                "link_to": "revolut-setup",
                "icon": "plug",
                "child": 0,
            },
            {
                "type": "Link",
                "label": "Banking app",
                "link_type": "URL",
                "url": "/banking",
                "icon": "landmark",
                "child": 0,
            },
        ]:
            target = item.get("link_to") or item.get("url")
            if not any((row.link_to or row.url) == target for row in sidebar.items):
                sidebar.append("items", item)
                changed = True
        if changed:
            sidebar.save(ignore_permissions=True)

    icon = frappe.get_doc("Desktop Icon", "Revolut Bank Feed").as_dict()
    keys = (
        "label",
        "name",
        "app",
        "icon_type",
        "link_type",
        "link",
        "link_to",
        "logo_url",
        "standard",
        "hidden",
        "parent_icon",
        "idx",
    )
    icon = {key: icon.get(key) for key in keys}
    for saved in frappe.get_all("Desktop Layout", fields=["name", "user", "layout"]):
        if "System Manager" not in frappe.get_roles(saved.user):
            continue
        layout = json.loads(saved.layout or "[]")
        if not isinstance(layout, list):
            continue
        updated = merge_home_icon(layout, icon)
        if updated != layout:
            frappe.db.set_value("Desktop Layout", saved.name, "layout", json.dumps(updated))
    frappe.cache.delete_key("desktop_icons")
    frappe.cache.delete_key("bootinfo")
