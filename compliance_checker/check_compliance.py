#!/usr/bin/env python3
"""
Main Compliance Checker Script

This script runs all compliance checks against a vLLM server.
"""

import argparse
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path

import yaml
from rich.console import Console
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.table import Table

from check_endpoints import EndpointChecker
from check_parameters import ParameterChecker
from check_streaming import StreamingChecker
from utils.api_client import APIClient
from utils.spec_loader import SpecLoader

console = Console()
logger = logging.getLogger(__name__)


def setup_logging(verbose: bool = False, log_file: str = None):
    """Setup logging configuration."""
    level = logging.DEBUG if verbose else logging.INFO

    # Console handler
    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_formatter = logging.Formatter("%(levelname)s - %(message)s")
    console_handler.setFormatter(console_formatter)

    # File handler
    handlers = [console_handler]
    if log_file:
        Path(log_file).parent.mkdir(parents=True, exist_ok=True)
        file_handler = logging.FileHandler(log_file)
        file_handler.setLevel(logging.DEBUG)
        file_formatter = logging.Formatter(
            "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        )
        file_handler.setFormatter(file_formatter)
        handlers.append(file_handler)

    # Configure root logger
    logging.basicConfig(
        level=level,
        handlers=handlers,
    )


def load_config(config_file: str) -> dict:
    """Load configuration file."""
    try:
        with open(config_file, "r") as f:
            config = yaml.safe_load(f)
        logger.info(f"Loaded config from {config_file}")
        return config
    except Exception as e:
        console.print(f"[red]Error loading config: {e}[/red]")
        sys.exit(4)


def check_server_health(client: APIClient) -> bool:
    """Check if server is reachable."""
    console.print("[cyan]Checking server health...[/cyan]")

    if client.check_health():
        console.print("[green]✓ Server is reachable[/green]")
        return True
    else:
        console.print("[red]✗ Server is not reachable[/red]")
        return False


def run_compliance_checks(
    client: APIClient,
    spec: SpecLoader,
    endpoints_only: bool = False,
    streaming_only: bool = False,
    parameters_only: bool = False,
) -> dict:
    """Run all compliance checks.

    Args:
        client: API client instance
        spec: Spec loader instance
        endpoints_only: Only run endpoint checks
        streaming_only: Only run streaming checks
        parameters_only: Only run parameter checks

    Returns:
        Dictionary with all results
    """
    results = {
        "timestamp": datetime.now().isoformat(),
        "server_url": client.base_url,
        "checks": {},
    }

    # Determine which checks to run
    run_all = not (endpoints_only or streaming_only or parameters_only)

    # Endpoint checks
    if run_all or endpoints_only:
        console.print("\n[bold cyan]═══ Endpoint Checks ═══[/bold cyan]\n")
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Running endpoint checks...", total=None)
            endpoint_checker = EndpointChecker(client, spec)
            results["checks"]["endpoints"] = endpoint_checker.check_all_endpoints()
            progress.update(task, completed=True)

    # Streaming checks
    if run_all or streaming_only:
        console.print("\n[bold cyan]═══ Streaming Checks ═══[/bold cyan]\n")
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Running streaming checks...", total=None)
            streaming_checker = StreamingChecker(client, spec)
            results["checks"]["streaming"] = streaming_checker.check_streaming()
            progress.update(task, completed=True)

    # Parameter checks
    if run_all or parameters_only:
        console.print("\n[bold cyan]═══ Parameter Checks ═══[/bold cyan]\n")
        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            task = progress.add_task("Running parameter checks...", total=None)
            parameter_checker = ParameterChecker(client, spec)
            results["checks"]["parameters"] = parameter_checker.check_all_parameters()
            progress.update(task, completed=True)

    return results


def calculate_overall_score(results: dict) -> dict:
    """Calculate overall compliance score.

    Args:
        results: Check results dictionary

    Returns:
        Summary dictionary with scores
    """
    checks = results.get("checks", {})

    scores = {}
    weights = {
        "endpoints": 0.4,
        "streaming": 0.4,
        "parameters": 0.2,
    }

    total_score = 0
    total_weight = 0

    for check_name, weight in weights.items():
        if check_name in checks:
            check_data = checks[check_name]

            # Get pass rate
            if check_name == "endpoints":
                pass_rate = check_data.get("pass_rate", 0)
            elif check_name == "streaming":
                pass_rate = check_data.get("summary", {}).get("pass_rate", 0)
            elif check_name == "parameters":
                pass_rate = check_data.get("pass_rate", 0)
            else:
                pass_rate = 0

            scores[check_name] = pass_rate
            total_score += pass_rate * weight
            total_weight += weight

    overall_score = total_score / total_weight if total_weight > 0 else 0

    return {
        "overall": round(overall_score, 2),
        "breakdown": scores,
    }


def print_summary(results: dict, spec: SpecLoader):
    """Print summary table."""
    console.print("\n[bold cyan]═══ Compliance Summary ═══[/bold cyan]\n")

    # Calculate scores
    scores = calculate_overall_score(results)

    # Create summary table
    table = Table(title="Test Results", show_header=True, header_style="bold magenta")
    table.add_column("Category", style="cyan", no_wrap=True)
    table.add_column("Total", justify="right")
    table.add_column("Passed", justify="right", style="green")
    table.add_column("Failed", justify="right", style="red")
    table.add_column("Pass Rate", justify="right")

    checks = results.get("checks", {})

    # Endpoint results
    if "endpoints" in checks:
        ep = checks["endpoints"]
        table.add_row(
            "Endpoints",
            str(ep.get("total", 0)),
            str(ep.get("passed", 0)),
            str(ep.get("failed", 0)),
            f"{ep.get('pass_rate', 0):.1f}%",
        )

    # Streaming results
    if "streaming" in checks:
        st = checks["streaming"].get("summary", {})
        table.add_row(
            "Streaming",
            str(st.get("total", 0)),
            str(st.get("passed", 0)),
            str(st.get("failed", 0)),
            f"{st.get('pass_rate', 0):.1f}%",
        )

    # Parameter results
    if "parameters" in checks:
        pm = checks["parameters"]
        table.add_row(
            "Parameters",
            str(pm.get("tested", 0)),
            str(pm.get("passed", 0)),
            str(pm.get("failed", 0)),
            f"{pm.get('pass_rate', 0):.1f}%",
        )

    console.print(table)

    # Overall score
    overall = scores["overall"]
    spec_score = spec.get_overall_compliance_score()

    console.print(f"\n[bold]Overall Compliance Score:[/bold] {overall:.1f}%")
    console.print(f"[bold]Spec Mapping Score:[/bold] {spec_score}%")

    # Status
    if overall >= 90:
        console.print("\n[bold green]✓ EXCELLENT COMPLIANCE[/bold green]")
    elif overall >= 70:
        console.print("\n[bold yellow]⚠ GOOD COMPLIANCE[/bold yellow]")
    else:
        console.print("\n[bold red]✗ NEEDS IMPROVEMENT[/bold red]")


def save_results(results: dict, output_dir: str, formats: list):
    """Save results to files.

    Args:
        results: Results dictionary
        output_dir: Output directory path
        formats: List of formats to save (json, markdown, html)
    """
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)

    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    date = datetime.now().strftime("%Y-%m-%d")

    # Save JSON
    if "json" in formats:
        json_file = output_path / f"compliance_report_{timestamp}.json"
        with open(json_file, "w") as f:
            json.dump(results, f, indent=2)
        console.print(f"[green]✓ Saved JSON report: {json_file}[/green]")

    # Save Markdown (imported from generate_report.py)
    if "markdown" in formats:
        from generate_report import generate_markdown_report

        md_file = output_path / f"compliance_report_{date}.md"
        generate_markdown_report(results, str(md_file))
        console.print(f"[green]✓ Saved Markdown report: {md_file}[/green]")

    # Save HTML
    if "html" in formats:
        from generate_report import generate_html_report

        html_file = output_path / f"compliance_report_{date}.html"
        generate_html_report(results, str(html_file))
        console.print(f"[green]✓ Saved HTML report: {html_file}[/green]")


