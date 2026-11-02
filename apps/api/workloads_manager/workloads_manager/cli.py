# Copyright © Advanced Micro Devices, Inc., or its affiliates.
#
# SPDX-License-Identifier: MIT

"""Command-line interface for the workloads manager."""

import os
import sys
from pathlib import Path

import httpx
import inquirer
import rich.table
import rich_click as click
from loguru import logger
from rich.console import Console
from rich.markup import escape

from . import config
from .core import patches, registration, repository, utils
from .core.workloads import (
    check_patches_match_changes,
    get_changed_workloads,
    get_registerable_workloads,
    get_workloads,
)
from .models import Workload

click.rich_click.USE_RICH_MARKUP = True
console = Console(width=120)

# Set default log level to INFO with a more concise format
logger.remove()
logger.add(sys.stderr, level="INFO", format="{message}")


@click.group()
@click.option("--debug", is_flag=True, help="Enable debug logging", envvar="WM_DEBUG", default=False)
def cli(debug: bool) -> None:
    """Manage AI workloads, patches, and registration."""
    if debug:
        # Reset logger and set to DEBUG level with concise format
        logger.remove()
        logger.add(sys.stderr, level="DEBUG", format="{message}")
        logger.debug("Debug logging enabled")


@cli.command()
@click.option("--force", is_flag=True, help="Force reset of the repository")
@click.option("--skip-patches", is_flag=True, help="Skip patch application")
def init(force: bool = False, skip_patches: bool = False) -> None:
    """Initialize or reset the workloads repository and apply patches.

    This will:
    1. Reset the repository to a clean state
    2. Apply all available patches
    """
    # Initialize the repository (clone or reset)
    console.print("Initializing repository...")
    init_result = repository.initialize(force)

    if not init_result["success"]:
        # The message quotes PATCHED_VERSION's contents, so it must be escaped: an
        # unescaped "[/]" in that file would silently delete part of the very value
        # this diagnostic exists to quote, or raise MarkupError and lose the line.
        console.print(f"[bold red]❌ {escape(init_result['message'])}")
        sys.exit(1)
    else:
        console.print(f"✅ Repository initialized to commit {init_result['commit'][:8]}")

    if skip_patches:
        console.print("\nSkipping patch application...")
        return

    # Apply patches
    console.print("\nApplying patches to workloads...")
    results = patches.apply_patches()

    if not results:
        console.print("[bold yellow]⚠️ No patches applied[/]")
        return

    failed_count = sum(1 for r in results if not r["success"])

    if failed_count == 0:
        console.print("[bold green]✅ All patches applied successfully[/]")
        return

    console.print(f"[bold red]❌ {failed_count} out of {len(results)} patches could not be applied[/]")
    logger.debug("Detailed patch application results:")
    for result in results:
        if not result["success"]:
            console.print(f"  - {result['name']}: {result['message']}")

    # A failed 3-way merge leaves conflict markers in the vendored chart, so the tree
    # this command produces is not safe to package. Fail loudly rather than let a
    # downstream build ship a broken chart.
    console.print("[bold red]The workloads tree is left in a broken state. Fix the patches and re-run 'wm init'.[/]")
    sys.exit(1)


@cli.command()
def update():
    """Update the workloads repository and reapply patches."""
    # Check if repo exists
    workloads_dir = Path(config.WORKLOADS_DIR)
    if not workloads_dir.exists():
        click.echo("❌ Workloads repository not found. Run 'wm init' first.")
        sys.exit(1)

    # Update the repository
    console.print("Updating workloads repository...")
    update_result = repository.update_repo()

    if not update_result["success"]:
        console.print(f"[bold red]❌ {update_result['message']}")
        sys.exit(1)

    # Show commit information
    if update_result.get("updated", False):
        old_commit = update_result.get("old_commit", "")[:8]
        new_commit = update_result.get("commit", "")[:8]
        console.print(f"[bold green]✅ Updated from {old_commit} to {new_commit}[/]")

        # Show commit log if available
        if update_result.get("commit_log"):
            console.print("\n[bold]Commits included in this update:[/]")
            for line in update_result["commit_log"].splitlines():
                console.print(f"  {line}")
    else:
        console.print(f"[green]✅ Repository already up to date at commit {update_result['commit'][:8]}[/]")

    # Apply patches
    console.print("\nApplying patches to workloads...")
    results = patches.apply_patches()

    if not results:
        console.print("[bold yellow]⚠️ No patches applied[/]")
    else:
        success_count = sum(1 for r in results if r["success"])

        if success_count == len(results):
            console.print("[bold green]✅ All patches applied successfully[/]")
        else:
            failed_count = len(results) - success_count
            console.print(f"[bold yellow]⚠️ {failed_count} out of {len(results)} patches could not be applied[/]")
            # Show details for failed patches
            for result in results:
                if not result["success"]:
                    console.print(f"  - {result['name']}: {result['message']}")

        if success_count < len(results):
            # Unlike 'init', this command exits 0 on a patch failure. Conflicts are the
            # expected outcome of moving to a newer upstream version, and the operator
            # resolves them by hand in the tree this command just left behind. Nothing
            # packages that tree, so failing hard here would only break the workflow.
            console.print("\n[bold yellow]Some patches need to be updated for the new version of the workloads.[/]")
            console.print("Run 'wm create-patches' after fixing the conflicts.")


