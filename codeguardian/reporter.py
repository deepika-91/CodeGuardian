"""
Reporter Module for CodeGuardian.
Generates an interactive HTML dashboard and CLI summary displaying
static findings, semantic symbols, evidence-grounded reviews, candidate patches,
and verification sandbox results.
"""

import html
from pathlib import Path
from typing import List, Optional

from codeguardian.reasoner import ReviewResult
from codeguardian.semantic_analyzer import JavaSemanticAnalyzer
from codeguardian.static_analyzer import StaticFinding
from codeguardian.verifier import VerificationResult, VerificationVerdict


class HTMLReporter:
    """Renders comprehensive, responsive HTML review reports."""

    @staticmethod
    def generate_html(
        target_file: str,
        original_code: str,
        findings: List[StaticFinding],
        semantic: JavaSemanticAnalyzer,
        review: ReviewResult,
        verification: Optional[VerificationResult] = None
    ) -> str:
        safe_code = html.escape(original_code)
        safe_javadoc = html.escape(review.generated_javadocs)
        safe_diff = html.escape(review.candidate_patch.patch_diff if review.candidate_patch else "No patch generated.")
        safe_patched_code = html.escape(review.candidate_patch.patched_code if review.candidate_patch else "")

        # Format verdict badge
        if verification:
            v = verification.verdict
            if v == VerificationVerdict.VALIDATED_BY_AVAILABLE_CHECKS:
                badge_class = "badge-pass"
                verdict_title = "VALIDATED BY AVAILABLE CHECKS"
                verdict_desc = "Candidate patch cleanly compiles, mitigates targeted violations, and passes all executed verification checks."
            elif v == VerificationVerdict.INCONCLUSIVE:
                badge_class = "badge-inconclusive"
                verdict_title = "INCONCLUSIVE (RESIDUAL RISKS NOTED)"
                verdict_desc = "Code compiles and static violations were mitigated; however, comprehensive unit tests were absent to mechanically guarantee complete runtime preservation under all edge cases."
            else:
                badge_class = "badge-fail"
                verdict_title = "FAILED VERIFICATION"
                verdict_desc = "Candidate patch failed compiler or reanalysis checks."
        else:
            badge_class = "badge-neutral"
            verdict_title = "VERIFICATION PENDING"
            verdict_desc = "Verification sandbox execution was not requested."

        # Format findings rows
        findings_html = ""
        for f in findings:
            url_link = f"<a href='{f.url}' target='_blank' class='link'>Docs</a>" if f.url else "—"
            findings_html += f"""
            <tr>
                <td><span class="tool-tag tool-{f.tool.lower()}">{html.escape(f.tool)}</span></td>
                <td><strong>{html.escape(f.rule)}</strong></td>
                <td>Line {f.line}</td>
                <td><span class="sev-tag sev-{f.severity.lower()}">{html.escape(str(f.severity))}</span></td>
                <td>{html.escape(f.message)}</td>
                <td>{url_link}</td>
            </tr>
            """

        # Format semantic symbols table
        symbols_html = ""
        for line_num in range(1, len(original_code.splitlines()) + 1):
            ctx = semantic.get_context_for_line(line_num)
            if ctx.enclosing_class or ctx.active_variables or ctx.method_invocations:
                vars_str = ", ".join([f"{v.name} ({v.type_name})" for v in ctx.active_variables]) if ctx.active_variables else "None"
                calls_str = ", ".join(ctx.method_invocations) if ctx.method_invocations else "None"
                symbols_html += f"""
                <tr>
                    <td><strong>Line {line_num}</strong></td>
                    <td><code>{html.escape(ctx.line_content.strip())}</code></td>
                    <td>{html.escape(ctx.enclosing_class or '—')}</td>
                    <td>{html.escape(ctx.enclosing_method or '—')}()</td>
                    <td>{html.escape(vars_str)}</td>
                    <td>{html.escape(calls_str)}</td>
                </tr>
                """

        # Format issues breakdown
        issues_html = ""
        for idx, iss in enumerate(review.issues, 1):
            issues_html += f"""
            <div class="issue-item">
                <div class="issue-header">
                    <span class="issue-num">#{idx}</span>
                    <span class="issue-title">[{html.escape(iss.tool)}] {html.escape(iss.rule)} (Line {iss.line})</span>
                    <span class="sev-tag sev-{iss.severity.lower()}">{html.escape(iss.severity)}</span>
                </div>
                <div class="issue-body">
                    <p><strong>Root Cause:</strong> {html.escape(iss.root_cause)}</p>
                    <p><strong>Supporting Evidence:</strong> <code>{html.escape(iss.supporting_evidence)}</code></p>
                    <p><strong>Coding Standard Reference:</strong> <span class="ref-tag">{html.escape(iss.guideline_ref)}</span></p>
                    <p><strong>Remediation Action:</strong> {html.escape(iss.suggested_action)}</p>
                </div>
            </div>
            """

        # Format verification history
        history_html = ""
        if verification:
            for item in verification.attempt_history:
                history_html += f"<li>{html.escape(item)}</li>"
            risks_html = "".join([f"<li>⚠️ {html.escape(r)}</li>" for r in verification.residual_risks])
        else:
            history_html = "<li>Verification sandbox did not run.</li>"
            risks_html = "<li>None</li>"

        html_template = f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>CodeGuardian Review Report</title>
