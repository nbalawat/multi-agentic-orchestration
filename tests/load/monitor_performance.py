#!/usr/bin/env python3
"""
Real-time performance monitor for RAPIDS load testing
Monitors backend metrics during load tests
"""

import argparse
import asyncio
import httpx
import sys
import time
from datetime import datetime
from typing import Dict, Any, Optional
from rich.console import Console
from rich.table import Table
from rich.live import Live
from rich.panel import Panel
from rich.layout import Layout


console = Console()


class PerformanceMonitor:
    """Monitor backend performance during load tests"""

    def __init__(self, base_url: str, refresh_interval: float = 1.0):
        self.base_url = base_url
        self.refresh_interval = refresh_interval
        self.client = httpx.AsyncClient(timeout=10.0)
        self.start_time = time.time()
        self.metrics_history: list = []

    async def fetch_health(self) -> Optional[Dict[str, Any]]:
        """Fetch health endpoint data"""
        try:
            response = await self.client.get(f"{self.base_url}/health")
            if response.status_code == 200:
                return response.json()
            return None
        except Exception:
            return None

    async def fetch_orchestrator_status(self) -> Optional[Dict[str, Any]]:
        """Fetch orchestrator status"""
        try:
            response = await self.client.get(f"{self.base_url}/get_orchestrator")
            if response.status_code == 200:
                return response.json()
            return None
        except Exception:
            return None

    async def fetch_agents(self) -> Optional[list]:
        """Fetch list of agents"""
        try:
            response = await self.client.get(f"{self.base_url}/list_agents")
            if response.status_code == 200:
                return response.json()
            return None
        except Exception:
            return None

    async def fetch_circuit_breakers(self) -> Optional[Dict[str, Any]]:
        """Fetch circuit breaker status"""
        try:
            response = await self.client.get(f"{self.base_url}/api/circuit-breakers")
            if response.status_code == 200:
                return response.json()
            return None
        except Exception:
            return None

    def create_dashboard(self, health: Optional[Dict], orchestrator: Optional[Dict],
                        agents: Optional[list], circuit_breakers: Optional[Dict]) -> Layout:
        """Create dashboard layout"""
        layout = Layout()
        layout.split_column(
            Layout(name="header", size=3),
            Layout(name="body"),
            Layout(name="footer", size=3)
        )

        # Header
        uptime = int(time.time() - self.start_time)
        uptime_str = f"{uptime // 60}m {uptime % 60}s"
        header_text = f"[bold cyan]RAPIDS Performance Monitor[/bold cyan] | Uptime: {uptime_str} | {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
        layout["header"].update(Panel(header_text, style="bold blue"))

        # Body - split into two columns
        layout["body"].split_row(
            Layout(name="left"),
            Layout(name="right")
        )

        # Left column - Health & Orchestrator
        left_table = Table(title="System Status", title_style="bold green")
        left_table.add_column("Metric", style="cyan")
        left_table.add_column("Value", style="magenta")

        if health:
            left_table.add_row("Backend Status", "✅ Healthy" if health.get('status') == 'healthy' else "❌ Unhealthy")
            left_table.add_row("Database", "✅ Connected" if health.get('database') == 'connected' else "❌ Disconnected")

        if orchestrator:
            left_table.add_row("Orchestrator ID", str(orchestrator.get('id', 'N/A'))[:16])
            left_table.add_row("Session ID", str(orchestrator.get('session_id', 'N/A'))[:16])
            left_table.add_row("Input Tokens", f"{orchestrator.get('input_tokens', 0):,}")
            left_table.add_row("Output Tokens", f"{orchestrator.get('output_tokens', 0):,}")
            left_table.add_row("Total Cost", f"${orchestrator.get('total_cost', 0):.4f}")

        layout["left"].update(Panel(left_table))

        # Right column - Agents
        right_table = Table(title="Active Agents", title_style="bold green")
        right_table.add_column("Name", style="cyan")
        right_table.add_column("Status", style="magenta")
        right_table.add_column("Tokens", style="yellow")

        if agents:
            for agent in agents[:10]:  # Show first 10 agents
                name = agent.get('name', 'Unknown')[:20]
                status = agent.get('status', 'UNKNOWN')
                tokens = agent.get('input_tokens', 0) + agent.get('output_tokens', 0)
                status_emoji = "🟢" if status == "IDLE" else "🔴" if status == "EXECUTING" else "⚪"
                right_table.add_row(name, f"{status_emoji} {status}", f"{tokens:,}")

            if len(agents) > 10:
                right_table.add_row("...", f"({len(agents) - 10} more)", "...")
        else:
            right_table.add_row("No agents", "-", "-")

        layout["right"].update(Panel(right_table))

        # Footer - Circuit Breakers
        footer_text = "Circuit Breakers: "
        if circuit_breakers:
            for name, status in circuit_breakers.items():
                state = status.get('state', 'UNKNOWN')
                if state == 'CLOSED':
                    footer_text += f"[green]{name}: {state}[/green] | "
                elif state == 'OPEN':
                    footer_text += f"[red]{name}: {state}[/red] | "
                else:
                    footer_text += f"[yellow]{name}: {state}[/yellow] | "
        else:
            footer_text += "[dim]Not available[/dim]"

        layout["footer"].update(Panel(footer_text.rstrip(" | ")))

        return layout

    async def monitor(self):
        """Run the monitoring loop"""
        console.print("\n[bold green]Starting Performance Monitor...[/bold green]\n")
        console.print(f"Monitoring: {self.base_url}")
        console.print(f"Refresh interval: {self.refresh_interval}s")
        console.print("\nPress Ctrl+C to stop\n")

        with Live(console=console, refresh_per_second=1) as live:
            while True:
                try:
                    # Fetch all metrics
                    health, orchestrator, agents, circuit_breakers = await asyncio.gather(
                        self.fetch_health(),
                        self.fetch_orchestrator_status(),
                        self.fetch_agents(),
                        self.fetch_circuit_breakers(),
                        return_exceptions=True
                    )

                    # Handle exceptions
                    health = health if not isinstance(health, Exception) else None
                    orchestrator = orchestrator if not isinstance(orchestrator, Exception) else None
                    agents = agents if not isinstance(agents, Exception) else None
                    circuit_breakers = circuit_breakers if not isinstance(circuit_breakers, Exception) else None

                    # Update dashboard
                    dashboard = self.create_dashboard(health, orchestrator, agents, circuit_breakers)
                    live.update(dashboard)

                    # Record metrics
                    self.metrics_history.append({
                        'timestamp': datetime.now().isoformat(),
                        'health': health,
                        'agent_count': len(agents) if agents else 0,
                        'orchestrator_cost': orchestrator.get('total_cost', 0) if orchestrator else 0
                    })

                    # Keep only last 100 metrics
                    if len(self.metrics_history) > 100:
                        self.metrics_history.pop(0)

                    await asyncio.sleep(self.refresh_interval)

                except KeyboardInterrupt:
                    break
                except Exception as e:
                    console.print(f"[red]Error: {e}[/red]")
                    await asyncio.sleep(self.refresh_interval)

    async def cleanup(self):
        """Cleanup resources"""
        await self.client.aclose()


async def main():
    parser = argparse.ArgumentParser(description="Monitor RAPIDS performance during load testing")
    parser.add_argument(
        "--host", type=str, default="http://127.0.0.1:9403",
        help="Backend URL (default: http://127.0.0.1:9403)"
    )
    parser.add_argument(
        "--interval", type=float, default=1.0,
        help="Refresh interval in seconds (default: 1.0)"
    )

    args = parser.parse_args()

    monitor = PerformanceMonitor(args.host, args.interval)
    try:
        await monitor.monitor()
    except KeyboardInterrupt:
        console.print("\n\n[yellow]⚠️  Monitoring stopped by user[/yellow]")
    finally:
        await monitor.cleanup()
        console.print("\n[green]✅ Monitor shutdown complete[/green]\n")


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        sys.exit(0)
