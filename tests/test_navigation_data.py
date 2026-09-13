from revolut_bank_feed.navigation_data import merge_home_icon


def test_adds_missing_icon_without_changing_saved_layout():
    layout = [{"label": "Accounting", "idx": 4, "hidden": 0}]
    icon = {"label": "Revolut Bank Feed", "logo_url": "/new.svg", "idx": 0}
    result = merge_home_icon(layout, icon)
    assert result[0] == layout[0]
    assert len(layout) == 1
    assert result[1]["idx"] == 5
    assert result[1]["label"] == "Revolut Bank Feed"


def test_refreshes_branding_but_preserves_user_placement_and_visibility():
    layout = [
        {
            "label": "Revolut Bank Feed",
            "idx": 7,
            "hidden": 1,
            "parent_icon": "Accounting",
            "logo_url": "/old.svg",
        }
    ]
    icon = {"label": "Revolut Bank Feed", "logo_url": "/new.svg", "idx": 0, "hidden": 0, "parent_icon": None}
    result = merge_home_icon(layout, icon)
    assert len(result) == 1
    assert result[0]["logo_url"] == "/new.svg"
    assert result[0]["hidden"] == 1
    assert result[0]["idx"] == 7
    assert result[0]["parent_icon"] == "Accounting"
    assert merge_home_icon(result, icon) == result
