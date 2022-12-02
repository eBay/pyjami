# **Py**thon-based **Ja**va code **mi**gration helper (Pyjami)
[![pre-commit](https://img.shields.io/badge/pre--commit-enabled-brightgreen?logo=pre-commit&logoColor=white)](https://github.com/pre-commit/pre-commit)
[![Code style: black](https://img.shields.io/badge/code%20style-black-000000.svg)](https://github.com/psf/black)
[![Code Coverage](coverage.svg)](https://github.com/dbrgn/coverage-badge)
[![CodeQL](https://github.com/ebay/pyjami/workflows/CodeQL/badge.svg)](https://github.com/ebay/pyjami/actions?query=workflow%3ACodeQL)
[![PyPI version](https://badge.fury.io/py/pyjami.svg)](https://badge.fury.io/py/pyjami)
[![HitCount](https://hits.dwyl.com/ebay/pyjami.svg?style=flat)](http://hits.dwyl.com/ebay/pyjami)

Python library which helps to automate the migration of Java classes/enums/interfaces.

## Scenario

When would you want to use this?

You have a Java project. You want to migrate 99+ classes/enums/interfaces in it. Let's say it contains a `com.foo.bar.MyClass`, and you want to replace all its usages with those of `org.example.newPackage.MyClass`.

Your first instinct is a **find-and-replace**, but you'd have to deal with [wildcard imports](https://www.baeldung.com/java-wildcard-imports) and partially-qualified references at each level of the package.

You thought of **IntelliJ IDEA**. It offers a `Refactor` > `Migrate Packages and Classes` feature, but:
* You have a more **complicated mapping** to specify. Perhaps you want to migrate `lorem.Foo` to `ipsum.Foo`, but for `lorem.Bar`, you want to migrate it to `dolor.Bar`. To do so in IntelliJ IDEA, you'd have to manually punch in each mapping rule.
* You don't want to migrate all of them in **one transaction**. Maybe you want to run unit tests after migrating each, committing the changes to a separate revision only if the tests all pass. IntelliJ IDEA doesn't offer such fine-grained control.
* Or you simply can't use / would avoid IntelliJ IDEA for some reason.

That's when this toolkit comes to help.

## Usage

### Migrate one symbol
Please ensure that you've installed these executable programs:

* `gnu-sed` (installed by default on most Linux distros; a manual step on macOS). This is because the BSD edition of `sed` does not support word boundaries ("`\b`").
* [`ripgrep`](https://github.com/BurntSushi/ripgrep), a line-oriented search tool that recursively searches the current directory for a regex pattern.

To migrate usages of `com.foo.bar.MyClass` to `org.example.newPackage.MyClass`, use `migrate(...)` in `java_symbol_migration_helpers.py`:

```python
from pathlib import Path
from pyjami.java_symbol_migration_helpers import find_suitable_sed_command, migrate
migrate(
    symbol="MyClass",
    path="src/main/com/foo/bar",
    old_package="com.foo.bar",
    new_package="org.example.newPackage",
    repo_dir=Path("repo/"),
    pom_dependency="""
        <dependency>
            <!-- New home for MyClass. -->
            <groupId>org.example</groupId>
            <artifactId>newPackage</artifactId>
        </dependency>
    """,
    sed_executable=find_suitable_sed_command(),
)
```

### Gather information for a list of symbols to migrate

We provide a `make_table()` function that gathers information about the symbols that are required in the migration process to follow.

Given an iterable (preferably a Pandas Series) of string, each of which being a symbol to migrate, this function returns a Pandas Dataframe with each line indicating the name, the java file path, and the package name of that symbol in the given directory.

For example, if you have `MyProject/Lorem.java` containing:

```java
package com.example.MyProject;

class Lorem {...}
```

and you run:

```python
make_table(
    symbols_to_migrate=("Lorem",),
    search_within_directory=pathlib.Path("MyProject/"),
)
```

you will get a table with one row of these values:

- `symbol`: `Lorem`
- `path`: `MyProject/Lorem.java`
- `package`: `com.example.MyProject`

These are the required information to feed into `migrate()`.

In the case that multiple file paths are found for a given symbol, the first file path that is a child of the firstmost entry in `order_of_preference` is taken. When none is present, it's treated as if no file path is found for this symbol. Therefore, even if you don't have a preference of which directories to favor, you might still want to provide `order_of_preference` with at least a `search_within_directory`, so that at least some choice is taken.

### Extra -- Sorting Components in an OpenAPI Contract

This is a common scenario to encounter when migrating handwritten Java code to a library generated from OpenAPI contract. In fact, this is the original case that kicked off this project.

Therefore, Pyjami also provides tools that specifically help with OpenAPI migrations. For example, `sort_components_in_contract.py` sorts components (data models) in an OpenAPI contract YAML file topologically, so that you can migrate with confidence.

Suppose your OpenAPI contract declares 2 components, `Pet` and `Pets`, with `Pets` referencing ("depending on") `Pet`:
```yaml
openapi: "3.0.0"
components:
  schemas:
    Pet:
      type: object
    Pets:
      type: array
      items:
        $ref: "#/components/schemas/Pet"
```

You can get the optimal order to migrate these symbols using `sort_symbols(...)`:

```python
>>> from pyjami.sort_components_in_contract import sort_symbols
>>> sort_symbols("contract.yaml")
("Pet", "Pets")
```

This ensures that, by the time you attempt to migrate `class Pets`, `class Pet` has already been migrated. This is particularly useful if you want to ensure that the migration of every single symbol should keep the unit tests intact.

## Development

This repository uses [Poetry](https://python-poetry.org/) for managing dependencies and packaging.

### Documentation

Refer to `docs/index.html` for documentation. It's also published as GitHub pages [here](https://opensource.ebay.com/pyjami/pyjami/java_symbol_migration_helpers.html).

Pyjami's documentation is generated via the [`pdoc`](https://pdoc.dev/docs/pdoc.html) tool:

```shell
pdoc ./pyjami -o ./docs
```

### Pre-Commit Hooks

The hooks are required for the team. Although skipping this step does not prevent you from making a commit, this step is critical in maintaining a uniform coding style across developers.

From now on, whenever you make a new commit, you should see logs like this in your terminal:

```
Check Yaml...............................................................Passed
Fix End of Files.........................................................Passed
Trim Trailing Whitespace.................................................Passed
black....................................................................Passed
```

If you see [Black](https://github.com/psf/black) failed and modified files:

```
Check Yaml...............................................................Passed
Fix End of Files.........................................................Passed
Trim Trailing Whitespace.................................................Passed
black....................................................................Failed
- hook id: black
- files were modified by this hook

reformatted path/to/file.py
All done! ✨ 🍰 ✨
1 file reformatted.
```

Then `git add` the auto-modified files and retry your `git commit` command.

Please report a bug if you do not see such messages.

### Testing

This project uses [`pytest`](https://docs.pytest.org/) for running tests and [`pytest-cov`](https://pytest-cov.readthedocs.io/en/latest/) for collecting test coverage information.

To run the tests, run:

```shell
pytest --cov=pyjami
```

You'll see a report like this:

```
---------- coverage: platform darwin, python 3.10.6-final-0 ----------
Name                                      Stmts   Miss  Cover
-------------------------------------------------------------
pyjami/__init__.py                            0      0   100%
pyjami/java_symbol_migration_helpers.py     150     18    88%
pyjami/sort_components_in_contract.py        53      8    85%
-------------------------------------------------------------
TOTAL                                       203     26    87%
```

Then, you can update the coverage badge:

```shell
coverage-badge -o coverage.svg
```

### Releasing

This library is available as a package on PyPI [here](https://pypi.org/project/pyjami/). To release a new version:

1. Bump the version number in `pyproject.toml` with a commit. Please follow [Semantic Versioning 2.0.0](https://semver.org/) specifications.
2. Create a new release on GitHub [here](https://github.com/eBay/pyjami/releases).

A GitHub workflow will be automatically triggered to build & publish this package to PyPI. Till eBay have an official account on PyPI, this action will keep on using a _PyPI API Token_ associated with Ming's personal PyPI account. The Token is stored on this GitHub repository as an Action Secret.

# License

Apache 2.0.
