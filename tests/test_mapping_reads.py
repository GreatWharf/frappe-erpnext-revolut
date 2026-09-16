import pytest
from test_persistence import Attr
from test_persistence import importer as importer


@pytest.mark.parametrize("for_update", [False, True])
def test_get_maps_uses_supported_current_reads_only_when_requested(importer, monkeypatch, for_update):
    module, store = importer
    connection = Attr(name="connection", company="Acme")
    mapping = Attr(
        name="map", account_id="known", currency="GBP", company="Acme", enabled=1, bank_account="bank"
    )
    bank = Attr(company="Acme", account="ledger", is_company_account=1, disabled=0)
    ledger = Attr(company="Acme", account_type="Bank", account_currency="GBP", is_group=0, disabled=0)
    reads = []

    def get_all(doctype, *, filters, fields):
        assert not for_update
        assert doctype == "Revolut Account Map"
        assert filters == {"connection": "connection"}
        assert fields == ["*"]
        reads.append("snapshot-maps")
        return [mapping]

    def get_values(doctype, filters, fieldname, *, as_dict=False, for_update=False):
        assert doctype == "Revolut Account Map"
        assert filters == {"connection": "connection"}
        assert fieldname == "*"
        assert as_dict and for_update
        reads.append("current-maps")
        return [mapping]

    def get_doc(doctype, name, **kwargs):
        assert kwargs == ({"for_update": True} if for_update else {})
        reads.append(doctype)
        return bank if doctype == "Bank Account" else ledger

    monkeypatch.setattr(module.frappe, "get_all", get_all)
    monkeypatch.setattr(store, "get_values", get_values, raising=False)
    monkeypatch.setattr(module.frappe, "get_doc", get_doc)
    result = module.get_maps(connection, for_update=True) if for_update else module.get_maps(connection)
    assert result == {("known", "GBP"): mapping}
    assert reads == ["current-maps" if for_update else "snapshot-maps", "Bank Account", "Account"]
