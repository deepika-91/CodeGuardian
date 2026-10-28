"""
Evidence Store and Guideline Retrieval Module for CodeGuardian (Contribution C2).
Maintains a versioned corpus of Java coding standards, static analyzer rule documentation,
and verified historical repair patterns, providing evidence-grounded context for reviews.
"""

import math
import re
from dataclasses import dataclass
from typing import Dict, List, Optional


@dataclass
class GuidelineRecord:
    rule_id: str
    tool_or_standard: str
    title: str
    explanation: str
    rationale: str
    standard_ref: str
    remediation_pattern: str


# =====================================================================
# CORPUS OF CODING GUIDELINES & ANALYZER RULES
# =====================================================================
GUIDELINE_CORPUS: List[GuidelineRecord] = [
    GuidelineRecord(
        rule_id="NoPackage",
        tool_or_standard="PMD (Code Style)",
        title="Package Declaration Requirement",
        explanation="Classes, interfaces, enums, and annotations must always belong to an explicitly named package.",
        rationale="Types defined in the default root package cannot be imported by classes within named packages, causing encapsulation failure and namespace collisions.",
        standard_ref="Java Language Specification (JLS §7.4.2) / Google Java Style §3.1",
        remediation_pattern="Declare an appropriate package statement at line 1 (e.g., `package com.example;`)."
    ),
    GuidelineRecord(
        rule_id="ShortVariable",
        tool_or_standard="PMD (Code Style)",
        title="Meaningful Variable Naming",
        explanation="Avoid variables with excessively short names (fewer than 3 characters, e.g. 'x', 'y') outside standard loop indices.",
        rationale="Descriptive identifier names convey semantic intent, reducing cognitive load during maintenance and preventing variable shadowing bugs.",
        standard_ref="Clean Code (Ch. 2: Meaningful Names) / PMD ShortVariable Rule",
        remediation_pattern="Rename variable to reflect its purpose (e.g., `firstValue`, `secondValue`, `xCoordinate`)."
    ),
    GuidelineRecord(
        rule_id="LocalVariableCouldBeFinal",
        tool_or_standard="PMD (Code Style)",
        title="Immutability & Final Local Variables",
        explanation="Local variables that are assigned once and never reassigned should be explicitly declared with the `final` keyword.",
        rationale="Marking variables final documents immutability, prevents accidental mutation downstream, and enables JVM compiler optimizations.",
        standard_ref="Effective Java (Item 17: Minimize Mutability) / PMD LocalVariableCouldBeFinal",
        remediation_pattern="Prepend the `final` keyword to the variable declaration: `final int value = ...;`."
    ),
    GuidelineRecord(
        rule_id="SystemPrintln",
        tool_or_standard="PMD (Best Practices)",
        title="Direct Standard Output / Error Usage",
        explanation="Avoid direct invocations of System.out.println() or System.err.print() in production code.",
        rationale="Standard I/O cannot be dynamically configured, filtered by severity levels (INFO/WARN/DEBUG), or redirected to centralized log aggregators.",
        standard_ref="SEI CERT Oracle Coding Standard for Java (ERR02-J) / PMD SystemPrintln",
        remediation_pattern="Replace with a structured logging framework (e.g., SLF4J `logger.info(...)`) or remove debug print statements."
    ),
    GuidelineRecord(
        rule_id="MissingJavadocTypeCheck",
        tool_or_standard="Checkstyle (Javadoc Comments)",
        title="Missing Class / Type Documentation",
        explanation="Public and package-private classes, interfaces, and enums must provide explanatory Javadoc comments.",
        rationale="Type-level Javadoc provides high-level architectural documentation and developer contracts for API consumers.",
        standard_ref="Google Java Style §7.1.1 (Javadoc: Class Comments) / Checkstyle MissingJavadocType",
        remediation_pattern="Add a `/** Represents ... */` block directly preceding the class declaration."
    ),
    GuidelineRecord(
        rule_id="MissingJavadocMethodCheck",
        tool_or_standard="Checkstyle (Javadoc Comments)",
        title="Missing Method Documentation",
        explanation="Public methods should have Javadoc comments documenting their purpose, parameters, return values, and thrown exceptions.",
        rationale="Documents the method's behavior, preconditions, parameter constraints, and postconditions.",
        standard_ref="Google Java Style §7.1.2 (Javadoc: Method Comments) / Checkstyle MissingJavadocMethod",
        remediation_pattern="Add a Javadoc block with `@param` and `@return` tags preceding the method signature."
    ),
    GuidelineRecord(
        rule_id="IndentationCheck",
        tool_or_standard="Checkstyle (Formatting)",
        title="Indentation Standards",
        explanation="Block elements, method headers, and statement lines must conform to the project's standard indentation level (typically 2 or 4 spaces).",
        rationale="Consistent indentation ensures visual scannability and prevents diff noise in collaborative version control.",
        standard_ref="Google Java Style §4.2 (Block indentation: +2 spaces) / Checkstyle Indentation",
        remediation_pattern="Re-align the statement to match the enclosing block indentation hierarchy."
    ),
    GuidelineRecord(
        rule_id="TestClassWithoutTestCases",
        tool_or_standard="PMD (Error Prone)",
        title="Test Class Lacks Test Cases",
        explanation="Classes named or structured like test cases must contain at least one valid `@Test` method.",
        rationale="Prevents dead test files or misconfigured test classes from being skipped silently during automated test suite execution.",
        standard_ref="JUnit Best Practices / PMD TestClassWithoutTestCases",
        remediation_pattern="Rename non-test classes (remove 'Test' prefix/suffix) or annotate test methods with `@Test`."
    )
]


class EvidenceStore:
    """Manages the versioned guideline corpus and performs retrieval for given analyzer findings."""

    def __init__(self, custom_guidelines: Optional[List[GuidelineRecord]] = None):
        self.corpus = custom_guidelines if custom_guidelines else GUIDELINE_CORPUS
        self.index_by_rule: Dict[str, GuidelineRecord] = {
            g.rule_id.lower(): g for g in self.corpus
        }

    def retrieve_for_finding(self, rule_id: str, message: str = "", top_k: int = 2) -> List[GuidelineRecord]:
        """Retrieves the top-k most relevant guideline records for a static finding."""
        rule_clean = rule_id.lower().strip()

        # 1. Exact match
        if rule_clean in self.index_by_rule:
            return [self.index_by_rule[rule_clean]]

        # 2. Substring match
        matches = []
        for g_rule, record in self.index_by_rule.items():
            if g_rule in rule_clean or rule_clean in g_rule:
                matches.append(record)

        if matches:
            return matches[:top_k]

        # 3. Term overlap / BM25 lexical ranking
        query_terms = set(re.findall(r'\w+', f"{rule_id} {message}".lower()))
        scored: List[tuple] = []
        for record in self.corpus:
            doc_text = f"{record.rule_id} {record.title} {record.explanation} {record.rationale}".lower()
            doc_terms = set(re.findall(r'\w+', doc_text))
            overlap = len(query_terms & doc_terms)
            if overlap > 0:
                scored.append((overlap, record))

        scored.sort(key=lambda x: x[0], reverse=True)
        results = [rec for _, rec in scored[:top_k]]
        return results if results else [self.corpus[0]]
