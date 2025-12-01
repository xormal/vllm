#!/usr/bin/env python3
"""
Report Generator

Generate compliance reports in various formats.
"""

import json
from datetime import datetime
from pathlib import Path
from typing import Dict

from jinja2 import Template


def generate_markdown_report(results: Dict, output_file: str):
    """Generate Markdown report.

    Args:
        results: Check results dictionary
        output_file: Output file path
    """
    template = """# OpenAI Responses API Compliance Report

**Date:** {{ timestamp }}
**Server:** {{ server_url }}

---

## Executive Summary

| Metric | Value |
|--------|-------|
| **Overall Compliance Score** | {{ overall_score }}% |
| **Total Tests** | {{ total_tests }} |
| **Tests Passed** | {{ tests_passed }} |
| **Tests Failed** | {{ tests_failed }} |
| **Pass Rate** | {{ pass_rate }}% |

**Status:** {% if overall_score >= 90 %}✅ **EXCELLENT**{% elif overall_score >= 70 %}⚠️ **GOOD**{% else %}❌ **NEEDS IMPROVEMENT**{% endif %}

---

## Endpoint Checks

{% if endpoints %}
| Endpoint | Status | Notes |
|----------|--------|-------|
{% for endpoint, result in endpoints.results.items() %}
| `{{ endpoint }}` | {% if result.status == 'passed' %}✅ Passed{% elif result.status == 'failed' %}❌ Failed{% elif result.status == 'skipped' %}⏭️ Skipped{% else %}⚠️ Error{% endif %} | {{ result.get('error', result.get('reason', '-')) }} |
{% endfor %}

**Summary:**
- Total: {{ endpoints.total }}
- Passed: {{ endpoints.passed }}
- Failed: {{ endpoints.failed }}
- Skipped: {{ endpoints.skipped }}
- Pass Rate: {{ endpoints.pass_rate }}%
{% else %}
*No endpoint checks performed*
{% endif %}

---

## Streaming Checks

{% if streaming %}
### Basic Streaming
- Status: {% if streaming.basic_streaming.status == 'passed' %}✅ Passed{% else %}❌ Failed{% endif %}
- Total Events: {{ streaming.basic_streaming.get('total_events', 0) }}
- Unique Event Types: {{ streaming.basic_streaming.get('unique_event_types', 0) }}

**Event Types Received:**
{% for event_type in streaming.basic_streaming.get('event_types', []) %}
- `{{ event_type }}`
{% endfor %}

{% if streaming.basic_streaming.get('missing_critical_events') %}
**⚠️ Missing Critical Events:**
{% for event in streaming.basic_streaming.missing_critical_events %}
- `{{ event }}`
{% endfor %}
{% endif %}

### Event Validation
- Status: {% if streaming.event_validation.status == 'passed' %}✅ Passed{% else %}❌ Failed{% endif %}
- Total Events: {{ streaming.event_validation.get('total_events', 0) }}
- Valid Events: {{ streaming.event_validation.get('valid_events', 0) }}
- Pass Rate: {{ streaming.event_validation.get('pass_rate', 0) }}%

### Reasoning Streaming
- Status: {% if streaming.reasoning_streaming.status == 'passed' %}✅ Passed{% elif streaming.reasoning_streaming.status == 'skipped' %}⏭️ Skipped{% else %}❌ Failed{% endif %}
- Reasoning Events: {{ streaming.reasoning_streaming.get('reasoning_events_count', 0) }}

**Summary:**
- Total Tests: {{ streaming.summary.total }}
- Passed: {{ streaming.summary.passed }}
- Failed: {{ streaming.summary.failed }}
- Pass Rate: {{ streaming.summary.pass_rate }}%
{% else %}
*No streaming checks performed*
{% endif %}

---

## Parameter Checks

{% if parameters %}
| Parameter | Status | Tests | Notes |
|-----------|--------|-------|-------|
{% for param, result in parameters.results.items() %}
| `{{ param }}` | {% if result.status == 'passed' %}✅ Passed{% elif result.status == 'failed' %}❌ Failed{% elif result.status == 'skipped' %}⏭️ Skipped{% else %}⚠️ Error{% endif %} | {{ result.get('test_count', 0) }} | {{ result.get('error', result.get('reason', '-')) }} |
{% endfor %}

**Summary:**
- Total Parameters: {{ parameters.total }}
- Tested: {{ parameters.tested }}
- Passed: {{ parameters.passed }}
- Failed: {{ parameters.failed }}
- Skipped: {{ parameters.skipped }}
- Pass Rate: {{ parameters.pass_rate }}%
{% else %}
*No parameter checks performed*
{% endif %}

---

## Recommendations

{% if overall_score < 70 %}
### High Priority
- Review failed endpoint tests
- Fix critical streaming event issues
- Validate parameter handling

{% elif overall_score < 90 %}
### Medium Priority
- Address failed tests
- Improve event coverage
- Enhance parameter validation

{% else %}
### Low Priority
- Maintain current compliance level
- Monitor for specification changes
- Consider implementing optional features

{% endif %}

---

## Detailed Results

Full results available in JSON format.

**Report Generated:** {{ timestamp }}
**Tool Version:** 1.0
"""

    # Prepare template data
    checks = results.get("checks", {})

    # Calculate overall score
    total_tests = 0
    tests_passed = 0

    if "endpoints" in checks:
        ep = checks["endpoints"]
        total_tests += ep.get("total", 0)
        tests_passed += ep.get("passed", 0)

    if "streaming" in checks:
        st = checks["streaming"].get("summary", {})
        total_tests += st.get("total", 0)
        tests_passed += st.get("passed", 0)

    if "parameters" in checks:
        pm = checks["parameters"]
        total_tests += pm.get("tested", 0)
        tests_passed += pm.get("passed", 0)

    tests_failed = total_tests - tests_passed
    pass_rate = (tests_passed / total_tests * 100) if total_tests > 0 else 0
    overall_score = pass_rate  # Simplified calculation

    data = {
        "timestamp": results.get("timestamp", datetime.now().isoformat()),
        "server_url": results.get("server_url", "N/A"),
        "overall_score": round(overall_score, 1),
        "total_tests": total_tests,
        "tests_passed": tests_passed,
        "tests_failed": tests_failed,
        "pass_rate": round(pass_rate, 1),
        "endpoints": checks.get("endpoints"),
        "streaming": checks.get("streaming"),
        "parameters": checks.get("parameters"),
    }

    # Render template
    t = Template(template)
    markdown = t.render(**data)

    # Save to file
    Path(output_file).write_text(markdown)


