#!/usr/bin/env python3
"""Symbol Sorter

Sort components (data models) in an OpenAPI contract YAML file topologically, so that you can migrate with confidence.

Topological sort ensures that depended-upon symbols always go first. This makes symbols with fewer dependencies always go first.

Usage:
  sort_components_in_contract.py [<contract_path>]
"""
from docopt import docopt

import os
from graphlib import TopologicalSorter, CycleError
import logging
import yaml


# Extract the references between symbols (`$ref`) from the definitions to a graph.
def find_recursively(scope, key: str = "$ref"):
    if isinstance(scope, dict):
        return find_recursively_in_dict(scope, key)
    elif isinstance(scope, list):
        return find_recursively_in_list(scope, key)
    return set()


def find_recursively_in_list(scope: list, key: str = "$ref"):
    results = set()
    for i in scope:
        results.update(find_recursively(i, key))
    return results


def find_recursively_in_dict(scope: dict, key: str = "$ref"):
    results = set()
    if key in scope:
        results.add(scope[key])
    for k, v in scope.items():
        results.update(find_recursively(v, key))
    return results


def build_dependency_graph(contract: dict) -> dict:
    g = dict()
    for symbol_name, symbol_def in contract["components"]["schemas"].items():
        symbols_referenced = find_recursively(symbol_def)
        symbols_referenced = set(
            map(
                lambda x: x.removeprefix("#/components/schemas/"),
                symbols_referenced,
            )
        )
        if symbol_name in symbols_referenced:
            logging.warning(f"`{symbol_name}` references itself.")
            symbols_referenced.remove(symbol_name)
        g[symbol_name] = symbols_referenced
    return g


def sort_symbols(contract_path: str) -> tuple[str]:
    with open(contract_path) as f:
        contract = yaml.load(f, Loader=yaml.FullLoader)

    # Get a list of all the symbols defined in this contract.
    components_in_contract = set(contract["components"]["schemas"].keys())

    logging.info(
        f"There are {len(components_in_contract)} symbols defined in the contract."
    )
    g = build_dependency_graph(contract)

    # Topologically sort the symbols.

    symbols_to_migrate_sorted = None
    while symbols_to_migrate_sorted is None:
        sorter = TopologicalSorter(g)
        try:
            symbols_to_migrate_sorted_generator = sorter.static_order()
            # Clean up.
            symbols_to_migrate_sorted_filtered = filter(
                lambda x: ".yaml#/" not in x, symbols_to_migrate_sorted_generator
            )
            symbols_to_migrate_sorted = tuple(symbols_to_migrate_sorted_filtered)
        except CycleError as e:
            cycle = e.args[1]
            logging.warning(
                f"Cycle detected: {' -> '.join(cycle)}. Randomly breaking the cycle by pretending `{cycle[0]}` wasn't a dependency of `{cycle[1]}`."
            )
            g[cycle[1]].remove(cycle[0])

    symbols_referenced_but_not_in_contract = set(symbols_to_migrate_sorted).difference(
        components_in_contract
    )
    logging.info(
        f"We want to have {len(symbols_to_migrate_sorted)} symbols migrated. The extra {len(symbols_referenced_but_not_in_contract)} symbols are referenced from other contracts (mostly from the ExperienceTypes library). We will be dealing with them next up in the _Find what symbols are referencable_ section."
    )
    return symbols_to_migrate_sorted


if __name__ == "__main__":
    arguments = docopt(__doc__, version="Symbol Sorter")
    logging.debug(f"Docopt arguments: {arguments}")

    # Load the OpenAPI YAML file as a nested dictionary.
    contract_path = arguments["<contract_path>"]
    if not contract_path:
        logging.warning("`contract_path` not defined. Using default value.")
        contract_path = os.path.expanduser(
            "~/Projects/scaffold/src/main/resources/contract.yaml"
        )
    symbols = sort_symbols(contract_path)
    print(",".join(symbols))
