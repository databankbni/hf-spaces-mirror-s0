"""
Parser Service — AST-aware code parsing for Python, JS/TS, Java, Go.
Extracts imports, function definitions, class definitions per file.
"""
import ast
import re
from pathlib import Path
from dataclasses import dataclass, field
from utils.logger import get_logger

logger = get_logger(__name__)


@dataclass
class FunctionDef:
    name: str
    line_start: int
    line_end: int
    calls: list[str] = field(default_factory=list)   # function names called within
    complexity: int = 1                               # cyclomatic complexity estimate


@dataclass
class ClassDef:
    name: str
    line_start: int
    line_end: int
    methods: list[str] = field(default_factory=list)
    bases: list[str] = field(default_factory=list)


@dataclass
class FileAST:
    path: str
    language: str
    imports: list[str] = field(default_factory=list)      # module paths imported
    functions: list[FunctionDef] = field(default_factory=list)
    classes: list[ClassDef] = field(default_factory=list)
    line_count: int = 0
    complexity: float = 1.0
    error: str | None = None


# ── Python parser ─────────────────────────────────────────────────────────────

class _PythonVisitor(ast.NodeVisitor):
    def __init__(self):
        self.imports: list[str] = []
        self.functions: list[FunctionDef] = []
        self.classes: list[ClassDef] = []
        self._current_calls: list[str] = []

    def visit_Import(self, node):
        for alias in node.names:
            self.imports.append(alias.name)
        self.generic_visit(node)

    def visit_ImportFrom(self, node):
        module = node.module or ""
        self.imports.append(module)
        self.generic_visit(node)

    def visit_FunctionDef(self, node):
        self._current_calls = []
        self.generic_visit(node)
        complexity = 1 + sum(
            1 for n in ast.walk(node)
            if isinstance(n, (ast.If, ast.For, ast.While, ast.ExceptHandler,
                               ast.With, ast.Assert, ast.comprehension))
        )
        self.functions.append(FunctionDef(
            name=node.name,
            line_start=node.lineno,
            line_end=node.end_lineno or node.lineno,
            calls=list(set(self._current_calls)),
            complexity=complexity,
        ))

    visit_AsyncFunctionDef = visit_FunctionDef

    def visit_Call(self, node):
        if isinstance(node.func, ast.Name):
            self._current_calls.append(node.func.id)
        elif isinstance(node.func, ast.Attribute):
            self._current_calls.append(node.func.attr)
        self.generic_visit(node)

    def visit_ClassDef(self, node):
        bases = [b.id if isinstance(b, ast.Name) else "" for b in node.bases]
        methods = [
            n.name for n in ast.walk(node)
            if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))
        ]
        self.classes.append(ClassDef(
            name=node.name,
            line_start=node.lineno,
            line_end=node.end_lineno or node.lineno,
            methods=methods,
            bases=[b for b in bases if b],
        ))
        self.generic_visit(node)


def _parse_python(path: str, content: str, line_count: int) -> FileAST:
    result = FileAST(path=path, language="Python", line_count=line_count)
    try:
        tree = ast.parse(content)
        visitor = _PythonVisitor()
        visitor.visit(tree)
        result.imports = list(set(visitor.imports))
        result.functions = visitor.functions
        result.classes = visitor.classes
        if visitor.functions:
            result.complexity = sum(f.complexity for f in visitor.functions) / len(visitor.functions)
    except SyntaxError as e:
        result.error = str(e)
    return result


# ── JavaScript / TypeScript parser (regex-based) ──────────────────────────────

_JS_IMPORT_RE = re.compile(
    r"""(?:import\s+.*?\s+from\s+['"]([^'"]+)['"]|require\s*\(\s*['"]([^'"]+)['"]\s*\))"""
)
_JS_FUNC_RE = re.compile(
    r"""(?:function\s+(\w+)|(?:const|let|var)\s+(\w+)\s*=\s*(?:async\s+)?(?:\(.*?\)|[\w]+)\s*=>|(\w+)\s*:\s*(?:async\s+)?function)"""
)
_JS_CLASS_RE = re.compile(r"class\s+(\w+)(?:\s+extends\s+(\w+))?")
_JS_CALL_RE = re.compile(r"\b([a-zA-Z_$][\w$]*)\s*\(")
_JSX_COMPONENT_RE = re.compile(r"<([A-Z]\w*)[\s/>]")
_JS_KEYWORDS = frozenset({
    "if", "for", "while", "switch", "catch", "return", "function", "typeof",
    "new", "await", "async", "import", "require", "export", "super", "constructor",
    "console", "log", "warn", "error", "setTimeout", "setInterval", "parseInt",
    "parseFloat", "String", "Number", "Boolean", "Array", "Object", "Promise",
    "JSON", "Math", "Date", "Map", "Set", "Symbol", "useState", "useEffect",
    "useMemo", "useCallback", "useRef", "useContext",
})


