import os
import re
import sys
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import List, Optional

import openpyxl

from .downloader import download_video
from .excel_parser import parse_excel
from .models import DownloadJob, DownloadResult, DownloadStatus
from .progress import ProgressUI, console

_URL_RE = re.compile(
    r"https?://(www\.)?(tiktok\.com|douyin\.com|facebook\.com|fb\.watch"
    r"|youtube\.com/shorts|youtu\.be)",
    re.IGNORECASE,
)


def _is_url(value: str) -> bool:
    return bool(_URL_RE.match(value.strip()))


def _save_failed_report(results: List[DownloadResult], output_dir: str):
    failed = [r for r in results if r.status == DownloadStatus.FAILED]
    if not failed:
        return

    report_path = os.path.join(output_dir, "failed_links.xlsx")
    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Failed Downloads"

    ws.append(["#", "URL", "Platform", "Attempts", "Error"])
    ws.column_dimensions["A"].width = 6
    ws.column_dimensions["B"].width = 60
    ws.column_dimensions["C"].width = 12
    ws.column_dimensions["D"].width = 10
    ws.column_dimensions["E"].width = 80

    for r in failed:
        ws.append([
            r.job.row_number,
            r.job.url,
            r.job.platform.value,
            r.attempts,
            r.error or "Unknown error",
        ])

    wb.save(report_path)


def run_sequential(
    jobs: List[DownloadJob],
    output: str,
    retries: int,
    ui: ProgressUI,
    cookies_browser: Optional[str] = None,
    use_cwd: bool = False,
) -> List[DownloadResult]:
    results = []

    for i, job in enumerate(jobs, start=1):
        def on_attempt(attempt, idx=i):
            ui.set_downloading(idx, attempt)

        result = download_video(
            job, output,
            max_retries=retries,
            on_attempt=on_attempt,
            cookies_browser=cookies_browser,
            use_cwd=use_cwd,
        )
        ui.set_result(i, result)
        results.append(result)

    return results


def run_parallel(
    jobs: List[DownloadJob],
    output: str,
    retries: int,
    workers: int,
    ui: ProgressUI,
    cookies_browser: Optional[str] = None,
    use_cwd: bool = False,
) -> List[DownloadResult]:
    results = [None] * len(jobs)

    with ThreadPoolExecutor(max_workers=workers) as executor:
        futures = {}
        for i, job in enumerate(jobs, start=1):
            def on_attempt(attempt, idx=i):
                ui.set_downloading(idx, attempt)

            future = executor.submit(
                download_video, job, output, retries, on_attempt, cookies_browser, use_cwd
            )
            futures[future] = i

        for future in as_completed(futures):
            i = futures[future]
            result = future.result()
            results[i - 1] = result
            ui.set_result(i, result)

    return results


