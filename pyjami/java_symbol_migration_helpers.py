"""
Helper/utility functions for migrating usages of a Java symbol from one package to another.
"""
import re
import os
import logging
import subprocess
import platform
from pathlib import Path
import pandas as pd

from collections.abc import Iterable
from functools import partial

package_declaration_pattern = re.compile(r"\bpackage.+?;\n")


def __get_score_in_order_of_preference_for_path(
    path: Path, order_of_preference: tuple[Path] = tuple()
) -> int:
    """
    Return the index of the first item in `order_of_preference` that is a parent of `path`.

    In the case where none of the candidates is a parent of `path`, return the length -- thus, the max-possible index + 1 -- of the `order_of_preference`.

    For example, when `path` is `b/d/f.java` and `order_of_preference` contains:
    - `a/`
    - `b/`
    - `c/`
    - `b/d/`

    This function will return `1`, because `b/` (with index `1`) is the first entry in `order_of_preference` that is a parent of `path`.

    See https://stackoverflow.com/a/2364277/15154381.
    """
    score_generator = (
        i
        for i, candidate in enumerate(order_of_preference)
        if path.is_relative_to(candidate)
    )
    return next(score_generator, len(order_of_preference))


def __find_java_files(
    symbol: str,
    search_within_directory: Path,
    order_of_preference: tuple[Path] = tuple(),
) -> str:
    """Find Java files by name."""
    paths = tuple(search_within_directory.rglob(symbol + ".java"))
    if len(paths) == 0:
        logging.warning(f"No path is found for {symbol}.")
        return None
    if len(paths) > 1:
        get_score = partial(
            __get_score_in_order_of_preference_for_path,
            order_of_preference=order_of_preference,
        )
        path = min(paths, key=get_score)
        logging.warning(
            f"{len(paths)} paths are found for {symbol}. We will use `{path.as_posix()}`."
        )
    else:
        path = paths[0]
    return path.as_posix()


package_pattern = re.compile("package (?P<name>.+?);")


def __get_package_name(path: str) -> str:
    """Get package name from `.java` files."""
    if path is None:
        return None
    with open(path) as f:
        content = f.read()
    match = package_pattern.search(content)
    if match is None:
        logging.error(f"Didn't find package name in `{path}`.")
        return None
    return match.group("name")


def make_table(
    symbols_to_migrate: Iterable[str],
    search_within_directory: Path = Path(),
    order_of_preference: tuple[Path] = tuple(),
) -> pd.DataFrame:
    """
    Gather information about the symbols that are required in the migration process to follow.

    Given an iterable (preferably a Pandas Series) of string, each of which being a symbol to migrate, this function returns a Pandas Dataframe with each line indicating the name, the java file path, and the package name of that symbol in the given directory.

    In the case that multiple file paths are found for a given symbol, the first file path that is a child of the firstmost entry in `order_of_preference` is taken. When none is present, it's treated as if no file path is found for this symbol. Therefore, even if you don't have a preference of which directories to favor, you might still want to provide `order_of_preference` with at least a `search_within_directory`, so that at least some choice is taken.
    """
    if type(symbols_to_migrate) != pd.Series:
        symbols_to_migrate = pd.Series(symbols_to_migrate, name="symbol")
    paths = symbols_to_migrate.apply(
        __find_java_files,
        search_within_directory=search_within_directory,
        order_of_preference=order_of_preference,
    )
    package_names = paths.apply(__get_package_name)
    paths = paths.str.removeprefix(search_within_directory.as_posix() + "/")
    df = pd.DataFrame(
        {
            "symbol": symbols_to_migrate,
            "path": paths,
            "package": package_names,
        }
    )
    df.dropna(inplace=True)
    return df


def find_poms_of_modified_modules(repo_dir: Path) -> pd.Series:
    """
    If your repository contains multiple modules, you might find this function useful.

    When you run some of the refactoring functions provided in this package, you might want to ensure that the `pom.xml` files of the sub-modules you tempered with contain the right dependencies. This is when this function will come in handy.
    """
    compose_pom_path = lambda x: os.path.join(repo_dir.as_posix(), x, "pom.xml")
    command = f"git -C {repo_dir.as_posix()} diff --name-only"
    result = subprocess.run(command, text=True, shell=True, capture_output=True)
    files_changed = result.stdout.rstrip(os.linesep).split(os.linesep)
    files_changed = pd.Series(files_changed)
    modules_changed = files_changed.apply(lambda x: x.split("/")[0]).drop_duplicates()
    poms_of_modules_changed = modules_changed.apply(compose_pom_path)
    are_poms_exist = poms_of_modules_changed.apply(os.path.isfile)
    poms_of_modules_changed = poms_of_modules_changed.loc[are_poms_exist]
    return poms_of_modules_changed


def find_suitable_sed_command():
    """
    Find the suitable `sed` command.

    The BSD edition of `sed` does not support word boundaries ("`\b`").

    To install the GNU edition of `sed`:
    ```shell
    brew install gnu-sed
    ```
    """
    if platform.system() == "Linux":
        return "sed"
    if platform.system() == "Darwin":
        return "gsed"
    # else:
    raise RuntimeWarning("Platform not supported. Trying `sed`.")
    return "sed"


