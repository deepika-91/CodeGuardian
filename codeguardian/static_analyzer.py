"""
Static Analysis Module for CodeGuardian.
Integrates PMD and Checkstyle, normalizing tool outputs into structured finding records.
"""

import json
import os
import subprocess
import xml.etree.ElementTree as ET
from dataclasses import dataclass, asdict
from pathlib import Path
from typing import List, Optional


@dataclass
class StaticFinding:
    tool: str
    rule: str
    ruleset: str
    file: str
    line: int
    end_line: int
    column: int
    severity: str
    message: str
    url: Optional[str] = None

    def to_dict(self):
        return asdict(self)


class StaticAnalyzerManager:
    """Manages execution and output normalization for PMD and Checkstyle."""

    def __init__(self, project_root: Optional[Path] = None):
        if project_root is None:
            self.project_root = Path(__file__).resolve().parent.parent
        else:
            self.project_root = Path(project_root).resolve()

        self.pmd_bin = self.project_root / "tools" / "pmd" / "bin" / ("pmd.bat" if os.name == "nt" else "pmd")
        self.checkstyle_jar = self.project_root / "tools" / "checkstyle" / "checkstyle.jar"

    def run_pmd(self, target_file: Path) -> List[StaticFinding]:
        """Runs PMD against a Java source file and extracts findings."""
        findings = []
        target_path = Path(target_file).resolve()
        if not target_path.exists():
            return findings

        if not self.pmd_bin.exists():
            # Attempt to use system pmd if local binary not found
            pmd_cmd = "pmd"
        else:
            pmd_cmd = str(self.pmd_bin)

        cmd = [
            pmd_cmd,
            "check",
            "-d", str(target_path),
            "-R", "category/java/bestpractices.xml,category/java/errorprone.xml,category/java/codestyle.xml",
            "-f", "json"
        ]

        try:
            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=60)
            stdout = result.stdout.strip()
            if stdout:
                # Find start of json if warnings precede it
                json_start = stdout.find("{")
                if json_start != -1:
                    data = json.loads(stdout[json_start:])
                    for f in data.get("files", []):
                        for v in f.get("violations", []):
                            findings.append(StaticFinding(
                                tool="PMD",
                                rule=v.get("rule", "UnknownRule"),
                                ruleset=v.get("ruleset", "General"),
                                file=str(target_path),
                                line=int(v.get("beginline", 1)),
                                end_line=int(v.get("endline", v.get("beginline", 1))),
                                column=int(v.get("begincolumn", 1)),
                                severity=str(v.get("priority", "Medium")),
                                message=v.get("description", "").strip(),
                                url=v.get("externalInfoUrl")
                            ))
        except Exception as e:
            print(f"[PMD Warning] Could not execute PMD: {e}")

        return findings

    def run_checkstyle(self, target_file: Path, config: str = "/google_checks.xml") -> List[StaticFinding]:
        """Runs Checkstyle against a Java source file and extracts findings."""
        findings = []
        target_path = Path(target_file).resolve()
        if not target_path.exists():
            return findings

        if not self.checkstyle_jar.exists():
            return findings

        cmd = [
            "java",
            "-jar", str(self.checkstyle_jar),
            "-c", config,
            str(target_path),
            "-f", "xml"
        ]

        try:
            result = subprocess.run(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, timeout=60)
            stdout = result.stdout.strip()
            if stdout:
                root = ET.fromstring(stdout)
                for file_elem in root.findall("file"):
                    for err in file_elem.findall("error"):
                        source = err.get("source", "")
                        rule_name = source.split(".")[-1] if "." in source else source
                        findings.append(StaticFinding(
                            tool="Checkstyle",
                            rule=rule_name,
                            ruleset="Style & Formatting",
                            file=str(target_path),
                            line=int(err.get("line", 1)),
                            end_line=int(err.get("line", 1)),
                            column=int(err.get("column", 1)),
                            severity=err.get("severity", "warning"),
                            message=err.get("message", "").strip(),
                            url=f"https://checkstyle.sourceforge.io/checks/{rule_name.lower()}.html"
                        ))
        except Exception as e:
            print(f"[Checkstyle Warning] Could not execute Checkstyle: {e}")

        return findings

    def run_all(self, target_file: Path) -> List[StaticFinding]:
        """Runs both PMD and Checkstyle and returns aggregated, line-sorted findings."""
        pmd_findings = self.run_pmd(target_file)
        cs_findings = self.run_checkstyle(target_file)
        combined = pmd_findings + cs_findings
        combined.sort(key=lambda f: (f.line, f.tool))
        return combined
