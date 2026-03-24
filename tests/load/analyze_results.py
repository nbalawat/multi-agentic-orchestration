#!/usr/bin/env python3
"""
Analyze load test results and generate summary report
"""

import argparse
import csv
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Any
from rich.console import Console
from rich.table import Table
from rich.panel import Panel
from rich.markdown import Markdown

console = Console()


class LoadTestAnalyzer:
    """Analyze load test results"""

    def __init__(self, reports_dir: Path):
        self.reports_dir = reports_dir
        self.results: List[Dict[str, Any]] = []

    def find_test_results(self) -> List[Path]:
        """Find all stats CSV files"""
        return sorted(
            self.reports_dir.glob("*_stats.csv"),
            key=lambda p: p.stat().st_mtime,
            reverse=True
        )

    def parse_stats_file(self, stats_file: Path) -> Dict[str, Any]:
        """Parse a stats CSV file"""
        result = {
            'file': stats_file.name,
            'timestamp': datetime.fromtimestamp(stats_file.stat().st_mtime),
            'endpoints': []
        }

        with open(stats_file, 'r') as f:
            reader = csv.DictReader(f)
            for row in reader:
                if row['Type'] == 'None':  # Skip summary rows during parse
                    continue

                endpoint = {
                    'name': row['Name'],
                    'method': row['Type'],
                    'requests': int(row['Request Count']),
                    'failures': int(row['Failure Count']),
                    'median_ms': float(row['Median Response Time']),
                    'avg_ms': float(row['Average Response Time']),
                    'min_ms': float(row['Min Response Time']),
                    'max_ms': float(row['Max Response Time']),
                    'p95_ms': float(row['95%']),
                    'p99_ms': float(row['99%']),
                    'rps': float(row['Requests/s']),
                    'avg_size_bytes': int(row['Average Content Size'])
                }

                if row['Name'] == 'Aggregated':
                    result['summary'] = endpoint
                else:
                    result['endpoints'].append(endpoint)

        return result

    def analyze_all_results(self) -> None:
        """Analyze all test results"""
        stats_files = self.find_test_results()

        if not stats_files:
            console.print("[red]No test results found in reports directory[/red]")
            return

        console.print(f"\n[cyan]Found {len(stats_files)} test result(s)[/cyan]\n")

        for stats_file in stats_files[:10]:  # Analyze latest 10 results
            result = self.parse_stats_file(stats_file)
            self.results.append(result)

    def print_summary_table(self) -> None:
        """Print summary table of all test runs"""
        if not self.results:
            return

        table = Table(title="Load Test Summary", title_style="bold cyan")
        table.add_column("Test Run", style="yellow")
        table.add_column("Timestamp", style="magenta")
        table.add_column("Requests", justify="right", style="cyan")
        table.add_column("Failures", justify="right", style="red")
        table.add_column("RPS", justify="right", style="green")
        table.add_column("P95 (ms)", justify="right", style="blue")
        table.add_column("Status", style="bold")

        for i, result in enumerate(self.results, 1):
            if 'summary' not in result:
                continue

            summary = result['summary']
            timestamp = result['timestamp'].strftime("%Y-%m-%d %H:%M")

            # Determine status based on targets
            p95 = summary['p95_ms']
            failure_rate = summary['failures'] / max(summary['requests'], 1) * 100

            status = "✅ PASS"
            if p95 > 300:
                status = "⚠️  P95 HIGH"
            if failure_rate > 1:
                status = "❌ FAIL"

            table.add_row(
                f"Run #{i}",
                timestamp,
                f"{summary['requests']:,}",
                f"{summary['failures']:,} ({failure_rate:.2f}%)",
                f"{summary['rps']:.2f}",
                f"{p95:.2f}",
                status
            )

        console.print(table)

    def print_detailed_analysis(self, index: int = 0) -> None:
        """Print detailed analysis of a specific test run"""
        if index >= len(self.results):
            console.print("[red]Invalid test run index[/red]")
            return

        result = self.results[index]
        console.print(f"\n[bold cyan]Detailed Analysis: {result['file']}[/bold cyan]")
        console.print(f"Timestamp: {result['timestamp']}\n")

        # Summary metrics
        if 'summary' in result:
            summary = result['summary']
            panel_content = f"""
**Overall Performance:**
- Total Requests: {summary['requests']:,}
- Failed Requests: {summary['failures']:,} ({summary['failures']/max(summary['requests'], 1)*100:.2f}%)
- Requests/sec: {summary['rps']:.2f}

**Response Times:**
- Median: {summary['median_ms']:.2f}ms
- Average: {summary['avg_ms']:.2f}ms
- P95: {summary['p95_ms']:.2f}ms
- P99: {summary['p99_ms']:.2f}ms
- Min: {summary['min_ms']:.2f}ms
- Max: {summary['max_ms']:.2f}ms

**Performance Assessment:**
"""
            # Check against targets
            if summary['rps'] >= 1000:
                panel_content += "\n✅ RPS target met (>= 1000 req/s)"
            else:
                panel_content += f"\n⚠️  RPS below target: {summary['rps']:.2f} req/s (target: >= 1000)"

            if summary['p95_ms'] < 300:
                panel_content += "\n✅ P95 latency target met (< 300ms)"
            else:
                panel_content += f"\n❌ P95 latency above target: {summary['p95_ms']:.2f}ms (target: < 300ms)"

            failure_rate = summary['failures'] / max(summary['requests'], 1) * 100
            if failure_rate < 1:
                panel_content += "\n✅ Error rate target met (< 1%)"
            else:
                panel_content += f"\n❌ Error rate above target: {failure_rate:.2f}% (target: < 1%)"

            console.print(Panel(Markdown(panel_content), title="Summary", border_style="cyan"))

        # Endpoint breakdown
        if result['endpoints']:
            table = Table(title="Endpoint Performance", title_style="bold green")
            table.add_column("Endpoint", style="cyan", no_wrap=False)
            table.add_column("Requests", justify="right")
            table.add_column("RPS", justify="right")
            table.add_column("P95 (ms)", justify="right")
            table.add_column("Failures", justify="right")

            # Sort by request count
            sorted_endpoints = sorted(
                result['endpoints'],
                key=lambda x: x['requests'],
                reverse=True
            )

            for endpoint in sorted_endpoints[:20]:  # Show top 20
                failure_rate = endpoint['failures'] / max(endpoint['requests'], 1) * 100
                failure_str = f"{endpoint['failures']:,}"
                if failure_rate > 0:
                    failure_str += f" ({failure_rate:.1f}%)"

                # Color code P95
                p95_str = f"{endpoint['p95_ms']:.2f}"
                if endpoint['p95_ms'] > 500:
                    p95_str = f"[red]{p95_str}[/red]"
                elif endpoint['p95_ms'] > 300:
                    p95_str = f"[yellow]{p95_str}[/yellow]"
                else:
                    p95_str = f"[green]{p95_str}[/green]"

                table.add_row(
                    endpoint['name'][:60],
                    f"{endpoint['requests']:,}",
                    f"{endpoint['rps']:.2f}",
                    p95_str,
                    failure_str
                )

            console.print("\n")
            console.print(table)

    def generate_json_report(self, output_file: Path) -> None:
        """Generate JSON report"""
        report = {
            'generated_at': datetime.now().isoformat(),
            'total_test_runs': len(self.results),
            'results': []
        }

        for result in self.results:
            report['results'].append({
                'file': result['file'],
                'timestamp': result['timestamp'].isoformat(),
                'summary': result.get('summary', {}),
                'endpoint_count': len(result['endpoints'])
            })

        with open(output_file, 'w') as f:
            json.dump(report, f, indent=2)

        console.print(f"\n[green]✅ JSON report saved to: {output_file}[/green]")