def _parse_js(path: str, content: str, language: str, line_count: int) -> FileAST:
    result = FileAST(path=path, language=language, line_count=line_count)
    imports = []
    for m in _JS_IMPORT_RE.finditer(content):
        imp = m.group(1) or m.group(2)
        if imp:
            imports.append(imp)
    result.imports = list(set(imports))

    func_matches = [
        (m.group(1) or m.group(2) or m.group(3), m.start())
        for m in _JS_FUNC_RE.finditer(content)
    ]
    # Skip 1–2 char names: regex picks up minified helpers and loop vars
    # that only pollute the call graph
    func_matches = [(n, s) for n, s in func_matches if n and len(n) > 2]

    functions = []
    for i, (name, start) in enumerate(func_matches):
        # Approximate body: from this definition to the next one (or EOF).
        # Good enough to attribute calls without a full JS parser.
        end = func_matches[i + 1][1] if i + 1 < len(func_matches) else len(content)
        body = content[start:end]
        calls = set()
        for cm in _JS_CALL_RE.finditer(body):
            callee = cm.group(1)
            if callee != name and callee not in _JS_KEYWORDS:
                calls.add(callee)
        # JSX usage counts as a call: <Button …/> uses the Button component
        for jm in _JSX_COMPONENT_RE.finditer(body):
            if jm.group(1) != name:
                calls.add(jm.group(1))
        line_start = content[:start].count("\n") + 1
        line_end = content[:end].count("\n") + 1
        complexity = 1 + len(re.findall(r"\b(?:if|for|while|case|catch)\b|&&|\|\|", body))
        functions.append(FunctionDef(
            name=name,
            line_start=line_start,
            line_end=line_end,
            calls=sorted(calls),
            complexity=min(complexity, 50),
        ))
    result.functions = functions

    classes = []
    for m in _JS_CLASS_RE.finditer(content):
        name = m.group(1)
        base = m.group(2)
        line = content[:m.start()].count("\n") + 1
        classes.append(ClassDef(
            name=name,
            line_start=line,
            line_end=line,
            bases=[base] if base else [],
        ))
    result.classes = classes
    return result


# ── Go parser (regex-based) ───────────────────────────────────────────────────

_GO_IMPORT_RE = re.compile(r'"([^"]+)"')
_GO_FUNC_RE = re.compile(r"^func\s+(?:\([^)]+\)\s+)?(\w+)\s*\(", re.MULTILINE)


def _parse_go(path: str, content: str, line_count: int) -> FileAST:
    result = FileAST(path=path, language="Go", line_count=line_count)
    # imports section
    import_block = re.search(r"import\s*\(([^)]+)\)", content, re.DOTALL)
    if import_block:
        result.imports = [m.group(1) for m in _GO_IMPORT_RE.finditer(import_block.group(1))]
    else:
        single = re.search(r'import\s+"([^"]+)"', content)
        if single:
            result.imports = [single.group(1)]

    result.functions = [
        FunctionDef(
            name=m.group(1),
            line_start=content[:m.start()].count("\n") + 1,
            line_end=content[:m.start()].count("\n") + 1,
        )
        for m in _GO_FUNC_RE.finditer(content)
    ]
    return result


# ── Java parser (regex-based) ─────────────────────────────────────────────────

_JAVA_IMPORT_RE = re.compile(r"import\s+([\w.]+);")
_JAVA_METHOD_RE = re.compile(
    r"(?:public|private|protected|static|\s)+[\w<>\[\]]+\s+(\w+)\s*\([^)]*\)\s*(?:throws\s+\w+)?\s*\{"
)
_JAVA_CLASS_RE = re.compile(r"(?:public\s+)?class\s+(\w+)(?:\s+extends\s+(\w+))?")


def _parse_java(path: str, content: str, line_count: int) -> FileAST:
    result = FileAST(path=path, language="Java", line_count=line_count)
    result.imports = [m.group(1) for m in _JAVA_IMPORT_RE.finditer(content)]
    result.functions = [
        FunctionDef(
            name=m.group(1),
            line_start=content[:m.start()].count("\n") + 1,
            line_end=content[:m.start()].count("\n") + 1,
        )
        for m in _JAVA_METHOD_RE.finditer(content)
    ]
    result.classes = [
        ClassDef(
            name=m.group(1),
            line_start=content[:m.start()].count("\n") + 1,
            line_end=content[:m.start()].count("\n") + 1,
            bases=[m.group(2)] if m.group(2) else [],
        )
        for m in _JAVA_CLASS_RE.finditer(content)
    ]
    return result


# ── Dispatcher ────────────────────────────────────────────────────────────────

class ParserService:
    def parse(self, path: str, content: str, language: str, line_count: int) -> FileAST:
        try:
            if language == "Python":
                return _parse_python(path, content, line_count)
            elif language in ("JavaScript", "TypeScript"):
                return _parse_js(path, content, language, line_count)
            elif language == "Go":
                return _parse_go(path, content, line_count)
            elif language == "Java":
                return _parse_java(path, content, line_count)
            else:
                # Generic: no deep parsing, just return empty AST
                return FileAST(path=path, language=language, line_count=line_count)
        except Exception as e:
            logger.warning(f"Parser error for {path}: {e}")
            return FileAST(path=path, language=language, line_count=line_count, error=str(e))

    def parse_file(self, file_entry) -> FileAST:
        try:
            content = Path(file_entry.abs_path).read_text(encoding="utf-8", errors="replace")
            return self.parse(file_entry.path, content, file_entry.language, file_entry.line_count)
        except Exception as e:
            return FileAST(path=file_entry.path, language=file_entry.language,
                           line_count=0, error=str(e))


def get_parser_service() -> ParserService:
    return ParserService()