def migrate_direct_usages(
    old_fully_qualified_name: str,
    new_fully_qualified_name: str,
    repo_dir: Path,
    sed_executable: str,
):
    command = f"rg '{old_fully_qualified_name}\\b' --type java --files-with-matches {repo_dir.as_posix()}"
    result = subprocess.run(command, text=True, shell=True, capture_output=True)
    java_paths = []
    if result.returncode == 0 and len(result.stdout) > 0:
        java_paths = result.stdout.rstrip(os.linesep).split(os.linesep)

    for java_path in java_paths:
        command = f"{sed_executable} -i 's/{old_fully_qualified_name}\\b/{new_fully_qualified_name}/g' {java_path}"
        result = subprocess.run(command, text=True, shell=True, capture_output=True)
        if result.stderr != "":
            logging.error(f'Stderr printed: "{result.stderr}"')


def replace_in_file(path: str, pattern: re.Pattern, replacement: str) -> int:
    """
    Replaces occurences of `pattern` in the file `path` with `replacement`.
    Returns a count of substitutions made.
    """
    with open(path) as f:
        content = f.read()
    content, num_substitutions = pattern.subn(replacement, content)
    if num_substitutions == 0:
        return 0
    with open(path, "w") as f:
        f.write(content)
    return num_substitutions


def ensure_file_contains(
    path: str,
    anchor: str = "<dependencies>",
    content_to_ensure: str = "<dependency />",
):
    """
    Ensures that the `pom.xml` files provided all contains a dependency as specified by `dependency_xml`.
    It adds the dependency immediately after `anchor` in the file if not found.
    """
    with open(path) as f:
        content = f.read()
    if content_to_ensure in content:
        return
    index = content.index(anchor) + len(anchor)
    content = content[:index] + content_to_ensure + content[index:]
    with open(path, "w") as f:
        f.write(content)


def migrate_wildcard_imports(
    package: str,
    usage_pattern: re.Pattern,
    new_fully_qualified_name: str,
    repo_dir: Path,
):
    """
    Wildcard imports: `import packageA.*;` might give you access to `packageA.packageB.Class`, in the form of `new packageB.Class();`.

    This function will:
    1. Find all Java files that 1) import `{package}.*` and 2) contains `usage_pattern`.
    2. In each file, replace each `usage_pattern` with `new_fully_qualified_name`.


    For example, if you want to migrate usages of `com.foo.bar.MyClass` to `org.newPackage.YourClass` for all code that imports `com.foo.*`, you would give:

    ```python3
    package = "com.foo",
    usage_pattern = re.compile(r'\bbar.MyClass\b'),
    new_fully_qualified_name = "org.newPackage.YourClass",
    ```

    You have to install [`ripgrep`](https://github.com/BurntSushi/ripgrep) first.
    """

    star_import = f"^import {package}.\\*;$"
    # Find files that import at this level with a wildcard.
    command = (
        f"rg '{star_import}' --type java --files-with-matches {repo_dir.as_posix()}"
    )
    result = subprocess.run(command, text=True, shell=True, capture_output=True)
    java_paths = []
    if result.returncode == 0 and len(result.stdout) > 0:
        java_paths = result.stdout.rstrip(os.linesep).split(os.linesep)
    if len(java_paths) == 0:
        return
    logging.debug(
        f"Trying to migrate wildcard imports. {len(java_paths)} files contain `{star_import}`."
    )
    # Replace usages of this symbol in each file.
    nums_substitutions = []
    for java_path in java_paths:
        nums_substitutions.append(
            replace_in_file(java_path, usage_pattern, new_fully_qualified_name)
        )
    count = sum(map(lambda x: x > 0, nums_substitutions))
    logging.debug(
        f"Modified {count} out of {len(nums_substitutions)} files with wildcard imports, a total of {sum(nums_substitutions)} substitutions."
    )


