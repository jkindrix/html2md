"""
Progress display and estimation for concurrent crawling.

This module provides real-time progress tracking and ETA calculation
based on rate limits and concurrent request statistics.
"""

import time
from datetime import timedelta
from typing import Dict, Optional, Any
from rich.console import Console
from rich.panel import Panel
from rich.progress import (
    Progress, SpinnerColumn, TextColumn, BarColumn, 
    TimeElapsedColumn, TimeRemainingColumn
)
from rich.table import Table
from rich.text import Text
from rich.layout import Layout


class CrawlProgress:
    """Display crawling progress with rate limit awareness."""
    
    def __init__(self, console: Optional[Console] = None, 
                 show_progress: bool = True,
                 polite_mode: bool = False):
        self.console = console or Console()
        self.show_progress = show_progress
        self.polite_mode = polite_mode
        self.start_time = time.time()
        self._last_update = 0
        self._update_interval = 0.5  # Update display every 500ms
        
        # Progress tracking
        self.total_urls = 0
        self.completed_urls = 0
        self.failed_urls = 0
        self.domains_active = set()
        self.domains_backoff = {}
        
        # Initialize progress display
        if self.show_progress:
            self._setup_display()
    
    def _setup_display(self):
        """Set up the progress display components."""
        self.progress = Progress(
            SpinnerColumn(),
            TextColumn("[bold blue]{task.description}"),
            BarColumn(),
            TextColumn("[progress.percentage]{task.percentage:>3.0f}%"),
            TimeElapsedColumn(),
            TimeRemainingColumn(),
            console=self.console,
            expand=False
        )
        
        self.main_task = self.progress.add_task(
            "Crawling websites", total=None, start=True
        )
    
    def update(self, stats: Dict[str, Any], force: bool = False):
        """
        Update progress display with current statistics.
        
        Args:
            stats: Statistics from concurrent controller
            force: Force update regardless of interval
        """
        if not self.show_progress:
            return
        
        # Check update interval
        now = time.time()
        if not force and now - self._last_update < self._update_interval:
            return
        
        self._last_update = now
        
        # Update progress bar
        if 'total_queued' in stats and stats['total_queued'] > 0:
            self.progress.update(
                self.main_task,
                completed=stats.get('total_completed', 0),
                total=stats['total_queued']
            )
        
        # Create status table
        self._display_status(stats)
    
    def _display_status(self, stats: Dict[str, Any]):
        """Display detailed status information."""
        # Create layout
        layout = Layout()
        
        # Top section: Overview
        overview = self._create_overview_panel(stats)
        
        # Middle section: Domain status
        domain_status = self._create_domain_panel(stats)
        
        # Bottom section: Performance metrics
        performance = self._create_performance_panel(stats)
        
        # Combine panels
        layout.split_column(
            Layout(overview, size=7),
            Layout(domain_status, size=10),
            Layout(performance, size=6)
        )
        
        # Clear and print
        self.console.clear()
        self.console.print(layout)
        self.console.print(self.progress)
    
    def _create_overview_panel(self, stats: Dict[str, Any]) -> Panel:
        """Create overview panel."""
        completed = stats.get('total_completed', 0)
        queued = stats.get('queued_requests', 0)
        active = stats.get('currently_active', 0)
        
        # Calculate progress percentage
        total = completed + queued + active
        progress_pct = (completed / total * 100) if total > 0 else 0
        
        # Create content
        content = Table.grid(padding=1)
        content.add_column(style="cyan", no_wrap=True)
        content.add_column(style="green")
        
        content.add_row("Mode:", "🐌 Polite" if self.polite_mode else "🚀 Normal")
        content.add_row("Progress:", f"{completed}/{total} ({progress_pct:.1f}%)")
        content.add_row("Active Requests:", str(active))
        content.add_row("Queued Requests:", str(queued))
        
        # Add ETA if available
        if 'eta_seconds' in stats and stats['eta_seconds']:
            eta = timedelta(seconds=int(stats['eta_seconds']))
            content.add_row("Estimated Time:", str(eta))
        
        # Add pause status
        if stats.get('is_paused', False):
            content.add_row("Status:", "[bold red]PAUSED[/bold red]")
        
        return Panel(content, title="[bold]Crawl Overview[/bold]", border_style="blue")
    
    def _create_domain_panel(self, stats: Dict[str, Any]) -> Panel:
        """Create domain status panel."""
        table = Table(title="Domain Status", show_header=True, header_style="bold cyan")
        table.add_column("Domain", style="white", no_wrap=True)
        table.add_column("Active", justify="center", style="green")
        table.add_column("Queued", justify="center", style="yellow")
        table.add_column("Status", justify="center")
        
        # Get domain-specific stats if available
        if 'domain_stats' in stats:
            for domain, domain_stat in stats['domain_stats'].items():
                status = "Active"
                status_style = "green"
                
                if domain_stat.get('in_backoff', False):
                    backoff_time = domain_stat.get('backoff_remaining', 0)
                    status = f"Backoff ({backoff_time:.0f}s)"
                    status_style = "red"
                elif domain_stat.get('consecutive_errors', 0) > 0:
                    status = f"Errors: {domain_stat['consecutive_errors']}"
                    status_style = "yellow"
                
                table.add_row(
                    domain[:30] + "..." if len(domain) > 30 else domain,
                    str(domain_stat.get('active_connections', 0)),
                    str(domain_stat.get('queued_requests', 0)),
                    Text(status, style=status_style)
                )
        else:
            # Fallback display
            active_domains = stats.get('active_domains', 0)
            backoff_domains = stats.get('domains_in_backoff', 0)
            
            table.add_row(
                f"Active Domains: {active_domains}",
                "", "", ""
            )
            table.add_row(
                f"Domains in Backoff: {backoff_domains}",
                "", "", "[red]Waiting[/red]"
            )
        
        return Panel(table, border_style="cyan")
    
    def _create_performance_panel(self, stats: Dict[str, Any]) -> Panel:
        """Create performance metrics panel."""
        content = Table.grid(padding=1)
        content.add_column(style="magenta", no_wrap=True)
        content.add_column(style="white")
        
        # Request rate
        rps = stats.get('requests_per_second', 0)
        content.add_row("Request Rate:", f"{rps:.2f} req/s")
        
        # Time elapsed
        elapsed = stats.get('elapsed_seconds', 0)
        elapsed_str = str(timedelta(seconds=int(elapsed)))
        content.add_row("Time Elapsed:", elapsed_str)
        
        content.add_row("Active Request:", f"{stats.get('currently_active', 0)}/1")
        
        # Error rate
        total_completed = stats.get('total_completed', 0)
        if total_completed > 0 and 'total_errors' in stats:
            error_rate = stats['total_errors'] / total_completed * 100
            content.add_row("Error Rate:", f"{error_rate:.1f}%")
        
        return Panel(content, title="[bold]Performance[/bold]", border_style="magenta")
    
    def show_completion(self, total_urls: int, total_time: float, 
                       success_count: int, error_count: int):
        """Show final completion summary."""
        if not self.show_progress:
            return
        
        # Clear progress
        self.progress.stop()
        
        # Create completion panel
        table = Table.grid(padding=1)
        table.add_column(style="cyan", no_wrap=True)
        table.add_column(style="green")
        
        table.add_row("Total URLs Processed:", str(total_urls))
        table.add_row("Successful:", f"{success_count} ({success_count/total_urls*100:.1f}%)")
        table.add_row("Failed:", f"{error_count} ({error_count/total_urls*100:.1f}%)")
        table.add_row("Total Time:", str(timedelta(seconds=int(total_time))))
        table.add_row("Average Rate:", f"{total_urls/total_time:.2f} URLs/second")
        
        panel = Panel(
            table,
            title="[bold green]Crawl Complete[/bold green]",
            border_style="green",
            expand=False
        )
        
        self.console.print(panel)
    
    def log_message(self, message: str, level: str = "info"):
        """Log a message without disrupting progress display."""
        if not self.show_progress:
            self.console.print(message)
            return
        
        # Temporarily pause progress
        self.progress.stop()
        
        # Print message with appropriate style
        if level == "error":
            self.console.print(f"[bold red]ERROR:[/bold red] {message}")
        elif level == "warning":
            self.console.print(f"[bold yellow]WARNING:[/bold yellow] {message}")
        else:
            self.console.print(f"[dim]{message}[/dim]")
        
        # Resume progress
        self.progress.start()
    
    def pause(self):
        """Pause the progress display."""
        if self.show_progress:
            self.progress.stop()
            self.console.print("[bold yellow]Progress display paused[/bold yellow]")
    
    def resume(self):
        """Resume the progress display."""
        if self.show_progress:
            self.progress.start()
            self.console.print("[bold green]Progress display resumed[/bold green]")


def estimate_crawl_time(total_urls: int, rate_limit: Optional[int] = None,
                       avg_response_time: float = 1.0) -> float:
    """
    Estimate crawl time for the sequential crawler.
    
    Args:
        total_urls: Total number of URLs to crawl
        rate_limit: Requests per minute limit (None for no limit)
        avg_response_time: Average response time per request in seconds
        
    Returns:
        Estimated time in seconds
    """
    if rate_limit:
        # Rate limited scenario
        time_by_rate_limit = (total_urls / rate_limit) * 60
        
        time_by_requests = total_urls * avg_response_time
        
        # Return the larger constraint
        return max(time_by_rate_limit, time_by_requests)
    else:
        return total_urls * avg_response_time


def format_eta(seconds: float) -> str:
    """Format ETA in human-readable format."""
    if seconds < 60:
        return f"{int(seconds)} seconds"
    elif seconds < 3600:
        minutes = int(seconds / 60)
        return f"{minutes} minute{'s' if minutes != 1 else ''}"
    else:
        hours = int(seconds / 3600)
        minutes = int((seconds % 3600) / 60)
        return f"{hours}h {minutes}m"
