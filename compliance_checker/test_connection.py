#!/usr/bin/env python3
"""
Quick test script to verify server connection and basic functionality.
"""

import sys
import yaml
from pathlib import Path

# Add utils to path
sys.path.insert(0, str(Path(__file__).parent))

from utils.api_client import APIClient
from rich.console import Console

console = Console()


def test_connection():
    """Test basic connection to vLLM server."""
    console.print("[bold cyan]Testing Connection to vLLM Server[/bold cyan]\n")

    # Load config
    try:
        with open("config.yaml", "r") as f:
            config = yaml.safe_load(f)
    except Exception as e:
        console.print(f"[red]✗ Failed to load config: {e}[/red]")
        return False

    server_config = config["server"]
    base_url = server_config["base_url"]

    console.print(f"Server URL: [cyan]{base_url}[/cyan]")

    # Initialize client
    client = APIClient(
        base_url=base_url,
        api_version=server_config.get("api_version", "v1"),
        timeout=server_config.get("timeout", 30),
        verify_ssl=server_config.get("verify_ssl", False),
    )

    # Test 1: Health check
    console.print("\n[yellow]Test 1: Health Check[/yellow]")
    try:
        if client.check_health():
            console.print("[green]✓ Server is reachable[/green]")
        else:
            console.print("[red]✗ Server health check failed[/red]")
            return False
    except Exception as e:
        console.print(f"[red]✗ Connection error: {e}[/red]")
        return False

    # Test 2: Models endpoint
    console.print("\n[yellow]Test 2: Models Endpoint[/yellow]")
    try:
        response = client.get("/v1/models")
        if response.status_code == 200:
            models_data = response.json()
            models = models_data.get("data", [])
            console.print(f"[green]✓ Models endpoint working ({len(models)} models available)[/green]")
            if models:
                console.print(f"  First model: [cyan]{models[0].get('id', 'unknown')}[/cyan]")
        else:
            console.print(f"[yellow]⚠ Models endpoint returned {response.status_code}[/yellow]")
    except Exception as e:
        console.print(f"[red]✗ Models endpoint error: {e}[/red]")

    # Test 3: Create response (basic)
    console.print("\n[yellow]Test 3: Create Response[/yellow]")
    try:
        data = {
            "model": config["testing"]["test_model"],
            "input": "Hello",
            "max_output_tokens": 10,
        }
        response = client.post("/v1/responses", data=data)
        if response.status_code == 200:
            response_data = response.json()
            console.print(f"[green]✓ Response created successfully[/green]")
            console.print(f"  Response ID: [cyan]{response_data.get('id', 'unknown')}[/cyan]")
            console.print(f"  Status: [cyan]{response_data.get('status', 'unknown')}[/cyan]")
        else:
            console.print(f"[yellow]⚠ Response creation returned {response.status_code}[/yellow]")
            console.print(f"  {response.text[:200]}")
    except Exception as e:
        console.print(f"[red]✗ Response creation error: {e}[/red]")

    # Test 4: Streaming
    console.print("\n[yellow]Test 4: Streaming[/yellow]")
    try:
        data = {
            "model": config["testing"]["test_model"],
            "input": "Count to 3",
            "max_output_tokens": 20,
            "stream": True,
        }

        event_count = 0
        event_types = set()

        for event in client.stream_sse("/v1/responses", data, timeout=30):
            event_count += 1
            event_type = event.get("type")
            if event_type:
                event_types.add(event_type)

            if event_count >= 5:  # Just test first few events
                break

        if event_count > 0:
            console.print(f"[green]✓ Streaming working ({event_count}+ events received)[/green]")
            console.print(f"  Event types: [cyan]{', '.join(list(event_types)[:3])}...[/cyan]")
        else:
            console.print("[yellow]⚠ No streaming events received[/yellow]")
    except Exception as e:
        console.print(f"[red]✗ Streaming error: {e}[/red]")

    # Close client
    client.close()

    console.print("\n[bold green]✓ Basic connectivity tests completed![/bold green]")
    console.print("\nYou can now run the full compliance check:")
    console.print("[cyan]python check_compliance.py[/cyan]\n")

    return True


if __name__ == "__main__":
    try:
        success = test_connection()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        console.print("\n[yellow]Interrupted by user[/yellow]")
        sys.exit(130)
    except Exception as e:
        console.print(f"\n[red]Unexpected error: {e}[/red]")
        sys.exit(1)
