"""Command-line interface for ci-agent."""

from __future__ import annotations

import sys
from pathlib import Path

import click
from rich.console import Console
from rich.markdown import Markdown
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn

from ci_agent.agent import CiAgent

console = Console()


@click.group()
def cli() -> None:
    """ci-agent: AI-powered GitHub Actions CI/CD workflow generator."""


@cli.command()
@click.option(
    "--src",
    default=".",
    show_default=True,
    help="Source directory to inspect.",
    type=click.Path(exists=True, file_okay=False, dir_okay=True, resolve_path=True),
)
@click.option(
    "--output",
    default=".github/workflows",
    show_default=True,
    help="Output directory for generated workflow files.",
)
@click.option(
    "--target",
    default="github-actions",
    show_default=True,
    help="CI/CD platform target (currently only github-actions is supported).",
)
@click.option(
    "--model",
    default="claude-sonnet-4-6",
    show_default=True,
    help="Anthropic model to use.",
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    default=False,
    help="Print tool calls and intermediate results.",
)
@click.option(
    "--api-key",
    envvar="ANTHROPIC_API_KEY",
    default=None,
    help="Anthropic API key (defaults to ANTHROPIC_API_KEY env var).",
    hide_input=True,
)
def generate(
    src: str,
    output: str,
    target: str,
    model: str,
    verbose: bool,
    api_key: str | None,
) -> None:
    """Inspect a project and generate GitHub Actions CI/CD workflows."""

    if target != "github-actions":
        console.print(
            f"[yellow]Warning:[/yellow] target '{target}' is not fully supported. "
            "Generating GitHub Actions workflows anyway."
        )

    src_path = Path(src)
    out_path = Path(output)

    console.print(
        Panel(
            f"[bold]Source:[/bold]  {src_path}\n"
            f"[bold]Output:[/bold]  {out_path}\n"
            f"[bold]Target:[/bold]  {target}\n"
            f"[bold]Model:[/bold]   {model}",
            title="[bold blue]ci-agent[/bold blue]",
            expand=False,
        )
    )

    agent = CiAgent(api_key=api_key, model=model, verbose=verbose)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        transient=True,
        console=console,
    ) as progress:
        task = progress.add_task("Generating CI/CD workflows...", total=None)
        try:
            summary = agent.generate(
                src_dir=str(src_path),
                output_dir=str(out_path),
                target=target,
            )
        except Exception as exc:  # noqa: BLE001
            progress.stop_task(task)
            console.print(f"[bold red]Error:[/bold red] {exc}")
            sys.exit(1)

    # Print summary
    console.print()
    console.print(Markdown(summary))

    # List generated files
    if out_path.exists():
        workflow_files = sorted(out_path.glob("*.yml")) + sorted(out_path.glob("*.yaml"))
        if workflow_files:
            console.print()
            console.print("[bold green]Generated workflow files:[/bold green]")
            for wf in workflow_files:
                console.print(f"  [cyan]{wf}[/cyan]")


@cli.command("detect")
@click.argument(
    "directory",
    default=".",
    type=click.Path(exists=True, file_okay=False, dir_okay=True, resolve_path=True),
)
def detect_cmd(directory: str) -> None:
    """Detect project tooling without generating workflows (useful for debugging)."""
    from ci_agent.detector import ProjectDetector

    detector = ProjectDetector(directory)
    info = detector.detect()

    console.print(
        Panel(
            f"[bold]Language:[/bold]         {info.language}\n"
            f"[bold]Runtime version:[/bold]  {info.runtime_version or 'unknown'}\n"
            f"[bold]Test runner:[/bold]      {info.test_runner}\n"
            f"[bold]Linter:[/bold]           {info.linter}\n"
            f"[bold]Formatter:[/bold]        {info.formatter}\n"
            f"[bold]Build tool:[/bold]       {info.build_tool}\n"
            f"[bold]Package manager:[/bold]  {info.package_manager}\n"
            f"[bold]Deploy target:[/bold]    {info.deployment_target}\n"
            f"[bold]Frameworks:[/bold]       {', '.join(info.frameworks) or 'none'}",
            title=f"[bold blue]Project detection: {directory}[/bold blue]",
            expand=False,
        )
    )


def main() -> None:
    """Entry point for the ci-agent command."""
    cli()


if __name__ == "__main__":
    main()
