from copy import deepcopy


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