def main():
    parser = argparse.ArgumentParser(description="Analyze RAPIDS load test results")
    parser.add_argument(
        "--reports-dir", type=Path, default=Path("reports"),
        help="Reports directory (default: reports/)"
    )
    parser.add_argument(
        "--detailed", action="store_true",
        help="Show detailed analysis of latest test"
    )
    parser.add_argument(
        "--json", type=Path,
        help="Generate JSON report to specified file"
    )
    parser.add_argument(
        "--latest", type=int, default=0,
        help="Analyze specific test run (0=latest, 1=second latest, etc.)"
    )

    args = parser.parse_args()

    if not args.reports_dir.exists():
        console.print(f"[red]Reports directory not found: {args.reports_dir}[/red]")
        sys.exit(1)

    analyzer = LoadTestAnalyzer(args.reports_dir)
    analyzer.analyze_all_results()

    if not analyzer.results:
        console.print("[yellow]No test results to analyze[/yellow]")
        sys.exit(0)

    # Print summary table
    analyzer.print_summary_table()

    # Print detailed analysis if requested
    if args.detailed:
        analyzer.print_detailed_analysis(args.latest)

    # Generate JSON report if requested
    if args.json:
        analyzer.generate_json_report(args.json)


if __name__ == "__main__":
    try:
        main()
    except KeyboardInterrupt:
        console.print("\n\n[yellow]⚠️  Interrupted by user[/yellow]")
        sys.exit(1)