@cli.command(name="create-patches")
def create_patches():
    """Create patches from modified workloads."""
    for w in get_workloads():
        if w.is_changed:
            result = patches.create_patch(w.dir_name)
            if not result["success"]:
                console.print(f"[bold yellow]⚠️ Failed to create patch for {w.dir_name}: {result['error']}[/]")

    # Get list of created patches
    created_patches = [p for p in patches.get_available_patches()]

    # Show a concise summary
    if len(created_patches) > 0:
        console.print(f"[bold green]✅ Created {len(created_patches)} patches[/]")

        # Only show the names, not the full paths
        if len(created_patches) <= 5:
            for patch in created_patches:
                console.print(f"  - {patch}")
        else:
            for patch in created_patches[:3]:
                console.print(f"  - {patch}")
            console.print(f"  - ... and {len(created_patches) - 3} more")
    else:
        console.print("[bold yellow]⚠️ No patches created[/]")


@cli.command()
@click.argument("workload", required=False)
@click.option(
    "--url", help="API URL to register to (overrides config)", envvar="WM_API_URL", default=config.API_BASE_URL
)
@click.option(
    "--yes",
    is_flag=True,
    help="Skip all confirmations and register without prompting",
    envvar="WM_SKIP_CONFIRMATIONS",
    default=False,
)
def register(workload: str | None, url: str, yes: bool = False) -> None:
    """Register a workload template to the service.

    If WORKLOAD is not provided, you will be prompted to select from available workloads.
    If WORKLOAD is 'all', a list of all registerable workloads will be displayed.
    """
    # Check repository and token
    dir_status = repository.check_directories()
    if not dir_status["workloads_repo_exists"]:
        console.print("[bold red]⚠️ Workloads repository not found. Cloning repo...[/]")
        init_result = repository.initialize(force=True)

        # Without this check a failed clone falls through to patching an absent or partial
        # tree, and the operator sees a patch error instead of the clone error that caused it.
        if not init_result["success"]:
            console.print(f"[bold red]❌ {init_result['message']}[/]")
            sys.exit(1)

        results = patches.apply_patches()

        failed_count = sum(1 for r in results if not r["success"])
        if failed_count > 0:
            console.print(f"[bold red]❌ {failed_count} out of {len(results)} patches could not be applied[/]")
            for result in results:
                if not result["success"]:
                    console.print(f"  - {result['name']}: {result['message']}")

            # A failed patch leaves conflict markers in the vendored chart, so registering it
            # now would publish unparseable YAML, the exact failure this clone step exists to prevent.
            console.print(
                "[bold red]The workloads tree is left in a broken state. Fix the patches and re-run 'wm init'.[/]"
            )
            sys.exit(1)

    token = os.environ.get("TOKEN")
    if not token:
        console.print("[bold red]❌ TOKEN environment variable not set[/]")
        console.print("[yellow]Note: Can only display available workloads without a token[/]")

    # Get registerable workloads
    registerable_workloads: list[Workload] = get_registerable_workloads()
    if not registerable_workloads:
        console.print("[bold red]❌ No registerable workloads found.[/]")
        console.print("[yellow]Each workload needs a metadata file with 'id' and 'type' fields at:[/]")
        console.print("[yellow]<workload>/helm/overrides/dev-center/_metadata.yaml[/]")

        # Check if any workloads exist at all
        all_workloads = get_workloads()
        if all_workloads:
            console.print("\n[bold]Available workloads without proper metadata:[/]")
            for w in all_workloads:
                console.print(f"  - {w.dir_name}")
        sys.exit(1)

    # If no workload is provided but --yes flag is set, treat as 'all'
    if not workload and yes:
        workload = "all"
        console.print("[bold]--yes flag provided, registering all workloads...[/]")

    # Check if the provided workload exists
    if workload and workload != "all":
        workload_exists = False
        for w in registerable_workloads:
            if w.dir_name == workload:
                workload_exists = True
                break

        if not workload_exists:
            console.print(f"[bold red]❌ Workload '{workload}' not found[/]")
            console.print("\n[bold]Available workloads:[/]")
            for w in registerable_workloads:
                console.print(f"  - {w.dir_name} (Type: {w.type}, Chart: {w.chart_name})")
            sys.exit(1)

    # If workload is 'all', either list or register all workloads
    if workload == "all":
        # Confirm before registering all workloads
        console.print(f"[bold]Preparing to register {len(registerable_workloads)} workloads:[/]")
        for w in registerable_workloads:
            console.print(f"  - {w.dir_name} (Type: {w.type}, Chart: {w.chart_name})")

        if not yes and not click.confirm("\nDo you want to proceed with registering ALL workloads?"):
            console.print("Registration cancelled.")
            sys.exit(0)

        # Register all workloads
        success_count = 0
        failed_workloads = []

        for w in registerable_workloads:
            console.print(f"\n[bold]Registering workload: {w.dir_name}[/]")

            result = registration.register_workload(w.dir_name, httpx.URL(url))
            utils.display_registration_result(result, console)

            # Check if there were any failed files in the registration
            failed_files = result.stats.failed

            if result.success and failed_files == 0:
                success_count += 1
            else:
                failed_workloads.append(w)
                # If there were failed files but the overall result is success, update the status
                if result.success and failed_files > 0:
                    console.print(
                        f"[yellow]⚠️  Workload {w.dir_name} had {failed_files} failed file(s) and will be marked as failed[/]"
                    )

        # Show summary
        console.print("\n[bold]Registration summary:[/]")
        console.print(f"Total workloads: {len(registerable_workloads)}")
        console.print(f"Successfully registered: {success_count}")

        if failed_workloads:
            console.print(f"[bold red]Failed workloads: {len(failed_workloads)}[/]")
            for failed in failed_workloads:
                console.print(f"  - {failed.dir_name}")

            # A partial registration leaves the service holding an incomplete set of charts.
            # Exiting 0 here would let an automated caller treat that as a finished rollout.
            console.print("[bold red]❌ Some workloads could not be registered[/]")
            sys.exit(1)

        console.print("[bold green]✅ All workloads registered successfully[/]")
        sys.exit(0)

    # If no workload is provided and no --yes flag, show interactive selection
    elif not workload:
        workload_choices = [w.dir_name for w in registerable_workloads]
        questions = [
            inquirer.List("workload", message="Select workload to register", choices=workload_choices),
        ]
        answers = inquirer.prompt(questions)
        if not answers:
            console.print("[bold red]❌ No workload selected[/]")
            sys.exit(1)
        workload = answers["workload"]

    # If a specific workload is provided (not 'all' and not from interactive selection)
    if workload != "all":
        console.print(f"\n[bold]Registering workload: {workload}[/]")
        result = registration.register_workload(workload, httpx.URL(url))  # type: ignore
        utils.display_registration_result(result, console)

        if not result.success:
            console.print(f"[bold red]❌ Failed to register workload: {result.error or 'Unknown error'}[/]")
            sys.exit(1)
        else:
            console.print(f"[bold green]✅ Successfully registered workload: {workload}[/]")
            sys.exit(0)


