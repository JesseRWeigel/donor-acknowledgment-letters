"""Prove a file's import graph does not reach a package, by parsing rather than grepping.

An independent checker is only independent if it shares no code with the thing it checks, and
`grep -L donorack` is satisfied by a file that never mentions the name and calls
`importlib.import_module("donor" + "ack")`, and is defeated by a file that mentions it only in a
comment. So this walks the graph: parse the file, collect its imports, follow the ones that
resolve to local source files, and repeat.

Usage: python3 scripts/check_imports.py <file> <forbidden-package> [...]
"""
from __future__ import annotations

import ast
import pathlib
import sys


def imports_of(path: pathlib.Path) -> set[str]:
    """Every module name this file imports, including inside functions and try blocks."""
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    found: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            found.update(a.name for a in node.names)
        elif isinstance(node, ast.ImportFrom):
            # A relative import has no module of its own to name; resolve it against the file.
            if node.level:
                base = path.parent
                for _ in range(node.level - 1):
                    base = base.parent
                prefix = ".".join(base.parts[-1:])
                found.add(f"{prefix}.{node.module}" if node.module else prefix)
            elif node.module:
                found.add(node.module)
        elif isinstance(node, ast.Call):
            # importlib.import_module("x"), and __import__("x"), both with a literal argument.
            target = node.func
            name = getattr(target, "attr", None) or getattr(target, "id", None)
            if name in ("import_module", "__import__") and node.args:
                arg = node.args[0]
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str):
                    found.add(arg.value)
                else:
                    found.add("<computed>")
    return found


def resolve(module: str, root: pathlib.Path) -> pathlib.Path | None:
    parts = module.split(".")
    for candidate in (root.joinpath(*parts).with_suffix(".py"),
                      root.joinpath(*parts, "__init__.py")):
        if candidate.is_file():
            return candidate
    return None


def show(path: pathlib.Path, root: pathlib.Path) -> str:
    """A readable name, without assuming the file sits under the working directory."""
    try:
        return str(path.relative_to(root))
    except ValueError:
        return str(path)


def main(argv):
    if len(argv) < 3:
        print(__doc__)
        return 2
    start = pathlib.Path(argv[1]).resolve()
    forbidden = set(argv[2:])
    root = pathlib.Path.cwd()

    seen: set[pathlib.Path] = set()
    queue = [start]
    reached: dict[str, str] = {}
    computed = []

    while queue:
        path = queue.pop()
        if path in seen:
            continue
        seen.add(path)
        for module in sorted(imports_of(path)):
            if module == "<computed>":
                computed.append(show(path, root))
                continue
            top = module.split(".")[0]
            if top in forbidden:
                reached[module] = show(path, root)
            nxt = resolve(module, root)
            if nxt and nxt not in seen:
                queue.append(nxt)

    if computed:
        print(f"  a dynamic import with a computed name appears in {', '.join(computed)}, so the "
              f"graph cannot be walked completely and independence cannot be proved")
        return 1
    if reached:
        for module, where in sorted(reached.items()):
            print(f"  {where} imports {module}")
        return 1

    files = ", ".join(sorted(show(p, root) for p in seen))
    print(f"  import graph of {show(start, root)} covers {len(seen)} file(s) and reaches "
          f"none of {', '.join(sorted(forbidden))}: {files}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
