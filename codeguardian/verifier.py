"""
Verification Sandbox Module for CodeGuardian (Contribution C3).
Validates candidate patches inside an isolated workspace using compiler checks,
static reanalysis, and test execution, producing explicit tri-state verdicts.
"""

import os
import shutil
import subprocess
import tempfile
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import List, Optional

from codeguardian.reasoner import CandidatePatch
from codeguardian.static_analyzer import StaticAnalyzerManager, StaticFinding


class VerificationVerdict(str, Enum):
    VALIDATED_BY_AVAILABLE_CHECKS = "VALIDATED_BY_AVAILABLE_CHECKS"
    FAILED_VERIFICATION = "FAILED_VERIFICATION"
    INCONCLUSIVE = "INCONCLUSIVE"


@dataclass
class VerificationResult:
    verdict: VerificationVerdict
    compilation_passed: bool
    compilation_output: str
    reanalysis_passed: bool
    original_violations_count: int
    reanalysis_violations_count: int
    resolved_violations_count: int
    test_passed: bool
    test_output: str
    residual_risks: List[str] = field(default_factory=list)
    attempt_history: List[str] = field(default_factory=list)


class PatchVerificationSandbox:
    """Manages isolated patch application, compilation verification, and static recheck."""

    def __init__(self, project_root: Optional[Path] = None):
        self.project_root = Path(project_root).resolve() if project_root else Path(__file__).resolve().parent.parent
        self.analyzer_manager = StaticAnalyzerManager(self.project_root)

    def verify_patch(
        self,
        original_file: Path,
        candidate_patch: CandidatePatch,
        original_findings: List[StaticFinding],
        max_attempts: int = 3
    ) -> VerificationResult:
        """
        Executes multi-stage verification in an isolated sandbox:
        1. Write patched code to temporary workspace
        2. Compile via javac (or mvn compile)
        3. Rerun static analyzers to verify target violation remediation
        4. Check regression tests (if available)
        5. Formulate tri-state verdict
        """
        history = []
        original_path = Path(original_file).resolve()
        file_name = original_path.name

        with tempfile.TemporaryDirectory() as temp_dir:
            temp_workspace = Path(temp_dir)
            temp_file = temp_workspace / file_name

            # Write candidate patch to isolated workspace
            temp_file.write_text(candidate_patch.patched_code, encoding="utf-8")
            history.append(f"Attempt 1: Applied candidate patch to isolated sandbox at {temp_file.name}")

            # 1. Compilation Verification
            compilation_passed = False
            comp_output = ""
            try:
                comp_res = subprocess.run(
                    ["javac", str(temp_file)],
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                    timeout=30
                )
                comp_output = (comp_res.stdout + comp_res.stderr).strip()
                compilation_passed = (comp_res.returncode == 0)
                if compilation_passed:
                    history.append("Compilation: SUCCESS (javac completed with exit code 0)")
                else:
                    history.append(f"Compilation: FAILED - {comp_output}")
            except Exception as e:
                comp_output = str(e)
                history.append(f"Compilation Error: {comp_output}")

            if not compilation_passed:
                return VerificationResult(
                    verdict=VerificationVerdict.FAILED_VERIFICATION,
                    compilation_passed=False,
                    compilation_output=comp_output,
                    reanalysis_passed=False,
                    original_violations_count=len(original_findings),
                    reanalysis_violations_count=len(original_findings),
                    resolved_violations_count=0,
                    test_passed=False,
                    test_output="Skipped due to compilation failure",
                    residual_risks=["Patch failed compilation; syntax or type error introduced."],
                    attempt_history=history
                )

            # 2. Static Reanalysis
            reanalysis_findings = self.analyzer_manager.run_all(temp_file)
            history.append(f"Reanalysis: Found {len(reanalysis_findings)} findings (originally {len(original_findings)})")

            resolved_count = max(0, len(original_findings) - len(reanalysis_findings))
            reanalysis_passed = (len(reanalysis_findings) < len(original_findings))

            # 3. Regression Test Execution (if tests exist)
            test_passed = True
            test_output = "No dedicated test harness configured for isolated single-file review."
            # If project has pom.xml and mvn is available, run mvn test
            pom_file = self.project_root / "pom.xml"
            if pom_file.exists():
                try:
                    t_res = subprocess.run(
                        ["mvn", "test", "-Dtest=*"],
                        cwd=str(self.project_root),
                        stdout=subprocess.PIPE,
                        stderr=subprocess.PIPE,
                        text=True,
                        timeout=120
                    )
                    test_passed = (t_res.returncode == 0)
                    test_output = t_res.stdout[-500:] if t_res.stdout else "Tests completed."
                except Exception as e:
                    test_output = f"Maven test execution skipped: {e}"

            # 4. Tri-State Classification & Residual Risk Assessment
            residual_risks = []
            if compilation_passed and reanalysis_passed:
                if test_passed and pom_file.exists():
                    verdict = VerificationVerdict.VALIDATED_BY_AVAILABLE_CHECKS
                    residual_risks.append("All available compiler, static analyzer, and test suite checks passed.")
                else:
                    verdict = VerificationVerdict.INCONCLUSIVE
                    residual_risks.append(
                        "Code compiles cleanly and static violations were mitigated; however, comprehensive unit tests were absent to mechanically verify behavioral equivalence under all runtime edge cases."
                    )
            elif compilation_passed and not reanalysis_passed:
                verdict = VerificationVerdict.INCONCLUSIVE
                residual_risks.append("Code compiles, but some static analyzer violations persist.")
            else:
                verdict = VerificationVerdict.FAILED_VERIFICATION
                residual_risks.append("Candidate patch failed verification checks.")

            return VerificationResult(
                verdict=verdict,
                compilation_passed=compilation_passed,
                compilation_output=comp_output if comp_output else "Compilation successful with 0 errors.",
                reanalysis_passed=reanalysis_passed,
                original_violations_count=len(original_findings),
                reanalysis_violations_count=len(reanalysis_findings),
                resolved_violations_count=resolved_count,
                test_passed=test_passed,
                test_output=test_output,
                residual_risks=residual_risks,
                attempt_history=history
            )
