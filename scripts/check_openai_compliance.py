#!/usr/bin/env python3
"""
Lightweight compliance checker that validates SPEC_TO_CODE_MAPPING.json.

This script mirrors the reference implementation outlined in
COMPLIANCE_TRACKING_PLAN.md and is safe to run in CI because it does not
require a running vLLM server.
"""

from __future__ import annotations

import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class ComplianceChecker:
    def __init__(self, mapping_file: str = "SPEC_TO_CODE_MAPPING.json") -> None:
        self.mapping_path = Path(mapping_file)
        if not self.mapping_path.exists():
            raise FileNotFoundError(
                f"SPEC mapping file not found: {self.mapping_path}"
            )
        self.mapping: dict[str, Any] = json.loads(self.mapping_path.read_text())

    def check_endpoints(self) -> dict[str, Any]:
        results = {
            "total": 0,
            "implemented": 0,
            "missing": 0,
            "partial": 0,
            "issues": [],
        }
        endpoints = self.mapping["endpoints"]
        for name, info in endpoints.items():
            results["total"] += 1
            implemented = info.get("implemented", False)
            status = info.get("status")
            if implemented or status == "implemented":
                results["implemented"] += 1
                # verify referenced file exists
                loc = info.get("code_location", {})
                code_file = loc.get("file")
                if code_file and not Path(code_file).exists():
                    results["issues"].append(
                        f"{name}: referenced file missing ({code_file})"
                    )
            elif status == "partially_implemented":
                results["partial"] += 1
            else:
                results["missing"] += 1
        return results

    def check_request_parameters(self) -> dict[str, Any]:
        params = self.mapping["request_parameters"]["ResponsesRequest"]
        results = {
            "total": len(params),
            "implemented": 0,
            "missing": 0,
            "type_mismatches": [],
        }
        for name, info in params.items():
            implemented = info.get("implemented")
            status = info.get("status")
            if implemented is True or status == "implemented":
                results["implemented"] += 1
                if not info.get("type_match", True):
                    results["type_mismatches"].append(name)
            else:
                results["missing"] += 1
        return results

    def check_streaming_events(self) -> dict[str, Any]:
        events = self.mapping["streaming_events"]
        results = {
            "total": len(events),
            "implemented": 0,
            "missing": 0,
            "high_priority_missing": [],
            "average_compliance": 0.0,
        }
        total_score = 0
        for name, info in events.items():
            implemented = info.get("implemented")
            if implemented:
                results["implemented"] += 1
            else:
                results["missing"] += 1
                priority = info.get("priority") or info.get("test_priority")
                if str(priority).lower() == "high" or str(priority).lower() == "critical":
                    results["high_priority_missing"].append(name)
            total_score += info.get("compliance_score", 0)
        if results["total"]:
            results["average_compliance"] = total_score / results["total"]
        return results

    def generate_report(self) -> str:
        """Render a Markdown compliance report."""
        timestamp = datetime.now(timezone.utc).isoformat()
        ep = self.check_endpoints()
        params = self.check_request_parameters()
        events = self.check_streaming_events()
        report = [
            "# OpenAI Responses API Compliance Report",
            f"Date: {timestamp}",
            "",
            "## Endpoints",
            f"- Total: {ep['total']}",
            f"- Implemented: {ep['implemented']}",
            f"- Missing: {ep['missing']}",
            f"- Partial: {ep['partial']}",
        ]
        if ep["issues"]:
            report.append("\n### Issues:")
            report.extend(f"- {issue}" for issue in ep["issues"])

        report.append("\n## Request Parameters")
        report.append(f"- Total: {params['total']}")
        report.append(f"- Implemented: {params['implemented']}")
        report.append(f"- Missing: {params['missing']}")
        if params["type_mismatches"]:
            report.append(
                "- Type mismatches: " + ", ".join(params["type_mismatches"])
            )

        report.append("\n## Streaming Events")
        report.append(f"- Total: {events['total']}")
        report.append(f"- Implemented: {events['implemented']}")
        report.append(f"- Missing: {events['missing']}")
        report.append(
            f"- Average compliance: {events['average_compliance']:.1f}%"
        )
        if events["high_priority_missing"]:
            report.append("\n### High Priority Missing:")
            report.extend(
                f"- {event}" for event in events["high_priority_missing"]
            )

        return "\n".join(report)

    def run(self) -> None:
        report_text = self.generate_report()
        output_dir = Path("compliance_reports")
        output_dir.mkdir(exist_ok=True)
        report_path = output_dir / f"report_{datetime.now(timezone.utc).date()}.md"
        report_path.write_text(report_text)
        print(report_text)

        # Exit with failure if critical items missing
        events = self.check_streaming_events()
        if events["high_priority_missing"]:
            print(
                "\nCritical streaming events missing: "
                + ", ".join(events["high_priority_missing"])
            )
            sys.exit(1)


def main() -> None:
    checker = ComplianceChecker()
    checker.run()


if __name__ == "__main__":
    main()
