"""
Java Semantic Analysis Module for CodeGuardian (Contribution C1).
Performs AST extraction, symbol resolution, and surrounding scope mapping
to ground code review findings in concrete Java type and method relationships.
"""

import re
from dataclasses import dataclass, field
from typing import Dict, List, Optional, Set


@dataclass
class VariableSymbol:
    name: str
    type_name: str
    is_final: bool
    line_number: int
    scope_method: Optional[str] = None


@dataclass
class MethodSymbol:
    name: str
    return_type: str
    parameters: List[str]
    modifiers: List[str]
    start_line: int
    end_line: int
    has_javadoc: bool = False
    local_variables: List[VariableSymbol] = field(default_factory=list)


@dataclass
class ClassSymbol:
    name: str
    package: Optional[str]
    modifiers: List[str]
    start_line: int
    end_line: int
    methods: Dict[str, MethodSymbol] = field(default_factory=dict)
    fields: List[VariableSymbol] = field(default_factory=list)
    has_javadoc: bool = False


@dataclass
class SemanticLineContext:
    line_number: int
    line_content: str
    package: Optional[str]
    enclosing_class: Optional[str]
    enclosing_method: Optional[str]
    active_variables: List[VariableSymbol]
    method_invocations: List[str]
    control_structure: Optional[str]
    provenance_summary: str


