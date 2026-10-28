#!/usr/bin/env python3
"""
CodeGuardian: Evidence-Grounded Java Code Review and Automated Repair
Using Semantic Analysis and Execution Feedback

End-to-End Pipeline Entrypoint:
1. Java Git PR / File Ingestion
2. Multi-Tool Static Analysis (PMD + Checkstyle)
3. Java Semantic Analysis (AST & Symbol Resolution - Contribution C1)
4. Finding Normalization & Evidence Retrieval (Contribution C2)
5. Evidence-Grounded LLM Reasoning & Candidate Repair (Stage 3)
6. Multi-Stage Automated Verification Sandbox (Contribution C3)
7. Tri-State Validated Review Report (HTML & Terminal Output)
"""

import argparse
import os
import sys
from pathlib import Path

# Add project root to sys.path
PROJECT_ROOT = Path(__file__).resolve().parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from codeguardian.static_analyzer import StaticAnalyzerManager
from codeguardian.semantic_analyzer import JavaSemanticAnalyzer
from codeguardian.evidence_store import EvidenceStore
from codeguardian.reasoner import EvidenceGroundedReasoner
from codeguardian.verifier import PatchVerificationSandbox
from codeguardian.reporter import HTMLReporter


def run_pipeline(
    java_file_path: Path,
    output_html: Path,
    enable_verification: bool = True
):
    print("=" * 75)
    print("CODEGUARDIAN: EVIDENCE-GROUNDED JAVA REVIEW & VERIFICATION PIPELINE")
    print("=" * 75)
    print(f"Target Source File: {java_file_path}")
    print(f"Output Report:     {output_html}")
    print()

    # Step 1: Read source code
    if not java_file_path.exists():
        print(f"ERROR: Target Java file not found at: {java_file_path}")
        sys.exit(1)

    code = java_file_path.read_text(encoding="utf-8")
    print(f"[Stage 1/6] Ingested Java code ({len(code.splitlines())} lines).")

    # Step 2: Multi-Tool Static Analysis (PMD & Checkstyle)
    print("[Stage 2/6] Running PMD and Checkstyle static analyzers...")
    analyzer_manager = StaticAnalyzerManager(PROJECT_ROOT)
    findings = analyzer_manager.run_all(java_file_path)
    print(f"            Detected {len(findings)} static violations.")
    for idx, f in enumerate(findings[:5], 1):
        print(f"            - {f.tool}:{f.rule} at line {f.line}: {f.message[:60]}...")
    if len(findings) > 5:
        print(f"            ... and {len(findings) - 5} more.")

    # Step 3: Java Semantic Analysis (AST & Symbol Resolution - C1)
    print("[Stage 3/6] Resolving AST, symbols, and scope hierarchies (JavaParser-compatible)...")
    semantic_analyzer = JavaSemanticAnalyzer(code)
    cls_names = list(semantic_analyzer.classes.keys())
    print(f"            Resolved classes: {cls_names}")
    for cname, csym in semantic_analyzer.classes.items():
        print(f"            - Class `{cname}`: {len(csym.methods)} methods, package: `{csym.package or 'default'}`")

    # Step 4: Finding Normalization & Evidence Retrieval (C2)
    print("[Stage 4/6] Retrieving evidence from coding standards & rule corpus...")
    evidence_store = EvidenceStore()
    reasoner = EvidenceGroundedReasoner(evidence_store)
    review_result = reasoner.reason(code, str(java_file_path), findings, semantic_analyzer)
    print(f"            Synthesized {len(review_result.issues)} grounded review explanations.")
    print(f"            Estimated Asymptotic Complexity: Time={review_result.time_complexity}, Space={review_result.space_complexity}")

    # Step 5: Multi-Stage Automated Verification Sandbox (C3)
    verification_result = None
    if enable_verification and review_result.candidate_patch:
        print("[Stage 5/6] Executing multi-stage verification in isolated sandbox...")
        sandbox = PatchVerificationSandbox(PROJECT_ROOT)
        verification_result = sandbox.verify_patch(
            original_file=java_file_path,
            candidate_patch=review_result.candidate_patch,
            original_findings=findings
        )
        print(f"            Verdict: {verification_result.verdict.value}")
        print(f"            Compilation: {'PASSED' if verification_result.compilation_passed else 'FAILED'}")
        print(f"            Static Reanalysis: {verification_result.resolved_violations_count} violations resolved.")
    else:
        print("[Stage 5/6] Verification sandbox skipped.")

    # Step 6: Render Interactive HTML Dashboard & CLI Summary
    print("[Stage 6/6] Generating interactive review dashboard...")
    html_content = HTMLReporter.generate_html(
        target_file=str(java_file_path),
        original_code=code,
        findings=findings,
        semantic=semantic_analyzer,
        review=review_result,
        verification=verification_result
    )
    output_html.write_text(html_content, encoding="utf-8")
    print(f"            HTML report saved to: {output_html.resolve()}")
    print()

    # Terminal Summary
    HTMLReporter.print_terminal_summary(
        target_file=str(java_file_path),
        findings=findings,
        review=review_result,
        verification=verification_result
    )


def main():
    parser = argparse.ArgumentParser(
        description="CodeGuardian: Evidence-Grounded Java Code Review and Automated Repair"
    )
    parser.add_argument(
        "--file", "-f",
        type=str,
        default="test_java/TestExample.java",
        help="Path to the Java source file to review"
    )
    parser.add_argument(
        "--output", "-o",
        type=str,
        default="code_review.html",
        help="Path to the generated HTML report file"
    )
    parser.add_argument(
        "--no-verify",
        action="store_true",
        help="Disable isolated sandbox patch verification"
    )

    args = parser.parse_args()
    target_file = Path(args.file)
    output_file = Path(args.output)
    enable_verify = not args.no_verify

    run_pipeline(target_file, output_file, enable_verification=enable_verify)


if __name__ == "__main__":
    main()