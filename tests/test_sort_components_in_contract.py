from pyjami.sort_components_in_contract import find_recursively, sort_symbols

import os


def test_find_recursively():
    scope = {
        0: {"$ref": 1, 2: 3},
        9: [{4: 5}, {"$ref": 6, 7: 8}],
        10: {11: 12},
        13: [14],
    }
    got = find_recursively(scope)
    assert got == {1, 6}


def test_sort_symbols():
    contract_path = os.path.join(
        os.path.dirname(__file__),
        "dummy_contract_for_test_sort_components_in_contract.yaml",
    )
    got = sort_symbols(contract_path)
    assert got == tuple(("Pet", "Pets"))
