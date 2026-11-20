import ast
import io
import tokenize
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SCAN_DIRS = ("quartz", "compat", "tools", "tests")


def _py_files():
    for d in SCAN_DIRS:
        base = ROOT / d
        if not base.exists():
            continue
        for p in base.rglob("*.py"):
            if "__pycache__" in p.parts:
                continue
            yield p


def _is_str_expr(node):
    return isinstance(node, ast.Expr) and isinstance(node.value, ast.Constant) and isinstance(node.value.value, str)


def test_no_comments_or_docstrings():
    violations = []
    for p in _py_files():
        try:
            src = p.read_text(encoding="utf-8")
        except Exception as exc:
            violations.append(f"{p}: read error {exc}")
            continue
        for tok in tokenize.generate_tokens(io.StringIO(src).readline):
            if tok.type == tokenize.COMMENT and not (tok.start[0] == 1 and tok.string.startswith("#!")):
                violations.append(f"{p}:{tok.start[0]} comment")
        for node in ast.walk(ast.parse(src)):
            for field in ("body", "orelse", "finalbody"):
                stmts = getattr(node, field, None)
                if not isinstance(stmts, list):
                    continue
                for stmt in stmts:
                    if _is_str_expr(stmt):
                        violations.append(f"{p}:{stmt.lineno} docstring")
    assert not violations, "\n".join(violations)