def main(args=None):
    import argparse

    parser = argparse.ArgumentParser(
        prog="aidownloader",
        description="📥 Batch download videos from TikTok, Douyin, Facebook Reels & YouTube Shorts",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Single URL — downloads into current folder
  aidownloader https://www.tiktok.com/@user/video/123
  aidownloader https://www.facebook.com/reel/456

  # Batch from Excel
  aidownloader --input links.xlsx
  aidownloader --input links.xlsx --output ./my-videos --workers 4
  aidownloader --input links.xlsx --dry-run
        """,
    )

    # Positional: optional single URL
    parser.add_argument(
        "url",
        nargs="?",
        metavar="URL",
        help="Single video URL to download into the current folder",
    )
    parser.add_argument("--input", "-i", help="Path to Excel file (.xlsx/.xls) for batch mode")
    parser.add_argument("--output", "-o", default=None, help="Output folder (default: current folder for URL mode, ./downloads for batch)")
    parser.add_argument("--workers", "-w", type=int, default=1, help="Parallel download workers (default: 1 = sequential)")
    parser.add_argument("--retries", "-r", type=int, default=3, help="Max retries per URL on failure (default: 3)")
    parser.add_argument("--dry-run", action="store_true", help="Parse Excel and list URLs without downloading")
    parser.add_argument(
        "--cookies-browser", "-c",
        metavar="BROWSER",
        help="Borrow cookies from browser to bypass 403 blocks (chrome, firefox, edge)",
    )

    parsed = parser.parse_args(args)
    cookies_browser = getattr(parsed, "cookies_browser", None)

    # ── MODE A: Single URL ──────────────────────────────────────────────────
    if parsed.url:
        url = parsed.url.strip()
        if not _is_url(url):
            console.print(f"[red]❌ Not a supported URL:[/red] {url}")
            console.print("[dim]Supported: TikTok, Douyin, Facebook Reels, YouTube Shorts[/dim]")
            sys.exit(1)

        job = DownloadJob(url=url, row_number=1)
        # Default output: current working directory (no date subfolder)
        output = parsed.output or os.getcwd()
        use_cwd = parsed.output is None  # flag to skip date subfolder

        console.print(f"\n[cyan]🔗 URL:[/cyan] {url}")
        console.print(f"[cyan]📦 Platform:[/cyan] [bold]{job.platform.value}[/bold]")
        console.print(f"[cyan]📂 Saving to:[/cyan] [bold]{output}[/bold]\n")

        if cookies_browser:
            console.print(f"[cyan]🍪 Using cookies from:[/cyan] [bold]{cookies_browser}[/bold]")

        ui = ProgressUI(total=1)
        ui.start()
        ui.add_job(1, job.platform.value, job.url)

        try:
            results = run_sequential([job], output, parsed.retries, ui, cookies_browser, use_cwd=True)
        finally:
            ui.stop()

        ui.print_summary()
        result = results[0]
        if result.status == DownloadStatus.SUCCESS:
            filename = os.path.basename(result.output_path or "")
            console.print(f"  [green]📄 File:[/green] [bold]{filename}[/bold]\n")
        return

    # ── MODE B: Batch Excel ─────────────────────────────────────────────────
    if not parsed.input:
        console.print("[red]❌ Provide either a URL or --input <excel file>[/red]")
        console.print("[dim]Run: aidownloader --help[/dim]")
        sys.exit(1)

    output = parsed.output or "./downloads"

    console.print(f"\n[cyan]📂 Reading:[/cyan] [bold]{parsed.input}[/bold]")
    try:
        jobs = parse_excel(parsed.input)
    except Exception as exc:
        console.print(f"[red]❌ Failed to parse Excel file:[/red] {exc}")
        sys.exit(1)

    console.print(f"[green]✅ Found [bold]{len(jobs)}[/bold] video URL(s)[/green]")

    if parsed.dry_run:
        console.print("\n[yellow]🔍 Dry run — no downloads will be performed:[/yellow]\n")
        for i, job in enumerate(jobs, 1):
            console.print(f"  [{i:>3}] [{job.platform.value}] {job.url}")
        console.print()
        sys.exit(0)

    if parsed.workers > 1:
        console.print(
            f"[yellow]⚡ Parallel mode:[/yellow] {parsed.workers} workers  "
            f"[dim](high values may trigger rate limiting)[/dim]"
        )
    else:
        console.print("[dim]🔁 Sequential mode (use --workers N for parallel)[/dim]")

    if cookies_browser:
        console.print(f"[cyan]🍪 Using cookies from:[/cyan] [bold]{cookies_browser}[/bold]")

    ui = ProgressUI(total=len(jobs))
    ui.start()

    for i, job in enumerate(jobs, start=1):
        ui.add_job(i, job.platform.value, job.url)

    try:
        if parsed.workers > 1:
            results = run_parallel(jobs, output, parsed.retries, parsed.workers, ui, cookies_browser)
        else:
            results = run_sequential(jobs, output, parsed.retries, ui, cookies_browser)
    finally:
        ui.stop()

    ui.print_summary()
    _save_failed_report(results, output)
