"""Local lint gate for import-hygiene issues that ruff does not catch.

RULE-LINT1's ruff selection (F401/F811/F841) has no rule for three other
CodeQL alert classes that have recurred in this repo's history (see the
`fix: resolve N CodeQL alerts` commits):

  py/import-and-import-from   -- a module imported both as `import X` and via
                                  `from X import Y` in the same file (RULE-LINT4)
  py/cyclic-import            -- two or more first-party modules whose
                                  module-level imports form a cycle
  py/unused-global-variable   -- a module-level assignment never read, either
                                  in its own file or by any other tracked file
                                  importing it (RULE-LINT6)

None of the three has a ruff equivalent (verified against `ruff rule --all`
and a `--select=ALL` probe for the first two; ruff's F841 is function-scope
only and does not look at module-level assignments at all), so all three are
checked here with plain `ast` parsing -- no CodeQL or third-party dependency
required. Runs in the RULE-CI1 pre-push hook and in CI (see
.github/workflows/ci.yml) alongside ruff.

Run directly: `python tools/check_import_lint.py`
"""
from __future__ import annotations

import ast
import re
import subprocess
import sys
from collections import deque
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent

# Packages checked for import cycles -- the three architectural layers (see
# .claude/rules/architecture.md). tools/ and tests/ are entry points that
# nothing else imports, so cycles there are not a real runtime risk.
CYCLE_PACKAGES = ["modules", "ui", "workers"]


class ImportAndImportFromViolation:
    def __init__(self, path: str, module: str, import_line: int, from_line: int):
        self.path = path
        self.module = module
        self.import_line = import_line
        self.from_line = from_line

    def __str__(self) -> str:
        return (
            f"{self.path}: '{self.module}' imported via both `import` (line "
            f"{self.import_line}) and `from ... import` (line {self.from_line})"
        )


class CyclicImportViolation:
    def __init__(self, cycle: list[str]):
        self.cycle = cycle

    def __str__(self) -> str:
        return " -> ".join([*self.cycle, self.cycle[0]])


class UnusedGlobalViolation:
    def __init__(self, path: str, name: str, lineno: int):
        self.path = path
        self.name = name
        self.lineno = lineno

    def __str__(self) -> str:
        return f"{self.path}:{self.lineno}: global '{self.name}' is never read anywhere"


