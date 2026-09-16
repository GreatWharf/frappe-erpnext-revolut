import json
from copy import deepcopy


def workspace_document():
    """v15 Workspace entry points, kept separate from v16 navigation fixtures."""
    shortcuts = [
        {"label": "Connect Revolut", "type": "Page", "link_to": "revolut-setup"},
        {"label": "Connections", "type": "DocType", "link_to": "Revolut Connection", "doc_view": "List"},
        {
            "label": "Account mappings",
            "type": "DocType",
            "link_to": "Revolut Account Map",
            "doc_view": "List",
        },
        {"label": "Bank transactions", "type": "DocType", "link_to": "Bank Transaction", "doc_view": "List"},
        {
            "label": "Source transactions",
            "type": "DocType",
            "link_to": "Revolut Source Transaction",
            "doc_view": "List",
        },
        {"label": "Sync logs", "type": "DocType", "link_to": "Revolut Sync Log", "doc_view": "List"},
    ]
    return {
        "doctype": "Workspace",
        "name": "Revolut Bank Feed",
        "label": "Revolut Bank Feed",
        "title": "Revolut Bank Feed",
        "module": "Revolut Bank Feed",
        "public": 1,
        "is_hidden": 0,
        "icon": "bank",
        "roles": [{"role": "System Manager"}],
        "shortcuts": shortcuts,
        "content": json.dumps(
            [
                {
                    "id": f"revolut-shortcut-{index}",
                    "type": "shortcut",
                    "data": {"shortcut_name": row["label"], "col": 4},
                }
                for index, row in enumerate(shortcuts)
            ]
        ),
    }


def workspace_sidebar_document():
    """v16 Workspace Sidebar entry point, kept in sync with workspace_sidebar/revolut_bank_feed.json."""
    return {
        "doctype": "Workspace Sidebar",
        "name": "Revolut Bank Feed",
        "title": "Revolut Bank Feed",
        "app": "revolut_bank_feed",
        "module": "Revolut Bank Feed",
        "standard": 1,
        "header_icon": "landmark",
        "items": [
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
            {
                "type": "Link",
                "label": "Bank transactions",
                "link_type": "DocType",
                "link_to": "Bank Transaction",
                "icon": "arrow-left-right",
                "child": 0,
            },
            {
                "type": "Link",
                "label": "Account mappings",
                "link_type": "DocType",
                "link_to": "Revolut Account Map",
                "icon": "link",
                "child": 0,
            },
            {
                "type": "Link",
                "label": "Sync logs",
                "link_type": "DocType",
                "link_to": "Revolut Sync Log",
                "icon": "list",
                "child": 0,
            },
            {
                "type": "Link",
                "label": "Connection settings",
                "link_type": "DocType",
                "link_to": "Revolut Connection",
                "icon": "settings",
                "child": 0,
            },
        ],
    }


def desktop_icon_document():
    """v16 Desktop Icon entry point, kept in sync with desktop_icon/revolut_bank_feed.json."""
    return {
        "doctype": "Desktop Icon",
        "name": "Revolut Bank Feed",
        "label": "Revolut Bank Feed",
        "icon_type": "App",
        "link_type": "External",
        "link": "/desk/revolut-setup?sidebar=Revolut%20Bank%20Feed",
        "app": "revolut_bank_feed",
        "standard": 1,
        "hidden": 0,
        "logo_url": "/assets/revolut_bank_feed/images/revolut-business-icon.svg",
        "roles": [{"role": "System Manager"}],
    }


def merge_home_icon(layout, icon):
    """Refresh app metadata while retaining the user's layout and hidden state."""
    result = deepcopy(layout)
    for item in result:
        if item.get("label") == icon["label"]:
            placement = {
                key: item[key] for key in ("idx", "hidden", "parent_icon", "in_folder") if key in item
            }
            item.update(icon)
            item.update(placement)
            return result
    added = deepcopy(icon)
    added["idx"] = max((item.get("idx") or 0 for item in result), default=0) + 1
    result.append(added)
    return result
