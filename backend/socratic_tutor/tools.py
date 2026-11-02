"""Read-only code-exploration tools the tutor agent can call."""
import ast
import importlib
import inspect
import os
import sys
from pathlib import Path

from langchain_core.tools import tool

MAX_OUTPUT = 4000
SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__", ".mypy_cache", "site-packages"}


def _clip(text: str) -> str:
    return text if len(text) <= MAX_OUTPUT else text[:MAX_OUTPUT] + "\n...[truncated]"


def _numbered(lines: list[str], start: int) -> str:
    return "\n".join(f"{i}: {line}" for i, line in enumerate(lines, start))


def find_definitions_in_source(source: str, name: str) -> list[tuple[int, int, str]]:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    found = []
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)) and node.name == name:
            found.append((node.lineno, node.end_lineno or node.lineno, type(node).__name__))
        elif isinstance(node, ast.Assign):
            if any(isinstance(t, ast.Name) and t.id == name for t in node.targets):
                found.append((node.lineno, node.end_lineno or node.lineno, "Assign"))
    return found


def find_references_in_source(source: str, name: str) -> list[int]:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return []
    lines = {
        n.lineno
        for n in ast.walk(tree)
        if (isinstance(n, ast.Name) and n.id == name) or (isinstance(n, ast.Attribute) and n.attr == name)
    }
    return sorted(lines)


def resolve_in_root(root: str, relative: str) -> Path | None:
    """Resolve a path, refusing anything that escapes the workspace root."""
    base = Path(root).resolve()
    target = (base / relative).resolve()
    return target if target == base or base in target.parents else None


def iter_python_files(root: str):
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = [d for d in dirnames if d not in SKIP_DIRS]
        for f in filenames:
            if f.endswith(".py"):
                yield Path(dirpath) / f


def imported_roots(source: str) -> set[str]:
    try:
        tree = ast.parse(source)
    except SyntaxError:
        return set()
    roots = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(a.name.split(".")[0] for a in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module and node.level == 0:
            roots.add(node.module.split(".")[0])
    return roots


def build_tools(file_path: str, file_content: str, workspace_root: str | None, tavily_api_key: str | None = None):
    file_lines = file_content.splitlines()

    @tool
    def read_lines(start_line: int, end_line: int) -> str:
        """Read a line range (1-based, inclusive) of the file under review, with line numbers."""
        start = max(1, start_line)
        end = min(len(file_lines), end_line)
        return _clip(_numbered(file_lines[start - 1 : end], start))

    @tool
    def find_definition(name: str) -> str:
        """Find where a function, class or variable is defined in the file under review."""
        hits = find_definitions_in_source(file_content, name)
        if not hits:
            return f"No definition of '{name}' found in {file_path}."
        return "\n".join(f"{kind} '{name}' at lines {s}-{e}" for s, e, kind in hits)

    @tool
    def find_references(name: str) -> str:
        """List line numbers in the file under review where a name is used."""
        lines = find_references_in_source(file_content, name)
        return f"'{name}' used on lines: {lines}" if lines else f"No uses of '{name}' found."

    @tool
    def list_imports() -> str:
        """List the import statements of the file under review."""
        out = [f"{i}: {l}" for i, l in enumerate(file_lines, 1) if l.lstrip().startswith(("import ", "from "))]
        return "\n".join(out) or "No imports."

    @tool
    def python_docs(dotted_name: str) -> str:
        """Get the signature and docstring of an imported or standard-library object, e.g. 'json.dumps'.
        Only modules imported by the file under review or in the standard library are inspected."""
        root = dotted_name.split(".")[0]
        allowed = imported_roots(file_content) | set(sys.stdlib_module_names)
        if root not in allowed:
            return f"'{root}' is neither imported by this file nor in the standard library."
        parts = dotted_name.split(".")
        obj = None
        for i in range(len(parts), 0, -1):
            try:
                obj = importlib.import_module(".".join(parts[:i]))
                for attr in parts[i:]:
                    obj = getattr(obj, attr)
                break
            except (ImportError, AttributeError):
                obj = None
        if obj is None:
            return f"Could not resolve '{dotted_name}'."
        try:
            sig = str(inspect.signature(obj))
        except (TypeError, ValueError):
            sig = "(signature unavailable)"
        doc = inspect.getdoc(obj) or "(no docstring)"
        url = f"https://docs.python.org/3/library/{parts[0]}.html" if root in sys.stdlib_module_names else ""
        return _clip(f"{dotted_name}{sig}\n\n{doc}\n\n{url}")

    tools = [read_lines, find_definition, find_references, list_imports, python_docs]

    if workspace_root:

        @tool
        def read_workspace_file(relative_path: str, start_line: int = 1, end_line: int = 200) -> str:
            """Read lines from another file inside the workspace (path relative to the workspace root)."""
            target = resolve_in_root(workspace_root, relative_path)
            if target is None or not target.is_file():
                return "File not found inside the workspace."
            lines = target.read_text(errors="replace").splitlines()
            start = max(1, start_line)
            return _clip(_numbered(lines[start - 1 : end_line], start))

        @tool
        def search_workspace(text: str) -> str:
            """Search all Python files in the workspace for a literal string; returns path:line matches."""
            hits = []
            for path in iter_python_files(workspace_root):
                try:
                    for i, line in enumerate(path.read_text(errors="replace").splitlines(), 1):
                        if text in line:
                            hits.append(f"{path.relative_to(workspace_root)}:{i}: {line.strip()}")
                except OSError:
                    continue
                if len(hits) >= 40:
                    break
            return _clip("\n".join(hits)) or "No matches."

        tools += [read_workspace_file, search_workspace]

    if tavily_api_key:

        @tool
        def search_web_docs(query: str) -> str:
            """Search the web for official documentation or articles about a library or concept."""
            from tavily import TavilyClient

            res = TavilyClient(api_key=tavily_api_key).search(query, max_results=4)
            return _clip("\n".join(f"{r['title']} - {r['url']}\n{r['content'][:300]}" for r in res["results"]))

        tools.append(search_web_docs)

    return tools
