from inventory_stage18_7 import build_inventory_rows_187
from rate_policy_stage18_7 import rate_factor_187, updated_unit_price_187

def test_rate_policy():
    # The default combined policy is the mean of the USD and gold increases.
    assert rate_factor_187(2, 3, 1, 1) == 2.5
    assert rate_factor_187(150, 120, 100, 100) == 1.35
    assert rate_factor_187(2, 3, 1, 1, "دلار بروز") == 2
    assert rate_factor_187(2, 3, 1, 1, "طلا بروز") == 3
    assert updated_unit_price_187(100, 2, 3, 1, 1) == 250

def test_inventory_material_rows_are_linked_to_transactions():
    rows = build_inventory_rows_187(
        [{"expense_id": "e1", "transaction_id": "t1", "category": "material",
          "description": "cement"}],
        [{"transaction_id": "t1", "amount": 125000}],
        lambda _row: {"quantity": 10, "unit": "bag"},
    )
    assert len(rows) == 1
    assert rows[0]["total_value"] == 125000
    assert rows[0]["quantity_value"] == 10
    assert rows[0]["unit_value"] == "bag"

def test_inventory_ignores_non_material_expenses():
    rows = build_inventory_rows_187(
        [{"expense_id": "e2", "category": "service", "description": "painting"}],
        [],
    )
    assert rows == []
