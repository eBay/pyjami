from pyjami.java_symbol_migration_helpers import (
    make_table,
    migrate,
    find_suitable_sed_command,
)
from pathlib import Path
import os
from shutil import copytree
from difflib import unified_diff


def test_make_table():
    search_scope = Path(
        os.path.dirname(__file__),
        "dummyJavaProject",
    )
    got = make_table(
        ("Lorem", "Ipsum", "SymbolWithNoJavaCode"),
        search_scope,
        (
            search_scope / "PreferredLocation",
            search_scope,
        ),
    ).to_dict()
    assert got == {
        "package": {0: "com.example.main.dummyJavaProject.PreferredLocation"},
        "path": {0: "PreferredLocation/Lorem.java"},
        "symbol": {0: "Lorem"},
    }


def __get_diff(
    file_relative_path, original_dummy_repo_path: Path, dummy_repo_path: Path
):
    original_lines = (
        (original_dummy_repo_path / file_relative_path).read_text().splitlines()
    )
    modified_lines = (dummy_repo_path / file_relative_path).read_text().splitlines()
    diff = unified_diff(original_lines, modified_lines, n=0)
    diff = map(lambda s: s.strip(), diff)
    return "\n".join(diff)


def test_migrate(tmp_path):
    sed_executable = find_suitable_sed_command()
    # Fixtures.
    original_dummy_repo_path = Path(os.path.dirname(__file__), "dummyJavaProject")
    dummy_repo_path = tmp_path / "dummyJavaProject"
    dummy_pom_dependency = """
        <dependency>
            <groupId>org.instance.new</groupId>
            <artifactId>dummyDestination</artifactId>
        </dependency>"""
    copytree(original_dummy_repo_path.as_posix(), dummy_repo_path.as_posix())
    # Run the test.
    original_file_path = dummy_repo_path / "Lorem.java"
    assert (
        original_file_path.is_file()
    ), "The original Java file should present before the migration is attempted."
    migrate(
        "Lorem",
        original_file_path.as_posix(),
        "com.example.main.dummyJavaProject",
        "org.instance.new.dummyDestination",
        tmp_path,
        dummy_pom_dependency,
        sed_executable=sed_executable,
    )
    assert (
        not original_file_path.is_file()
    ), "The original Java file should have been deleted."

    diff = __get_diff("UserOfLorem.java", original_dummy_repo_path, dummy_repo_path)
    assert (
        diff
        == """---
+++
@@ -2,0 +3 @@
+import org.instance.new.dummyDestination.Lorem;"""
    )

    diff = __get_diff(
        "ForeignWildcardUserOfLorem.java", original_dummy_repo_path, dummy_repo_path
    )
    assert (
        diff
        == """---
+++
@@ -7 +7 @@
-        Lorem lorem = new Lorem();
+        org.instance.new.dummyDestination.Lorem lorem = new org.instance.new.dummyDestination.Lorem();"""
    )

    diff = __get_diff(
        "ForeignUserOfLorem.java", original_dummy_repo_path, dummy_repo_path
    )
    assert (
        diff
        == """---
+++
@@ -3 +3 @@
-import com.example.main.dummyJavaProject.Lorem;
+import org.instance.new.dummyDestination.Lorem;"""
    )
