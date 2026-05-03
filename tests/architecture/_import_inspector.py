"""Shared helper for parsing Python imports via the ast module.

Used by the architecture fitness function tests. Parses each
Python module under src/app/ once, extracts its imports, and
returns them as structured data the tests can assert against.
"""

from __future__ import annotations

import ast
from dataclasses import dataclass
from pathlib import Path

# Project root assumed to be the parent of tests/.
_PROJECT_ROOT = Path(__file__).resolve().parents[2]
_SRC_ROOT = _PROJECT_ROOT / "src" / "app"


@dataclass(frozen=True)
class ImportRecord:
    """One `from X import Y` statement extracted from a module.

    Attributes:
        source_module: Dotted module path of the file doing the import.
            Example: 'app.intake.invoice_tool'.
        imported_module: Dotted module path being imported from.
            Example: 'app.core.entities'. None for plain `import X`
            statements (which are rare in this codebase).
        imported_names: Names being imported. Example: ('Invoice',
            'PORecord'). Empty tuple for star imports.
        line_number: Line in the source file. Useful for failure
            messages.
    """

    source_module: str
    imported_module: str | None
    imported_names: tuple[str, ...]
    line_number: int


def discover_app_modules() -> list[Path]:
    """Return every Python file under src/app/ as a Path.

    Excludes __pycache__ directories. Includes __init__.py files
    even when empty (their imports still count).
    """
    return sorted(path for path in _SRC_ROOT.rglob("*.py") if "__pycache__" not in path.parts)


def module_path_from_file(file_path: Path) -> str:
    """Convert a file path under src/app/ to a dotted module path.

    Example:
        src/app/intake/invoice_tool.py -> 'app.intake.invoice_tool'
        src/app/core/__init__.py       -> 'app.core'

    Args:
        file_path: Path to a .py file under src/.

    Returns:
        Dotted module path string.
    """
    relative = file_path.relative_to(_PROJECT_ROOT / "src")
    parts = list(relative.with_suffix("").parts)
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def parse_imports(file_path: Path) -> list[ImportRecord]:
    """Parse one Python file and return all its `from X import Y` records.

    Plain `import X` statements are returned with imported_names
    containing the bound name and imported_module=None.

    Args:
        file_path: Path to the .py file to parse.

    Returns:
        List of ImportRecord, one per import statement.

    Raises:
        SyntaxError: If the file is not valid Python.
    """
    source_module = module_path_from_file(file_path)
    source_text = file_path.read_text(encoding="utf-8")
    tree = ast.parse(source_text, filename=str(file_path))

    records: list[ImportRecord] = []
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            records.append(
                ImportRecord(
                    source_module=source_module,
                    imported_module=node.module,
                    imported_names=tuple(alias.name for alias in node.names),
                    line_number=node.lineno,
                )
            )
        elif isinstance(node, ast.Import):
            for alias in node.names:
                records.append(
                    ImportRecord(
                        source_module=source_module,
                        imported_module=None,
                        imported_names=(alias.name,),
                        line_number=node.lineno,
                    )
                )
    return records


def all_app_imports() -> list[ImportRecord]:
    """Parse every module under src/app/ and return a flat list.

    Returns:
        Every ImportRecord from every module under src/app/.
    """
    records: list[ImportRecord] = []
    for path in discover_app_modules():
        records.extend(parse_imports(path))
    return records