def generate_html_report(results: Dict, output_file: str):
    """Generate HTML report.

    Args:
        results: Check results dictionary
        output_file: Output file path
    """
    template = """<!DOCTYPE html>
<html lang="en">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>OpenAI API Compliance Report</title>
    <style>
        * {
            margin: 0;
            padding: 0;
            box-sizing: border-box;
        }

        body {
            font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, Oxygen, Ubuntu, Cantarell, sans-serif;
            line-height: 1.6;
            color: #333;
            background: #f5f5f5;
            padding: 20px;
        }

        .container {
            max-width: 1200px;
            margin: 0 auto;
            background: white;
            padding: 30px;
            border-radius: 8px;
            box-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }

        h1, h2, h3 {
            color: #2c3e50;
            margin-top: 20px;
            margin-bottom: 10px;
        }

        h1 {
            font-size: 2em;
            border-bottom: 3px solid #3498db;
            padding-bottom: 10px;
        }

        .header {
            background: linear-gradient(135deg, #667eea 0%, #764ba2 100%);
            color: white;
            padding: 20px;
            border-radius: 8px;
            margin-bottom: 30px;
        }

        .header h1 {
            color: white;
            border: none;
            margin: 0;
        }

        .meta {
            display: grid;
            grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
            gap: 15px;
            margin: 20px 0;
        }

        .meta-item {
            background: #f8f9fa;
            padding: 15px;
            border-radius: 5px;
            border-left: 4px solid #3498db;
        }

        .meta-item label {
            font-weight: bold;
            color: #666;
            display: block;
            margin-bottom: 5px;
        }

        .meta-item value {
            font-size: 1.5em;
            color: #2c3e50;
        }

        .status {
            display: inline-block;
            padding: 5px 15px;
            border-radius: 20px;
            font-weight: bold;
            margin: 10px 0;
        }

        .status.excellent {
            background: #2ecc71;
            color: white;
        }

        .status.good {
            background: #f39c12;
            color: white;
        }

        .status.poor {
            background: #e74c3c;
            color: white;
        }

        table {
            width: 100%;
            border-collapse: collapse;
            margin: 20px 0;
            background: white;
        }

        table th {
            background: #34495e;
            color: white;
            padding: 12px;
            text-align: left;
            font-weight: bold;
        }

        table td {
            padding: 10px 12px;
            border-bottom: 1px solid #ecf0f1;
        }

        table tr:hover {
            background: #f8f9fa;
        }

        .badge {
            display: inline-block;
            padding: 3px 8px;
            border-radius: 3px;
            font-size: 0.9em;
            font-weight: bold;
        }

        .badge.passed {
            background: #2ecc71;
            color: white;
        }

        .badge.failed {
            background: #e74c3c;
            color: white;
        }

        .badge.skipped {
            background: #95a5a6;
            color: white;
        }

        .badge.error {
            background: #e67e22;
            color: white;
        }

        .section {
            margin: 30px 0;
            padding: 20px;
            background: #f8f9fa;
            border-radius: 8px;
        }

        .progress-bar {
            width: 100%;
            height: 30px;
            background: #ecf0f1;
            border-radius: 15px;
            overflow: hidden;
            margin: 10px 0;
        }

        .progress-fill {
            height: 100%;
            background: linear-gradient(90deg, #2ecc71, #27ae60);
            display: flex;
            align-items: center;
            justify-content: center;
            color: white;
            font-weight: bold;
            transition: width 0.3s ease;
        }

        .footer {
            margin-top: 30px;
            padding-top: 20px;
            border-top: 1px solid #ecf0f1;
            text-align: center;
            color: #7f8c8d;
        }

        code {
            background: #f4f4f4;
            padding: 2px 6px;
            border-radius: 3px;
            font-family: "Courier New", monospace;
        }

        ul {
            margin: 10px 0;
            padding-left: 30px;
        }

        li {
            margin: 5px 0;
        }
    </style>
</head>
<body>
    <div class="container">
        <div class="header">
            <h1>OpenAI Responses API Compliance Report</h1>
            <p>{{ timestamp }}</p>
            <p>Server: {{ server_url }}</p>
        </div>

        <div class="meta">
            <div class="meta-item">
                <label>Overall Score</label>
                <value>{{ overall_score }}%</value>
            </div>
            <div class="meta-item">
                <label>Total Tests</label>
                <value>{{ total_tests }}</value>
            </div>
            <div class="meta-item">
                <label>Tests Passed</label>
                <value style="color: #2ecc71;">{{ tests_passed }}</value>
            </div>
            <div class="meta-item">
                <label>Tests Failed</label>
                <value style="color: #e74c3c;">{{ tests_failed }}</value>
            </div>
        </div>

        <div class="progress-bar">
            <div class="progress-fill" style="width: {{ overall_score }}%;">
                {{ overall_score }}%
            </div>
        </div>

        <div class="status {% if overall_score >= 90 %}excellent{% elif overall_score >= 70 %}good{% else %}poor{% endif %}">
            {% if overall_score >= 90 %}✅ EXCELLENT COMPLIANCE{% elif overall_score >= 70 %}⚠️ GOOD COMPLIANCE{% else %}❌ NEEDS IMPROVEMENT{% endif %}
        </div>

        {% if endpoints %}
        <div class="section">
            <h2>Endpoint Checks</h2>
            <table>
                <thead>
                    <tr>
                        <th>Endpoint</th>
                        <th>Status</th>
                        <th>Notes</th>
                    </tr>
                </thead>
                <tbody>
                    {% for endpoint, result in endpoints.results.items() %}
                    <tr>
                        <td><code>{{ endpoint }}</code></td>
                        <td>
                            <span class="badge {{ result.status }}">
                                {% if result.status == 'passed' %}✓ Passed
                                {% elif result.status == 'failed' %}✗ Failed
                                {% elif result.status == 'skipped' %}⊝ Skipped
                                {% else %}⚠ Error{% endif %}
                            </span>
                        </td>
                        <td>{{ result.get('error', result.get('reason', '-')) }}</td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
            <p><strong>Pass Rate:</strong> {{ endpoints.pass_rate }}% ({{ endpoints.passed }}/{{ endpoints.total - endpoints.skipped }})</p>
        </div>
        {% endif %}

        {% if streaming %}
        <div class="section">
            <h2>Streaming Checks</h2>

            <h3>Basic Streaming</h3>
            <ul>
                <li><strong>Status:</strong> <span class="badge {{ streaming.basic_streaming.status }}">{{ streaming.basic_streaming.status }}</span></li>
                <li><strong>Total Events:</strong> {{ streaming.basic_streaming.get('total_events', 0) }}</li>
                <li><strong>Unique Types:</strong> {{ streaming.basic_streaming.get('unique_event_types', 0) }}</li>
            </ul>

            {% if streaming.basic_streaming.get('missing_critical_events') %}
            <p><strong>⚠️ Missing Critical Events:</strong></p>
            <ul>
                {% for event in streaming.basic_streaming.missing_critical_events %}
                <li><code>{{ event }}</code></li>
                {% endfor %}
            </ul>
            {% endif %}

            <p><strong>Pass Rate:</strong> {{ streaming.summary.pass_rate }}% ({{ streaming.summary.passed }}/{{ streaming.summary.total }})</p>
        </div>
        {% endif %}

        {% if parameters %}
        <div class="section">
            <h2>Parameter Checks</h2>
            <table>
                <thead>
                    <tr>
                        <th>Parameter</th>
                        <th>Status</th>
                        <th>Tests</th>
                    </tr>
                </thead>
                <tbody>
                    {% for param, result in parameters.results.items() %}
                    <tr>
                        <td><code>{{ param }}</code></td>
                        <td>
                            <span class="badge {{ result.status }}">
                                {{ result.status }}
                            </span>
                        </td>
                        <td>{{ result.get('test_count', 0) }}</td>
                    </tr>
                    {% endfor %}
                </tbody>
            </table>
            <p><strong>Pass Rate:</strong> {{ parameters.pass_rate }}% ({{ parameters.passed }}/{{ parameters.tested }})</p>
        </div>
        {% endif %}

        <div class="footer">
            <p>Report generated by vLLM OpenAI API Compliance Checker v1.0</p>
            <p>{{ timestamp }}</p>
        </div>
    </div>
</body>
</html>
"""

    # Prepare data (same as markdown)
    checks = results.get("checks", {})

    total_tests = 0
    tests_passed = 0

    if "endpoints" in checks:
        ep = checks["endpoints"]
        total_tests += ep.get("total", 0) - ep.get("skipped", 0)
        tests_passed += ep.get("passed", 0)

    if "streaming" in checks:
        st = checks["streaming"].get("summary", {})
        total_tests += st.get("total", 0)
        tests_passed += st.get("passed", 0)

    if "parameters" in checks:
        pm = checks["parameters"]
        total_tests += pm.get("tested", 0)
        tests_passed += pm.get("passed", 0)

    tests_failed = total_tests - tests_passed
    pass_rate = (tests_passed / total_tests * 100) if total_tests > 0 else 0
    overall_score = pass_rate

    data = {
        "timestamp": results.get("timestamp", datetime.now().isoformat()),
        "server_url": results.get("server_url", "N/A"),
        "overall_score": round(overall_score, 1),
        "total_tests": total_tests,
        "tests_passed": tests_passed,
        "tests_failed": tests_failed,
        "pass_rate": round(pass_rate, 1),
        "endpoints": checks.get("endpoints"),
        "streaming": checks.get("streaming"),
        "parameters": checks.get("parameters"),
    }

    # Render template
    t = Template(template)
    html = t.render(**data)

    # Save to file
    Path(output_file).write_text(html)


if __name__ == "__main__":
    import sys

    if len(sys.argv) < 3:
        print("Usage: python generate_report.py <results.json> <output_file>")
        sys.exit(1)

    # Load results
    with open(sys.argv[1]) as f:
        results = json.load(f)

    output_file = sys.argv[2]

    # Determine format from extension
    if output_file.endswith(".md"):
        generate_markdown_report(results, output_file)
        print(f"✓ Generated Markdown report: {output_file}")
    elif output_file.endswith(".html"):
        generate_html_report(results, output_file)
        print(f"✓ Generated HTML report: {output_file}")
    else:
        print("Error: Output file must be .md or .html")
        sys.exit(1)