<style>
* {{ box-sizing: border-box; }}
body {{
    margin: 0; padding: 0;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Helvetica, Arial, sans-serif;
    background: #0f172a; color: #f8fafc;
    line-height: 1.6;
}}
.header {{
    background: linear-gradient(135deg, #1e1b4b, #0f172a);
    border-bottom: 1px solid #334155;
    padding: 35px 20px; text-align: center;
}}
.header h1 {{ margin: 0; font-size: 28px; color: #38bdf8; font-weight: 700; }}
.header p {{ margin: 8px 0 0; color: #94a3b8; font-size: 15px; }}

.container {{
    width: 92%; max-width: 1250px;
    margin: 30px auto; display: flex; flex-direction: column; gap: 25px;
}}

.verdict-banner {{
    padding: 22px 28px; border-radius: 12px;
    display: flex; flex-direction: column; gap: 6px;
    border: 1px solid rgba(255,255,255,0.1);
}}
.badge-pass {{ background: rgba(34, 197, 94, 0.15); border-color: #22c55e; }}
.badge-inconclusive {{ background: rgba(245, 158, 11, 0.15); border-color: #f59e0b; }}
.badge-fail {{ background: rgba(239, 68, 68, 0.15); border-color: #ef4444; }}
.badge-neutral {{ background: rgba(100, 116, 139, 0.15); border-color: #64748b; }}

.verdict-title {{ font-size: 20px; font-weight: 800; letter-spacing: 0.5px; }}
.badge-pass .verdict-title {{ color: #4ade80; }}
.badge-inconclusive .verdict-title {{ color: #fbbf24; }}
.badge-fail .verdict-title {{ color: #f87171; }}
.verdict-desc {{ font-size: 14px; color: #cbd5e1; }}

.metrics-grid {{
    display: grid; grid-template-columns: repeat(auto-fit, minmax(220px, 1fr)); gap: 15px;
}}
.metric-card {{
    background: #1e293b; border: 1px solid #334155;
    border-radius: 10px; padding: 18px; text-align: center;
}}
.metric-label {{ font-size: 13px; color: #94a3b8; text-transform: uppercase; font-weight: 600; }}
.metric-val {{ font-size: 24px; font-weight: 700; margin-top: 6px; color: #38bdf8; }}

.card {{
    background: #1e293b; border: 1px solid #334155;
    border-radius: 12px; padding: 24px;
}}
.card h2 {{
    margin-top: 0; font-size: 20px; color: #f1f5f9;
    border-bottom: 1px solid #334155; padding-bottom: 12px;
}}

pre.code-block {{
    background: #090d16; color: #e2e8f0;
    padding: 18px; border-radius: 8px; overflow-x: auto;
    font-family: "SFMono-Regular", Consolas, "Courier New", monospace;
    font-size: 13.5px; line-height: 1.5; border: 1px solid #1e293b;
}}

table {{
    width: 100%; border-collapse: collapse; margin-top: 10px; font-size: 14px;
}}
th, td {{
    padding: 12px 14px; text-align: left; border-bottom: 1px solid #334155;
}}
th {{ background: #0f172a; color: #94a3b8; font-weight: 600; }}
tr:hover {{ background: rgba(255,255,255,0.02); }}

.tool-tag {{
    display: inline-block; padding: 3px 8px; border-radius: 6px;
    font-size: 11px; font-weight: 700; text-transform: uppercase;
}}
.tool-pmd {{ background: #818cf8; color: #1e1b4b; }}
.tool-checkstyle {{ background: #38bdf8; color: #082f49; }}

.sev-tag {{
    display: inline-block; padding: 2px 8px; border-radius: 4px;
    font-size: 11px; font-weight: 600;
}}
.sev-warning, .sev-medium, .sev-3 {{ background: #ca8a04; color: #fef08a; }}
.sev-error, .sev-high, .sev-2, .sev-1 {{ background: #dc2626; color: #fecaca; }}

.link {{ color: #38bdf8; text-decoration: none; font-weight: 600; }}
.link:hover {{ text-decoration: underline; }}

.issue-item {{
    background: #0f172a; border: 1px solid #334155;
    border-radius: 8px; padding: 18px; margin-bottom: 15px;
}}
.issue-header {{
    display: flex; align-items: center; gap: 12px; margin-bottom: 10px;
}}
.issue-num {{
    background: #38bdf8; color: #082f49; padding: 2px 8px;
    border-radius: 4px; font-weight: 700; font-size: 12px;
}}
.issue-title {{ font-size: 16px; font-weight: 700; color: #f8fafc; }}
.issue-body p {{ margin: 6px 0; font-size: 14px; color: #cbd5e1; }}
.ref-tag {{ background: #1e293b; padding: 2px 8px; border-radius: 4px; color: #a5f3fc; font-size: 12px; }}

.footer {{
    text-align: center; padding: 30px; color: #64748b; font-size: 13px;
    border-top: 1px solid #1e293b; margin-top: 20px;
}}
</style>
</head>
<body>

<div class="header">
    <h1>CodeGuardian: Evidence-Grounded Java Code Review</h1>
    <p>Java AST Semantic Grounding • Guideline Evidence Retrieval • Multi-Stage Verification Sandbox</p>
</div>

<div class="container">

    <!-- VERDICT BANNER -->
    <div class="verdict-banner {badge_class}">
        <div class="verdict-title">VERDICT: {verdict_title}</div>
        <div class="verdict-desc">{verdict_desc}</div>
    </div>

    <!-- METRICS GRID -->
    <div class="metrics-grid">
        <div class="metric-card">
            <div class="metric-label">Target File</div>
            <div class="metric-val" style="font-size: 18px;">{html.escape(Path(target_file).name)}</div>
        </div>
        <div class="metric-card">
            <div class="metric-label">Static Violations</div>
            <div class="metric-val">{len(findings)}</div>
        </div>
        <div class="metric-card">
            <div class="metric-label">Time Complexity</div>
            <div class="metric-val">{html.escape(review.time_complexity)}</div>
        </div>
        <div class="metric-card">
            <div class="metric-label">Space Complexity</div>
            <div class="metric-val">{html.escape(review.space_complexity)}</div>
        </div>
    </div>

    <!-- ORIGINAL SOURCE CODE -->
    <div class="card">
        <h2>Target Source Code</h2>
        <pre class="code-block">{safe_code}</pre>
    </div>

    <!-- STATIC ANALYZER RESULTS -->
    <div class="card">
        <h2>Static Analysis Diagnostics (PMD & Checkstyle)</h2>
        <table>
            <thead>
                <tr>
                    <th>Tool</th>
                    <th>Rule</th>
                    <th>Location</th>
                    <th>Severity</th>
                    <th>Diagnostic Message</th>
                    <th>Documentation</th>
                </tr>
            </thead>
            <tbody>
                {findings_html if findings_html else '<tr><td colspan="6">No static violations detected.</td></tr>'}
            </tbody>
        </table>
    </div>

    <!-- JAVA SEMANTIC SYMBOLS (CONTRIBUTION C1) -->
    <div class="card">
        <h2>Java Semantic Symbol Context (Contribution C1)</h2>
        <p style="color: #94a3b8; font-size: 13px; margin-top: -6px;">
            AST-resolved variable types, method boundaries, and call hierarchies for grounded reasoning.
        </p>
        <table>
            <thead>
                <tr>
                    <th>Line</th>
                    <th>Statement</th>
                    <th>Class</th>
                    <th>Method</th>
                    <th>In-Scope Variables & Types</th>
                    <th>Calls</th>
                </tr>
            </thead>
            <tbody>
                {symbols_html}
            </tbody>
        </table>
    </div>

    <!-- EVIDENCE-GROUNDED REVIEW (CONTRIBUTION C2) -->
    <div class="card">
        <h2>Evidence-Grounded Review & Explanations (Contribution C2)</h2>
        {issues_html if issues_html else '<p>No actionable review issues identified.</p>'}
    </div>

    <!-- CANDIDATE PATCH (STAGE 3) -->
    <div class="card">
        <h2>Candidate Automated Repair Patch (Stage 3)</h2>
        <p><strong>Change Rationale:</strong> {html.escape(review.candidate_patch.change_rationale if review.candidate_patch else 'None')}</p>
        <p><strong>Unified Diff:</strong></p>
        <pre class="code-block">{safe_diff}</pre>
    </div>

    <!-- MULTI-STAGE VERIFICATION (CONTRIBUTION C3) -->
    <div class="card">
        <h2>Multi-Stage Sandbox Verification Results (Contribution C3)</h2>
        <p><strong>Compilation Status:</strong> <code>{html.escape(verification.compilation_output if verification else 'N/A')}</code></p>
        <p><strong>Attempt & Execution History:</strong></p>
        <ul>
            {history_html}
        </ul>
        <p><strong>Residual Risk Assessment:</strong></p>
        <ul>
            {risks_html}
        </ul>
    </div>

    <!-- AUTOMATIC JAVADOCS -->
    <div class="card">
        <h2>Synthesized JavaDoc Documentation</h2>
        <pre class="code-block">{safe_javadoc}</pre>
    </div>

</div>

<div class="footer">
    CodeGuardian • Department of Computer Science and Information Technology, Koneru Lakshmaiah Education Foundation
    <br>Supervised by Dr. Jagan Mohan Reddy Danda
</div>

</body>
</html>
"""
        return html_template

    @staticmethod
    def print_terminal_summary(
        target_file: str,
        findings: List[StaticFinding],
        review: ReviewResult,
        verification: Optional[VerificationResult] = None
    ):
        print("=" * 75)
        print("CODEGUARDIAN: EVIDENCE-GROUNDED REVIEW & VERIFICATION REPORT")
        print("=" * 75)
        print(f"File: {target_file}")
        print(f"Static Violations Detected: {len(findings)}")
        print(f"Estimated Time Complexity:  {review.time_complexity}")
        print(f"Estimated Space Complexity: {review.space_complexity}")

        if verification:
            print(f"Verification Verdict:       {verification.verdict.value}")
            print(f"Compilation Check:          {'PASSED' if verification.compilation_passed else 'FAILED'}")
            print(f"Resolved Violations:        {verification.resolved_violations_count} / {len(findings)}")
            if verification.residual_risks:
                print("Residual Risks:")
                for r in verification.residual_risks:
                    print(f"  * {r}")
        print("=" * 75)
