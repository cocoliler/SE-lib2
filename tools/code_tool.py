from __future__ import annotations

import ast
from pathlib import Path

from agent.schemas import CodeAnalysis, FunctionSignature
from tools.file_tool import read_python_files


class _FunctionVisitor(ast.NodeVisitor):
    def __init__(self) -> None:
        self.functions: list[FunctionSignature] = []
        self.classes: list[str] = []
        self.imports: list[str] = []

    def visit_FunctionDef(self, node: ast.FunctionDef) -> None:
        args = []
        for arg in node.args.args:
            arg_str = arg.arg
            if arg.annotation:
                try:
                    arg_str += f": {ast.unparse(arg.annotation)}"
                except Exception:
                    pass
            args.append(arg_str)
        if node.args.vararg:
            args.append(f"*{node.args.vararg.arg}")
        for arg in node.args.kwonlyargs:
            args.append(arg.arg)
        if node.args.kwarg:
            args.append(f"**{node.args.kwarg.arg}")

        docstring = ast.get_docstring(node)
        self.functions.append(
            FunctionSignature(
                name=node.name,
                line_start=node.lineno,
                line_end=getattr(node, "end_lineno", node.lineno),
                args=args,
                docstring=docstring,
            )
        )
        self.generic_visit(node)

    def visit_AsyncFunctionDef(self, node: ast.AsyncFunctionDef) -> None:
        self.visit_FunctionDef(node)

    def visit_ClassDef(self, node: ast.ClassDef) -> None:
        self.classes.append(node.name)
        self.generic_visit(node)

    def visit_Import(self, node: ast.Import) -> None:
        for alias in node.names:
            name = alias.name
            if alias.asname:
                name += f" as {alias.asname}"
            self.imports.append(name)

    def visit_ImportFrom(self, node: ast.ImportFrom) -> None:
        module = node.module or ""
        level = "." * (node.level or 0)
        for alias in node.names:
            name = alias.name
            if alias.asname:
                name += f" as {alias.asname}"
            self.imports.append(f"from {level}{module} import {name}")


def analyze_source(source: str, file_path: str = "<string>") -> CodeAnalysis:
    analysis = CodeAnalysis(
        file_path=file_path,
        total_lines=len(source.splitlines()),
    )

    try:
        tree = ast.parse(source, filename=file_path)
    except SyntaxError as exc:
        analysis.syntax_valid = False
        analysis.syntax_error = f"L{exc.lineno or 0}: {exc.msg}"
        return analysis

    visitor = _FunctionVisitor()
    visitor.visit(tree)
    analysis.functions = visitor.functions
    analysis.classes = visitor.classes
    analysis.imports = visitor.imports

    return analysis


def analyze_path(path: Path | str) -> list[CodeAnalysis]:
    files = read_python_files(path)
    return [analyze_source(f.content, f.path) for f in files]


def format_function_summary(analyses: list[CodeAnalysis]) -> str:
    lines: list[str] = []
    for analysis in analyses:
        lines.append(f"--- {analysis.file_path} ---")
        if not analysis.syntax_valid:
            lines.append(f"[语法错误] {analysis.syntax_error}")
            continue
        lines.append(f"总行数: {analysis.total_lines}")
        if analysis.classes:
            lines.append(f"类: {', '.join(analysis.classes)}")
        if analysis.imports:
            lines.append(f"导入数: {len(analysis.imports)}")
        if not analysis.functions:
            lines.append("(未发现顶层函数)")
        for func in analysis.functions:
            sig = f"def {func.name}({', '.join(func.args)})"
            lines.append(
                f"- L{func.line_start}-L{func.line_end} {sig}"
                + (f"  # {func.docstring.splitlines()[0]}" if func.docstring else "")
            )
    return "\n".join(lines)
