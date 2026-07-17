"""CLI presentation adapters for one-source conversion outcomes."""

import sys
from enum import Enum
from pathlib import Path
from typing import Callable, Optional

from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, TaskID

from html2md.cli.conversion_service import ConversionResult, convert_source
from html2md.markdown.content_extractor import ContentMode


def _convert_one(
    source: str,
    content_mode: ContentMode,
    selector: Optional[str],
    output: Optional[Path],
    no_cookies: bool,
    browser_cookies: bool,
    browser: Optional[Enum],
    cookie_json: Optional[Path],
    headers_file: Optional[Path],
    storage_state: Optional[Path],
    local: bool,
    download_images: bool,
    images_dir: str,
    enhanced_headers: bool,
    user_agent_contact: Optional[str],
    simulate_browser: bool,
    insecure: bool,
    include_metadata: bool,
    render_js: bool,
    allow_private_network: bool,
    on_status: Optional[Callable[[str], None]] = None,
) -> ConversionResult:
    """Translate CLI option types into one presentation-neutral conversion."""
    status_callback = on_status or (lambda _message: None)
    return convert_source(
        source,
        content_mode=content_mode,
        selector=selector,
        output=output,
        no_cookies=no_cookies,
        browser_cookies=browser_cookies,
        browser=browser.value if browser else None,
        cookie_json=cookie_json,
        headers_file=headers_file,
        storage_state=storage_state,
        local=local,
        download_images=download_images,
        images_dir=images_dir,
        enhanced_headers=enhanced_headers,
        user_agent_contact=user_agent_contact,
        simulate_browser=simulate_browser,
        insecure=insecure,
        include_metadata=include_metadata,
        render_js=render_js,
        allow_private_network=allow_private_network,
        on_status=status_callback,
    )


def process_single_with_progress(
    source: str,
    content_mode: ContentMode,
    selector: Optional[str],
    output: Optional[Path],
    no_cookies: bool,
    browser_cookies: bool,
    browser: Optional[Enum],
    cookie_path: Optional[Path] = None,
    cookie_json: Optional[Path] = None,
    headers_file: Optional[Path] = None,
    storage_state: Optional[Path] = None,
    local: bool = False,
    download_images: bool = False,
    images_dir: str = "images",
    enhanced_headers: bool = True,
    user_agent_contact: Optional[str] = None,
    simulate_browser: bool = False,
    insecure: bool = False,
    include_metadata: bool = False,
    render_js: bool = False,
    allow_private_network: bool = False,
    progress: Optional[Progress] = None,
    task_id: Optional[TaskID] = None,
    console: Optional[Console] = None,
) -> bool:
    """Render a shared conversion result with interactive progress output."""
    del cookie_path  # The command persists this preference before conversion.
    if progress is None or task_id is None or console is None:
        raise ValueError("progress, task_id, and console are required in fancy mode")
    progress.update(task_id, description=f"Processing {source}")
    result = _convert_one(
        source,
        content_mode,
        selector,
        output,
        no_cookies,
        browser_cookies,
        browser,
        cookie_json,
        headers_file,
        storage_state,
        local,
        download_images,
        images_dir,
        enhanced_headers,
        user_agent_contact,
        simulate_browser,
        insecure,
        include_metadata,
        render_js,
        allow_private_network,
        lambda message: progress.update(task_id, description=message),
    )

    if not result.succeeded:
        progress.stop()
        if result.error:
            console.print(
                Panel(
                    f"[bold red]Error processing:[/bold red] {source}\n{result.error}",
                    title="Error",
                    border_style="red",
                )
            )
        else:
            console.print(
                Panel(
                    f"[bold red]Unable to retrieve or convert content from:[/bold red] {source}",
                    title="Error",
                    border_style="red",
                )
            )
        progress.start()
        progress.update(task_id, description=f"❌ Failed {source}")
        return False

    if output:
        progress.update(task_id, description=f"Saving to {output}")
        output.write_text(result.markdown or "", encoding="utf-8")

    progress.stop()
    if output:
        action = (
            "Downloaded and converted" if result.is_remote else "Converted local file"
        )
        console.print(
            f"[bold green]✓[/bold green] {action} [bold]{result.source_label}[/bold]"
        )
        console.print(
            f"[bold green]✓[/bold green] Saved output to [bold]{output}[/bold]"
        )
    else:
        label = "URL" if result.is_remote else "File"
        console.print(Panel.fit(f"# {label}: {result.source_label}", title="Source"))
        console.print(result.markdown)
    progress.start()
    progress.update(task_id, description=f"✅ Completed {result.source_label}")
    return True


def process_single_quiet(
    source: str,
    content_mode: ContentMode,
    selector: Optional[str],
    output: Optional[Path],
    no_cookies: bool,
    browser_cookies: bool,
    browser: Optional[Enum],
    cookie_path: Optional[Path] = None,
    cookie_json: Optional[Path] = None,
    headers_file: Optional[Path] = None,
    storage_state: Optional[Path] = None,
    local: bool = False,
    download_images: bool = False,
    images_dir: str = "images",
    enhanced_headers: bool = True,
    user_agent_contact: Optional[str] = None,
    simulate_browser: bool = False,
    insecure: bool = False,
    include_metadata: bool = False,
    render_js: bool = False,
    allow_private_network: bool = False,
) -> bool:
    """Render a shared conversion result without decoration."""
    del cookie_path  # The command persists this preference before conversion.
    result = _convert_one(
        source,
        content_mode,
        selector,
        output,
        no_cookies,
        browser_cookies,
        browser,
        cookie_json,
        headers_file,
        storage_state,
        local,
        download_images,
        images_dir,
        enhanced_headers,
        user_agent_contact,
        simulate_browser,
        insecure,
        include_metadata,
        render_js,
        allow_private_network,
    )
    if not result.succeeded:
        if result.error:
            message = f"Error processing {source}: {result.error}"
        elif result.is_remote:
            message = f"Error: Unable to retrieve content from {source}"
        else:
            message = f"Error: Unable to convert local file {result.source_label}"
        print(message, file=sys.stderr)
        return False

    if output:
        output.write_text(result.markdown or "", encoding="utf-8")
    else:
        print(result.markdown)
    return True
