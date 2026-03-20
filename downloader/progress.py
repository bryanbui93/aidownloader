import io
import sys
from typing import List

from rich.console import Console, Group as RichGroup
from rich.live import Live
from rich.panel import Panel
from rich.progress import (
    BarColumn,
    MofNCompleteColumn,
    Progress,
    SpinnerColumn,
    TaskID,
    TextColumn,
    TimeElapsedColumn,
    TimeRemainingColumn,
)
from rich.table import Table
from rich.text import Text

from .models import DownloadResult, DownloadStatus


def _make_console() -> Console:
    """Create a Rich Console with UTF-8 output on Windows.

    Windows CMD/PowerShell defaults to cp1252 which cannot encode emoji.
    Wrapping stdout in a UTF-8 TextIOWrapper fixes UnicodeEncodeError.
    """
    if sys.platform == "win32":
        try:
            utf8_stdout = io.TextIOWrapper(
                sys.stdout.buffer, encoding="utf-8", errors="replace"
            )
            return Console(file=utf8_stdout, highlight=False)
        except AttributeError:
            # Fallback: stdout has no .buffer (e.g. inside some IDEs)
            return Console(highlight=False)
    return Console()


console = _make_console()

# Status icon mapping
_STATUS_STYLE = {
    DownloadStatus.PENDING:     ("⏳", "dim"),
    DownloadStatus.DOWNLOADING: ("⬇️ ", "cyan"),
    DownloadStatus.SUCCESS:     ("✅", "green"),
    DownloadStatus.FAILED:      ("❌", "red"),
    DownloadStatus.SKIPPED:     ("⏭️ ", "yellow"),
}

_PLATFORM_COLOR = {
    "TikTok":   "bright_magenta",
    "Douyin":   "red",
    "Facebook": "blue",
    "YouTube":  "bright_red",
    "Unknown":  "dim",
}


def _make_status_cell(status: DownloadStatus, attempt: int = 0) -> Text:
    icon, style = _STATUS_STYLE[status]
    label = status.value.capitalize()
    if status == DownloadStatus.DOWNLOADING and attempt > 1:
        label = f"Retry {attempt}"
    return Text(f"{icon} {label}", style=style)


def _truncate(text: str, max_len: int = 55) -> str:
    return text if len(text) <= max_len else text[:max_len - 3] + "..."


def _build_table(rows: list) -> Table:
    table = Table(
        show_header=True,
        header_style="bold cyan",
        border_style="grey27",
        expand=True,
    )
    table.add_column("#", style="dim", width=4, justify="right")
    table.add_column("Platform", width=10)
    table.add_column("URL", no_wrap=True)
    table.add_column("Status", width=16)

    for row in rows:
        num, platform, url, status_cell = row
        platform_color = _PLATFORM_COLOR.get(platform, "white")
        table.add_row(
            str(num),
            Text(platform, style=platform_color),
            Text(_truncate(url), style="dim"),
            status_cell,
        )

    return table


class ProgressUI:
    def __init__(self, total: int):
        self._total = total
        self._rows: list = []
        self._results: List[DownloadResult] = []

        self._progress = Progress(
            SpinnerColumn(),
            TextColumn("[bold cyan]Downloading videos[/bold cyan]"),
            BarColumn(bar_width=None),
            MofNCompleteColumn(),
            TimeElapsedColumn(),
            TimeRemainingColumn(),
            console=console,
        )
        self._task_id: TaskID = self._progress.add_task("", total=total)
        self._live = Live(refresh_per_second=8, console=console)

    def _render(self) -> RichGroup:
        # Render table panel + progress bar as a vertical Group.
        # NOTE: Panel.subtitle cannot accept a Progress renderable (causes AttributeError
        # on rich <=14.x), so we stack them using RichGroup instead.
        table = _build_table(self._rows)
        panel = Panel(
            table,
            title="[bold]🎬 AI Video Downloader[/bold]",
            border_style="cyan",
        )
        return RichGroup(panel, self._progress)

    def start(self):
        self._live.start()

    def stop(self):
        self._live.stop()

    def add_job(self, index: int, platform: str, url: str):
        """Register a new job row as PENDING."""
        self._rows.append(
            [index, platform, url, _make_status_cell(DownloadStatus.PENDING)]
        )
        self._live.update(self._render())

    def set_downloading(self, index: int, attempt: int = 1):
        """Mark a row as currently downloading."""
        self._rows[index - 1][3] = _make_status_cell(
            DownloadStatus.DOWNLOADING, attempt
        )
        self._live.update(self._render())

    def set_result(self, index: int, result: DownloadResult):
        """Update a row with the final result and advance the progress bar."""
        self._rows[index - 1][3] = _make_status_cell(result.status, result.attempts)
        self._results.append(result)
        self._progress.advance(self._task_id)
        self._live.update(self._render())

    def print_summary(self):
        """Print a final summary panel after all downloads complete."""
        succeeded = sum(1 for r in self._results if r.status == DownloadStatus.SUCCESS)
        failed = sum(1 for r in self._results if r.status == DownloadStatus.FAILED)

        console.print()
        console.rule("[bold cyan]Download Summary[/bold cyan]")
        console.print(f"  ✅ [green]Succeeded:[/green] {succeeded}")
        console.print(f"  ❌ [red]Failed:[/red]    {failed}")
        console.print(f"  📦 [cyan]Total:[/cyan]     {self._total}")

        if failed:
            console.print(
                "\n  [yellow]⚠️  Failed URLs saved to [bold]failed_links.xlsx[/bold][/yellow]"
            )
        console.print()
