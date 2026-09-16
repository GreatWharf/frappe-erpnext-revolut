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