def _iter_tracked_python_files() -> list[Path]:
    out = subprocess.run(
        ["git", "ls-files", "*.py"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return [REPO_ROOT / line for line in out.splitlines() if line]


# Pre-existing violations from before this gate existed are grandfathered
# here rather than fixed in bulk in the commit that adds the gate, same as
# KNOWN_LARGE_MODULES in tests/test_module_loc.py. The 46 found when this
# checker was first written (the tests/*_import() smoke-test idiom of
# `import modules.foo` + a later `from modules.foo import Bar` in the same
# file, plus 3 plugin dependency-presence checks and one ui/ local import)
# were all fixed in the same change, so this starts empty. Remove an entry
# once its file is fixed; do not add new entries here -- a new violation
# should fail the gate.
BASELINE_IMPORT_AND_IMPORT_FROM: frozenset[tuple[str, str]] = frozenset()


def find_import_and_import_from_violations(
    paths: list[Path] | None = None,
    baseline: frozenset[tuple[str, str]] = BASELINE_IMPORT_AND_IMPORT_FROM,
) -> list[ImportAndImportFromViolation]:
    violations = []
    for path in paths if paths is not None else _iter_tracked_python_files():
        try:
            tree = ast.parse(
                path.read_text(encoding="utf-8", errors="replace"), filename=str(path)
            )
        except SyntaxError:
            continue

        import_lines: dict[str, int] = {}
        from_lines: dict[str, int] = {}

        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    import_lines.setdefault(alias.name, node.lineno)
            elif isinstance(node, ast.ImportFrom):
                if node.level == 0 and node.module:
                    from_lines.setdefault(node.module, node.lineno)

        rel_path = path.relative_to(REPO_ROOT).as_posix()
        for module in sorted(set(import_lines) & set(from_lines)):
            if (rel_path, module) in baseline:
                continue
            violations.append(
                ImportAndImportFromViolation(
                    rel_path,
                    module,
                    import_lines[module],
                    from_lines[module],
                )
            )
    return violations


class _ImportCollector(ast.NodeVisitor):
    """Collects module-level (load-time) import targets only.

    Imports nested inside function/async-function bodies are deferred -- they
    run on first call, not at import time, so they cannot form a load-time
    cycle (this is the same reason the codebase uses local imports to dodge
    cycles, e.g. app.py's `--trace-windows` block). Imports inside
    `if TYPE_CHECKING:` are excluded for the same reason: they never execute
    at runtime.
    """

    def __init__(self):
        # (module_or_None, level, [imported names]) -- level 0 == absolute
        self.imports: list[tuple[str | None, int, list[str]]] = []

    def visit_FunctionDef(self, node):
        return

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_If(self, node):
        test = node.test
        if (isinstance(test, ast.Name) and test.id == "TYPE_CHECKING") or (
            isinstance(test, ast.Attribute) and test.attr == "TYPE_CHECKING"
        ):
            return
        self.generic_visit(node)

    def visit_Import(self, node):
        for alias in node.names:
            self.imports.append((alias.name, 0, []))

    def visit_ImportFrom(self, node):
        self.imports.append((node.module, node.level, [a.name for a in node.names]))


def _file_to_module(path: Path) -> str:
    parts = list(path.relative_to(REPO_ROOT).with_suffix("").parts)
    if parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _file_package_parts(path: Path) -> list[str]:
    return list(path.relative_to(REPO_ROOT).with_suffix("").parts[:-1])


def _resolve_relative(file_package_parts: list[str], module: str | None, level: int) -> str | None:
    if level - 1 > len(file_package_parts):
        return None  # would climb above the repo root -- unresolvable
    base_parts = file_package_parts[: len(file_package_parts) - (level - 1)] if level > 1 else list(file_package_parts)
    if module:
        return ".".join(base_parts + module.split("."))
    return ".".join(base_parts) if base_parts else None


def _discover_project_modules(package_roots: list[str]) -> dict[str, Path]:
    modules: dict[str, Path] = {}
    for pkg in package_roots:
        for path in (REPO_ROOT / pkg).rglob("*.py"):
            modules[_file_to_module(path)] = path
    return modules


def _build_import_graph(package_roots: list[str]) -> dict[str, set[str]]:
    modules = _discover_project_modules(package_roots)
    known = set(modules)
    graph: dict[str, set[str]] = {m: set() for m in known}

    for module_name, path in modules.items():
        try:
            tree = ast.parse(
                path.read_text(encoding="utf-8", errors="replace"), filename=str(path)
            )
        except SyntaxError:
            continue

        collector = _ImportCollector()
        collector.visit(tree)
        file_package_parts = _file_package_parts(path)

        for raw_module, level, names in collector.imports:
            base = raw_module if level == 0 else _resolve_relative(file_package_parts, raw_module, level)
            if base is None:
                continue

            targets = {f"{base}.{name}" for name in names if f"{base}.{name}" in known}
            if not targets and base in known:
                targets.add(base)

            graph[module_name].update(t for t in targets if t != module_name)

    return graph


def _tarjan_scc(graph: dict[str, set[str]]) -> list[list[str]]:
    index_counter = [0]
    stack: list[str] = []
    lowlink: dict[str, int] = {}
    index: dict[str, int] = {}
    on_stack: dict[str, bool] = {}
    result: list[list[str]] = []

    def strongconnect(node: str) -> None:
        index[node] = index_counter[0]
        lowlink[node] = index_counter[0]
        index_counter[0] += 1
        stack.append(node)
        on_stack[node] = True

        for successor in graph.get(node, ()):
            if successor not in index:
                strongconnect(successor)
                lowlink[node] = min(lowlink[node], lowlink[successor])
            elif on_stack.get(successor):
                lowlink[node] = min(lowlink[node], index[successor])

        if lowlink[node] == index[node]:
            scc = []
            while True:
                w = stack.pop()
                on_stack[w] = False
                scc.append(w)
                if w == node:
                    break
            result.append(scc)

    for node in graph:
        if node not in index:
            strongconnect(node)

    return result


def _shortest_cycle(scc_nodes: list[str], graph: dict[str, set[str]]) -> list[str]:
    """BFS for a minimal, concrete cycle within an SCC (for an actionable message).

    `parent[start]` is deliberately never overwritten: the node that closes the
    loop back to `start` is tracked separately (`closing_predecessor`), so the
    parent chain still terminates at `None` when walked back from it. Folding
    the closure into `parent[start]` instead makes the chain self-referential
    and the walk-back below never terminates.
    """
    scc_set = set(scc_nodes)
    start = scc_nodes[0]
    parent: dict[str, str | None] = {start: None}
    queue = deque([start])
    closing_predecessor: str | None = None

    while queue and closing_predecessor is None:
        node = queue.popleft()
        for nxt in graph.get(node, ()):
            if nxt not in scc_set:
                continue
            if nxt == start:
                if node != start:
                    closing_predecessor = node
                    break
                continue
            if nxt not in parent:
                parent[nxt] = node
                queue.append(nxt)

    if closing_predecessor is None:
        return list(scc_nodes)  # shouldn't happen for a genuine SCC, but stay safe

    path = []
    cur: str | None = closing_predecessor
    while cur is not None:
        path.append(cur)
        cur = parent[cur]
    path.reverse()
    return path


def find_cyclic_import_violations(
    package_roots: list[str] = CYCLE_PACKAGES,
) -> list[CyclicImportViolation]:
    graph = _build_import_graph(package_roots)
    violations = []
    for scc in _tarjan_scc(graph):
        if len(scc) < 2:
            continue
        violations.append(CyclicImportViolation(_shortest_cycle(scc, graph)))
    return violations


# Names CodeQL's py/unused-global-variable query itself treats as intentionally
# unused (see the rule's own help text): entirely underscores, containing
# "unused" (any case), the literal names "dummy"/"empty", or a dunder like
# `__all__`. Note this is narrower than ruff's default dummy-variable-rgx,
# which exempts *any* leading underscore -- see the pyproject.toml comment
# next to `dummy-variable-rgx` for the local-variable equivalent of this gap.
_UNUSED_GLOBAL_EXEMPT_RE = re.compile(r"^_+$|unused|^(dummy|empty)$|^__.*__$", re.IGNORECASE)

# Packages checked for unused globals -- same first-party layers as
# CYCLE_PACKAGES. tests/ and tools/ are excluded as *candidates* (their
# module-level constants are routinely consumed only by pytest fixture
# machinery, which is a much noisier pattern to model) but are still scanned
# as *consumers* below, since a modules/ui/workers global is often only
# referenced from a test.
UNUSED_GLOBAL_PACKAGES = CYCLE_PACKAGES

# Every entry here was independently confirmed against this repo's CodeQL
# alert history (`gh api repos/.../code-scanning/alerts` filtered to
# py/unused-global-variable): each is either already dismissed there as
# "used in tests" / "false positive" (a human previously verified the real
# reference is a string-based `monkeypatch.setattr("module.NAME", ...)` or
# similar, which no AST-based tool -- this one or CodeQL's -- can see), or
# (for the modules/device_types.py, modules/nl_query.py,
# modules/notification_router.py, modules/wifi_scanner.py entries) a
# plausible half-wired feature stub rather than clear-cut dead code, left for
# a deliberate follow-up decision rather than a silent auto-delete. Do not
# add new entries here -- a new violation should fail the gate. Remove an
# entry once its file is fixed or the name is genuinely wired up.
BASELINE_UNUSED_GLOBALS: frozenset[tuple[str, str]] = frozenset({
    ("modules/device_types.py", "TYPE_DOMAIN_CONTROLLER"),
    ("modules/device_types.py", "TYPE_FILE_NAS"),
    ("modules/device_types.py", "TYPE_MAIL_SERVER"),
    ("modules/device_types.py", "TYPE_PRINT_SERVER"),
    ("modules/device_types.py", "TYPE_WEB_SERVER"),
    ("modules/dhcp_lease_scanner.py", "_LINUX_LEASE_FILES"),
    ("modules/ha_detector.py", "HA_TYPE_LABELS"),
    ("modules/internet_exposure.py", "_RFC1918"),
    ("modules/nl_query.py", "EXAMPLE_QUERIES"),
    ("modules/notification_router.py", "SEVERITY_LEVELS"),
    ("modules/syslog_receiver.py", "_MONTHS"),
    ("modules/wifi_scanner.py", "CHANNELS_24GHZ"),
    ("modules/wifi_scanner.py", "CHANNELS_5GHZ"),
    ("ui/pages/log_source_panel.py", "_SYSLOG_SEVERITY_COLOR"),
    ("ui/pages/trend_page.py", "_SEV_BG"),
    ("ui/pages/trigger_builder_page.py", "_BUILDER_METRICS"),
    ("ui/pages/trigger_builder_page.py", "_BUILDER_OPS"),
    ("ui/styles.py", "IP_CALC_NET_BIT_BG"),
    ("ui/styles.py", "HTML_GREEN"),
    ("ui/styles.py", "HTML_RED"),
    ("ui/styles.py", "HTML_AMBER"),
    ("ui/styles.py", "HTML_MUTED"),
    ("ui/styles.py", "HTML_BG_LIGHT"),
    ("ui/styles.py", "HTML_BG_ALT"),
    ("ui/styles.py", "FONT_XS"),
    ("ui/styles.py", "FONT_SM"),
    ("ui/styles.py", "FONT_MD"),
    ("ui/styles.py", "FONT_LG"),
    ("ui/styles.py", "FONT_XL"),
    ("ui/widgets/device_detail_pane.py", "_ALL_TYPES"),
    ("ui/widgets/device_detail_pane.py", "_WINDOWS"),
})


def _module_all_exports(tree: ast.AST) -> set[str]:
    names: set[str] = set()
    for node in tree.body if isinstance(tree, ast.Module) else []:
        if isinstance(node, ast.Assign) and any(
            isinstance(t, ast.Name) and t.id == "__all__" for t in node.targets
        ):
            if isinstance(node.value, (ast.List, ast.Tuple, ast.Set)):
                for elt in node.value.elts:
                    if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                        names.add(elt.value)
    return names


def _cross_file_usage_index(
    all_paths: list[Path],
) -> tuple[set[tuple[str, str]], dict[str, set[str]]]:
    """Build (module, name) pairs seen via `from module import name`, plus a
    module -> {attrs accessed} map for `import module [as alias]; alias.attr`.
    """
    from_import_pairs: set[tuple[str, str]] = set()
    attr_access_by_module: dict[str, set[str]] = {}

    for path in all_paths:
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"), filename=str(path))
        except SyntaxError:
            continue

        fpp = _file_package_parts(path)
        aliases: dict[str, str] = {}
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom):
                base = node.module if node.level == 0 else _resolve_relative(fpp, node.module, node.level)
                if base:
                    for a in node.names:
                        from_import_pairs.add((base, a.name))
            elif isinstance(node, ast.Import):
                for a in node.names:
                    aliases[a.asname or a.name.split(".")[0]] = a.name

        for node in ast.walk(tree):
            if isinstance(node, ast.Attribute) and isinstance(node.value, ast.Name):
                mod = aliases.get(node.value.id)
                if mod:
                    attr_access_by_module.setdefault(mod, set()).add(node.attr)

    return from_import_pairs, attr_access_by_module


def find_unused_global_violations(
    package_roots: list[str] = UNUSED_GLOBAL_PACKAGES,
    baseline: frozenset[tuple[str, str]] = BASELINE_UNUSED_GLOBALS,
    candidate_paths: list[Path] | None = None,
) -> list[UnusedGlobalViolation]:
    """`candidate_paths`, when given, restricts which files are treated as
    definition sites to check (used by the baseline-staleness test to probe
    a single file); the cross-file usage index it's checked against always
    scans the full tracked-file set regardless, since usage can come from
    anywhere.
    """
    all_paths = _iter_tracked_python_files()
    from_import_pairs, attr_access_by_module = _cross_file_usage_index(all_paths)

    if candidate_paths is None:
        candidate_paths = [
            p for p in all_paths if p.relative_to(REPO_ROOT).parts[0] in package_roots
        ]

    violations = []
    for path in candidate_paths:
        try:
            tree = ast.parse(path.read_text(encoding="utf-8", errors="replace"), filename=str(path))
        except SyntaxError:
            continue

        rel_path = path.relative_to(REPO_ROOT).as_posix()
        mod_dotted = _file_to_module(path)
        exported = _module_all_exports(tree)

        module_assigns: dict[str, int] = {}
        for node in tree.body:
            target = None
            if isinstance(node, ast.Assign) and len(node.targets) == 1 and isinstance(node.targets[0], ast.Name):
                target = node.targets[0]
            elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.value is not None:
                target = node.target
            if target is not None and not _UNUSED_GLOBAL_EXEMPT_RE.search(target.id):
                module_assigns[target.id] = node.lineno

        if not module_assigns:
            continue

        read_in_file = {
            node.id for node in ast.walk(tree)
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load)
        }

        for name, lineno in module_assigns.items():
            if (rel_path, name) in baseline:
                continue
            if name in exported or name in read_in_file:
                continue
            if (mod_dotted, name) in from_import_pairs:
                continue
            if name in attr_access_by_module.get(mod_dotted, set()):
                continue
            violations.append(UnusedGlobalViolation(rel_path, name, lineno))

    return violations


def main() -> int:
    hygiene = find_import_and_import_from_violations()
    cycles = find_cyclic_import_violations()
    unused_globals = find_unused_global_violations()

    if not hygiene and not cycles and not unused_globals:
        print(
            "[check_import_lint] OK -- no import-and-import-from, cyclic-import, "
            "or unused-global-variable violations."
        )
        return 0

    if hygiene:
        print(
            f"\n{len(hygiene)} import-and-import-from violation(s) "
            "(CodeQL py/import-and-import-from, RULE-LINT4):"
        )
        for v in hygiene:
            print(f"  {v}")

    if cycles:
        print(f"\n{len(cycles)} cyclic-import violation(s) (CodeQL py/cyclic-import):")
        for v in cycles:
            print(f"  {v}")

    if unused_globals:
        print(
            f"\n{len(unused_globals)} unused-global-variable violation(s) "
            "(CodeQL py/unused-global-variable, RULE-LINT6):"
        )
        for v in unused_globals:
            print(f"  {v}")

    return 1


if __name__ == "__main__":
    sys.exit(main())