def main():
    """Main entry point."""
    parser = argparse.ArgumentParser(
        description="OpenAI Responses API Compliance Checker",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )

    parser.add_argument(
        "--config",
        default="config.yaml",
        help="Path to configuration file (default: config.yaml)",
    )

    parser.add_argument(
        "--endpoints-only",
        action="store_true",
        help="Only run endpoint checks",
    )

    parser.add_argument(
        "--streaming-only",
        action="store_true",
        help="Only run streaming checks",
    )

    parser.add_argument(
        "--parameters-only",
        action="store_true",
        help="Only run parameter checks",
    )

    parser.add_argument(
        "--verbose",
        "-v",
        action="store_true",
        help="Enable verbose logging",
    )

    parser.add_argument(
        "--output",
        "-o",
        help="Output directory for reports (overrides config)",
    )

    parser.add_argument(
        "--format",
        choices=["json", "markdown", "html"],
        action="append",
        help="Output format (can specify multiple)",
    )

    parser.add_argument(
        "--fail-fast",
        action="store_true",
        help="Exit on first failure",
    )

    parser.add_argument(
        "--critical-only",
        action="store_true",
        help="Only check critical endpoints/events",
    )

    args = parser.parse_args()

    # Load config
    config = load_config(args.config)

    # Setup logging
    log_file = config.get("logging", {}).get("file", "logs/compliance.log")
    setup_logging(args.verbose, log_file)

    console.print("[bold cyan]OpenAI Responses API Compliance Checker[/bold cyan]")
    console.print(f"Version: 1.0")
    console.print(f"Config: {args.config}\n")

    # Initialize API client
    server_config = config["server"]
    auth_config = config.get("auth", {})

    api_key = None
    if auth_config.get("enabled"):
        api_key = auth_config.get("api_key") or os.environ.get("OPENAI_API_KEY")

    client = APIClient(
        base_url=server_config["base_url"],
        api_version=server_config.get("api_version", "v1"),
        timeout=server_config.get("timeout", 30),
        api_key=api_key,
        verify_ssl=server_config.get("verify_ssl", False),
    )

    # Check server health
    if not check_server_health(client):
        console.print("[red]Server is not reachable. Exiting.[/red]")
        sys.exit(3)

    # Load spec
    try:
        spec_file = config["compliance"]["spec_mapping"]
        spec = SpecLoader(spec_file)
    except Exception as e:
        console.print(f"[red]Error loading spec: {e}[/red]")
        sys.exit(4)

    # Run checks
    try:
        results = run_compliance_checks(
            client,
            spec,
            endpoints_only=args.endpoints_only,
            streaming_only=args.streaming_only,
            parameters_only=args.parameters_only,
        )

        # Print summary
        print_summary(results, spec)

        # Save results
        output_dir = args.output or config["reporting"]["output_dir"]
        formats = args.format or config["reporting"]["formats"]
        save_results(results, output_dir, formats)

        # Calculate overall score
        scores = calculate_overall_score(results)
        overall_score = scores["overall"]

        # Check thresholds
        thresholds = config["compliance"]["thresholds"]
        if overall_score < thresholds["overall"]:
            console.print(f"\n[red]✗ Compliance below threshold ({thresholds['overall']}%)[/red]")
            sys.exit(1)
        else:
            console.print(f"\n[green]✓ Compliance above threshold ({thresholds['overall']}%)[/green]")
            sys.exit(0)

    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted by user[/yellow]")
        sys.exit(130)
    except Exception as e:
        console.print(f"\n[red]Error: {e}[/red]")
        logger.exception("Compliance check failed")
        sys.exit(1)
    finally:
        client.close()


if __name__ == "__main__":
    main()