class JavaSemanticAnalyzer:
    """Extracts semantic symbols, type bindings, and scope hierarchies from Java source code."""

    def __init__(self, java_code: str):
        self.code = java_code
        self.lines = java_code.splitlines()
        self.package_name: Optional[str] = None
        self.imports: List[str] = []
        self.classes: Dict[str, ClassSymbol] = {}
        self._parse()

    def _parse(self):
        """Performs structured lexical and AST extraction over Java code."""
        # 1. Package detection
        pkg_match = re.search(r'^\s*package\s+([a-zA-Z_][\w\.]*)\s*;', self.code, re.MULTILINE)
        if pkg_match:
            self.package_name = pkg_match.group(1)

        # 2. Imports detection
        for match in re.finditer(r'^\s*import\s+(?:static\s+)?([a-zA-Z_][\w\.\*]*)\s*;', self.code, re.MULTILINE):
            self.imports.append(match.group(1))

        # 3. Class detection
        class_regex = re.compile(
            r'^(\s*)((?:(?:public|protected|private|abstract|final|static)\s+)*)class\s+([A-Za-z_]\w*)'
            r'(?:\s+extends\s+([A-Za-z_]\w*))?(?:\s+implements\s+[^{]+)?\s*\{',
            re.MULTILINE
        )

        for match in class_regex.finditer(self.code):
            start_pos = match.start()
            start_line = self.code[:start_pos].count('\n') + 1
            modifiers = [m for m in match.group(2).split() if m]
            class_name = match.group(3)

            # Check if previous lines contain javadoc
            has_javadoc = False
            if start_line > 1:
                prev_lines = "\n".join(self.lines[max(0, start_line - 5):start_line - 1])
                if "*/" in prev_lines:
                    has_javadoc = True

            class_symbol = ClassSymbol(
                name=class_name,
                package=self.package_name,
                modifiers=modifiers,
                start_line=start_line,
                end_line=len(self.lines),
                has_javadoc=has_javadoc
            )
            self.classes[class_name] = class_symbol

        # 4. Method detection
        method_regex = re.compile(
            r'^(\s*)((?:(?:public|protected|private|static|final|abstract|synchronized)\s+)+)'
            r'([\w<>\[\], ?]+)\s+([A-Za-z_]\w*)\s*\(([^)]*)\)\s*(?:throws\s+[^{]+)?\s*\{',
            re.MULTILINE
        )

        for match in method_regex.finditer(self.code):
            start_pos = match.start()
            start_line = self.code[:start_pos].count('\n') + 1
            modifiers = [m for m in match.group(2).split() if m]
            return_type = match.group(3).strip()
            method_name = match.group(4)
            param_str = match.group(5).strip()

            params = [p.strip() for p in param_str.split(',') if p.strip()] if param_str else []

            # Determine end line by tracking brace balance
            brace_count = 0
            end_line = start_line
            for i in range(start_line - 1, len(self.lines)):
                line = self.lines[i]
                brace_count += line.count('{') - line.count('}')
                if brace_count == 0 and i >= start_line - 1:
                    end_line = i + 1
                    break

            has_javadoc = False
            if start_line > 1:
                prev_lines = "\n".join(self.lines[max(0, start_line - 5):start_line - 1])
                if "*/" in prev_lines:
                    has_javadoc = True

            method_symbol = MethodSymbol(
                name=method_name,
                return_type=return_type,
                parameters=params,
                modifiers=modifiers,
                start_line=start_line,
                end_line=end_line,
                has_javadoc=has_javadoc
            )

            # Assign to innermost enclosing class
            for cls in self.classes.values():
                if cls.start_line <= start_line <= cls.end_line:
                    cls.methods[method_name] = method_symbol
                    break

        # 5. Local variable declarations detection
        var_regex = re.compile(
            r'^\s*(final\s+)?([A-Z]\w*|int|long|double|float|boolean|char|byte|short|String)\s+([A-Za-z_]\w*)\s*(?:=\s*[^;]+)?\s*;',
            re.MULTILINE
        )

        for match in var_regex.finditer(self.code):
            start_pos = match.start()
            var_line = self.code[:start_pos].count('\n') + 1
            is_final = bool(match.group(1))
            var_type = match.group(2)
            var_name = match.group(3)

            # Find containing method
            found_method = None
            for cls in self.classes.values():
                for meth in cls.methods.values():
                    if meth.start_line <= var_line <= meth.end_line:
                        found_method = meth.name
                        var_sym = VariableSymbol(
                            name=var_name,
                            type_name=var_type,
                            is_final=is_final,
                            line_number=var_line,
                            scope_method=found_method
                        )
                        meth.local_variables.append(var_sym)
                        break

    def get_context_for_line(self, line_num: int) -> SemanticLineContext:
        """Resolves scope, active variables, and method calls for a specific line number."""
        line_content = self.lines[line_num - 1] if 1 <= line_num <= len(self.lines) else ""

        enclosing_class = None
        for cls in self.classes.values():
            if cls.start_line <= line_num <= cls.end_line:
                enclosing_class = cls.name
                break

        enclosing_method = None
        active_vars: List[VariableSymbol] = []
        if enclosing_class and enclosing_class in self.classes:
            for meth in self.classes[enclosing_class].methods.values():
                if meth.start_line <= line_num <= meth.end_line:
                    enclosing_method = meth.name
                    # Active variables are declared before or on this line
                    active_vars = [v for v in meth.local_variables if v.line_number <= line_num]
                    break

        # Extract method calls on this line (e.g. System.out.println)
        method_calls = re.findall(r'([A-Za-z_]\w*(?:\.[A-Za-z_]\w*)*)\s*\(', line_content)

        # Detect control structures
        control_structure = None
        stripped = line_content.strip()
        for kw in ["if", "for", "while", "switch", "try", "catch", "return"]:
            if stripped.startswith(kw):
                control_structure = kw
                break

        # Build human-readable provenance summary
        prov_parts = []
        if enclosing_class:
            prov_parts.append(f"Class: {enclosing_class}")
        if enclosing_method:
            prov_parts.append(f"Method: {enclosing_method}()")
        if active_vars:
            vars_str = ", ".join([f"{v.name}:{v.type_name}" + (" (final)" if v.is_final else "") for v in active_vars])
            prov_parts.append(f"In-scope: [{vars_str}]")
        if method_calls:
            prov_parts.append(f"Calls: {', '.join(method_calls)}")

        provenance = " | ".join(prov_parts) if prov_parts else "Global / file-level scope"

        return SemanticLineContext(
            line_number=line_num,
            line_content=line_content,
            package=self.package_name,
            enclosing_class=enclosing_class,
            enclosing_method=enclosing_method,
            active_variables=active_vars,
            method_invocations=method_calls,
            control_structure=control_structure,
            provenance_summary=provenance
        )