@cli.command()
def status():
    """Show the status of workloads and patches."""
    # Get directory status and workload objects
    dir_status = repository.check_directories()
    workload_objects = get_workloads()

    # Display directory status
    console.print(f"Workloads Repository: {'✅ Exists' if dir_status['workloads_repo_exists'] else '❌ Not found'}")
    console.print(f"Patches Directory: {'✅ Exists' if dir_status['patches_dir_exists'] else '❌ Not found'}")

    # Create a table for workloads
    if workload_objects:
        console.print("\n[bold]Workloads Status:[/]")

        # Create a table
        table = rich.table.Table(show_header=True, header_style="bold")
        table.add_column("Workload")
        table.add_column("Metadata")
        table.add_column("Patched")

        # Add rows to the table - workloads are already sorted with metadata first
        for w in workload_objects:
            # Style the workload name based on metadata status
            workload_style = "[green]" if w.metadata else "[grey70]"

            table.add_row(
                f"{workload_style}{w.dir_name}[/]",
                "✅" if w.metadata else "❌",
                "[orange3]✓[/]" if w.has_patch else "",
            )

        console.print(table)
    else:
        console.print("\nWorkloads: None found")

    git_status = repository.get_repo_status()
    if "error" in git_status:
        console.print(f"\nGit Status: ❌ {git_status['error']}")
    else:
        console.print("\nGit Status:")
        console.print(f"  Branch: {git_status['branch']}")
        console.print(f"  Commit: {git_status['commit']}")
        # Only show the first line of the commit message
        first_line = git_status["commit_message"].split("\n")[0].strip()
        console.print(f"  Message: {first_line}")

        # Get changed workloads
        changed_workloads, non_workload_changes = get_changed_workloads()
        available_patches = patches.get_available_patches()

        # Check if changes match patches
        changes_match = check_patches_match_changes(changed_workloads, available_patches, non_workload_changes)

        # Enhanced display for repository state
        if git_status["is_dirty"]:
            if changes_match:
                console.print("  [bold green]Status: Changes match current patches[/]")
            else:
                console.print("  [bold yellow]Status: Repository has uncommitted changes[/]")

            # Show which workloads have changes
            if changed_workloads:
                console.print("  [bold]Changed workloads:[/]")
                for changed_workload in sorted(changed_workloads):
                    console.print(f"    - {changed_workload}")

            # Show non-workload changes if any exist
            if non_workload_changes:
                console.print("  [bold]Non-workload changes:[/]")
                for change in non_workload_changes[:5]:  # Show only first 5 to avoid clutter
                    console.print(f"    - {change}")
                if len(non_workload_changes) > 5:
                    console.print(f"    ... and {len(non_workload_changes) - 5} more")
        else:
            console.print("  [bold green]Status: Clean[/]")


def main():
    """Entry point for the CLI."""
    cli()


if __name__ == "__main__":
    main()
