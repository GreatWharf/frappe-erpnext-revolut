import ast
import json
from pathlib import Path

ROOT = Path(__file__).parents[1]


def test_doctype_fields_and_controller_paths_are_installable():
    folder = ROOT / "revolut_bank_feed" / "revolut_bank_feed" / "doctype"
    specs = list(folder.glob("*/*.json"))
    assert len(specs) == 11
    for path in specs:
        doc = json.loads(path.read_text())
        assert doc["module"] == "Revolut Bank Feed"
        fields = [field["fieldname"] for field in doc["fields"]]
        assert len(fields) == len(set(fields))
        assert set(fields) == set(doc["field_order"])
        assert path.stem == doc["name"].lower().replace(" ", "_")
        tree = ast.parse(path.with_suffix(".py").read_text())
        assert any(
            isinstance(node, ast.ClassDef) and node.name == doc["name"].replace(" ", "") for node in tree.body
        )
        assert all(permission["role"] == "System Manager" for permission in doc["permissions"])


def test_all_credentials_are_password_fields():
    path = ROOT / "revolut_bank_feed/revolut_bank_feed/doctype/revolut_connection/revolut_connection.json"
    fields = {field["fieldname"]: field for field in json.loads(path.read_text())["fields"]}
    for key in ["private_key", "access_token", "refresh_token", "webhook_secret", "previous_webhook_secret"]:
        assert fields[key]["fieldtype"] == "Password"
        assert fields[key]["permlevel"] == 1