def migrate_relative_usages(
    package: str,
    usage_pattern: re.Pattern,
    new_fully_qualified_name: str,
    this_symbol_path: str,
    repo_dir: Path,
):
    """
    Relative usages: `package.ClassFoo` might be able to use `package.ClassBar` without importing it, because they're in the same package.

    This function will:
    1. Find all Java files declared under the package `package` (minus the one at `this_symbol_path`).
    2. Replace each `usage_pattern` with `new_fully_qualified_name`.

    For example, if you want to migrate usages of `com.foo.bar.MyClass` to `org.newPackage.YourClass` for all code under the package of `com.foo`, you would give:

    ```python3
    package = "com.foo",
    usage_pattern = re.compile(r'\bbar.MyClass\b'),
    new_fully_qualified_name = "org.newPackage.YourClass",
    this_symbol_path = "src/main/java/com/foo/bar/MyClass.java",
    ```

    You have to install [`ripgrep`](https://github.com/BurntSushi/ripgrep) first.
    """
    package_declaration = f"^package {package};$"
    # Find classes declared in this package.
    command = f"rg '{package_declaration}' --type java --files-with-matches {repo_dir.as_posix()}/"
    result = subprocess.run(command, text=True, shell=True, capture_output=True)
    java_paths = []
    if result.returncode == 0 and len(result.stdout) > 0:
        java_paths = result.stdout.rstrip(os.linesep).split(os.linesep)
    if len(java_paths) == 0:
        logging.debug("No file found.")
        return
    logging.debug(
        f"Trying to migrate relative usages. {len(java_paths)} files contain `{package_declaration}`."
    )
    # Replace usages of this symbol in each file.
    for java_path in java_paths:
        if java_path == this_symbol_path:
            continue
        with open(java_path) as f:
            content = f.read()
        if not usage_pattern.search(content):
            continue
        logging.debug(
            f"`{java_path.removeprefix(repo_dir.as_posix()+'/')}` uses this symbol with relative quantifier."
        )
        import_to_add = f"\nimport {new_fully_qualified_name};"
        index = content.rfind("\nimport ")
        if index > 0:
            content = content[:index] + import_to_add + content[index:]
            logging.debug(
                "Added import statement after the last existing import statement."
            )
        else:
            content, n_sub = package_declaration_pattern.subn(
                lambda m: m.group() + import_to_add, content, 1
            )
            if n_sub == 0:
                logging.warn(
                    "Failed to find a proper place to add the import statement."
                )
            else:
                logging.debug("Added import statement after the package declaration.")
        with open(java_path, "w") as f:
            f.write(content)


def migrate_usages_at_each_level(
    package: str,
    symbol: str,
    new_fully_qualified_name: str,
    this_symbol_path: str,
    repo_dir: Path,
):
    """
    For each parental level of this `symbol` (as provided in `package`), this function migrates the usage of this `symbol` to the `new_fully_qualified_name`.

    For example, if you want to migrate usages of `com.foo.bar.MyClass` to `org.newPackage.YourClass`, you will specify:

    ```python3
    package = "com.foo.bar",
    symbol = "MyClass",
    new_fully_qualified_name = "org.newPackage.YourClass",
    ```

    This function will:
    1. Look in the package `com` for usages of `foo.bar.MyClass`.
    2. Look in the package `com.foo` for usages of `bar.MyClass`.
    3. Look in the package `com.foo.bar` for usages of `MyClass`.

    Also provide:
    - `this_symbol_path`: Path to the old Java file of this `symbol` (e.g., `com.foo.bar.MyClass`).

    You have to install [`ripgrep`](https://github.com/BurntSushi/ripgrep) first.
    """
    parts = package.split(".")
    for i in range(1, len(parts) + 1):
        former_half = ".".join(parts[:i])
        latter_half = ".".join(parts[i:])

        usage = f"{latter_half}.{symbol}".lstrip(".")
        logging.debug(f"Finding `{usage}` in `{former_half}`")
        usage_pattern = re.compile(f"\\b(?<!\\.){usage}\\b")
        migrate_wildcard_imports(
            package=former_half,
            usage_pattern=usage_pattern,
            new_fully_qualified_name=new_fully_qualified_name,
            repo_dir=repo_dir,
        )
        migrate_relative_usages(
            package=former_half,
            usage_pattern=usage_pattern,
            new_fully_qualified_name=new_fully_qualified_name,
            this_symbol_path=this_symbol_path,
            repo_dir=repo_dir,
        )


def migrate(
    symbol: str,
    path: str,
    old_package: str,
    new_package: str,
    repo_dir: Path,
    pom_dependency: str,
    sed_executable: str = "sed",
):
    """
    Migrate all usages of the given `symbol` in the `old_package` (which sits at `path`) to the symbol with the same name in the `new_package`, adding `pom_dependency` to the `pom.xml` files of sub-modules if necessary.
    """
    path = os.path.join(repo_dir.as_posix(), path)
    if not os.path.isfile(path):
        logging.info(f"`{symbol}` is already migrated. Skipping.")
        return
    old_fully_qualified_name = f"{old_package}.{symbol}"
    new_fully_qualified_name = f"{new_package}.{symbol}"

    # Replace direct usages.
    migrate_direct_usages(
        old_fully_qualified_name=old_fully_qualified_name,
        new_fully_qualified_name=new_fully_qualified_name,
        repo_dir=repo_dir,
        sed_executable=sed_executable,
    )
    # Now, deal with each level.
    migrate_usages_at_each_level(
        package=old_package,
        symbol=symbol,
        new_fully_qualified_name=new_fully_qualified_name,
        this_symbol_path=path,
        repo_dir=repo_dir,
    )
    # Edit pom.xml. Add dependency on demand.
    poms_of_modules_changed = find_poms_of_modified_modules(repo_dir=repo_dir)
    poms_of_modules_changed.apply(
        ensure_file_contains,
        anchor="<dependencies>",
        content_to_ensure=pom_dependency,
    )
    # Delete the hand-written source code file of this symbol.
    os.remove(path)
