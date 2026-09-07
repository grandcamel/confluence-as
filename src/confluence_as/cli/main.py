"""Main CLI entry point for Confluence Assistant Skills."""

from __future__ import annotations

from importlib import import_module
from pathlib import Path

import click
from as_engine.help import render_help

from confluence_as import __version__
from confluence_as.cli.commands.help_cmds import HelpGroup, surface_map


class LazyGroups(HelpGroup):
    """Load only the selected command family and its indexed migration hints."""

    modules = {
        "admin": ("admin_cmds", "admin"),
        "analytics": ("analytics_cmds", "analytics"),
        "api": ("api_cmds", "api"),
        "attachment": ("attachment_cmds", "attachment"),
        "bulk": ("bulk_cmds", "bulk"),
        "help": ("help_cmds", "help_command"),
        "hierarchy": ("hierarchy_cmds", "hierarchy"),
        "jira": ("jira_cmds", "jira"),
        "label": ("label_cmds", "label"),
        "ops": ("ops_cmds", "ops"),
        "page": ("page_cmds", "page"),
        "permission": ("permission_cmds", "permission"),
        "property": ("property_cmds", "property_cmd"),
        "search": ("search_cmds", "search"),
        "template": ("template_cmds", "template"),
    }
    migration_groups = {"comment", "space", "watch"}

    def list_commands(self, ctx):
        return sorted(set(self.modules) | self.migration_groups)

    def get_command(self, ctx, name):
        if name in self.commands:
            return self.commands[name]
        if name not in self.modules and name not in self.migration_groups:
            return None
        if name in self.modules:
            module, symbol = self.modules[name]
            command = getattr(
                import_module("confluence_as.cli.commands." + module), symbol
            )
        else:
            from confluence_as.cli.legacy import MigrationGroup

            command = MigrationGroup(name, help="Legacy migration hints.")
        if name not in {"api", "help"}:
            from as_engine.index import ProductIndexes

            from confluence_as.cli.legacy import records, register

            indexes = ProductIndexes(Path(__file__).parents[1] / "_generated")
            register(
                command, records([indexes.get("v2"), indexes.get("v1")]), prefix=name
            )
        self.add_command(command, name)
        return command


@click.group(cls=LazyGroups, invoke_without_command=True)
@click.version_option(version=__version__, prog_name="confluence-as")
@click.option(
    "--output",
    "-o",
    type=click.Choice(["text", "json"]),
    default="text",
    help="Output format.",
)
@click.option(
    "--verbose",
    "-v",
    is_flag=True,
    help="Enable verbose output.",
)
@click.option(
    "--quiet",
    "-q",
    is_flag=True,
    help="Suppress non-essential output.",
)
@click.pass_context
def cli(
    ctx: click.Context,
    output: str,
    verbose: bool,
    quiet: bool,
) -> None:
    """Confluence Assistant Skills CLI.

    A command-line interface for interacting with Confluence Cloud.

    Use --help on any command for more information.

    Examples:

        confluence-as api describe getPageById

        confluence-as api call searchByCQL --cql "space = DOCS AND type = page"

        confluence-as api search spaces
    """
    # Store options in context for subcommands
    ctx.ensure_object(dict)
    ctx.obj["output"] = output
    ctx.obj["verbose"] = verbose
    ctx.obj["quiet"] = quiet

    if ctx.invoked_subcommand is None:
        click.echo(render_help(surface_map()))


if __name__ == "__main__":
    cli()
