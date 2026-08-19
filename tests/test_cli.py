"""Test suite for Confluence CLI.

Tests the CLI commands with mocked API client. After the CLI-only refactoring,
commands make direct API calls rather than delegating to skill scripts.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from confluence_as.cli.main import cli


@pytest.fixture
def runner() -> CliRunner:
    """Create a CLI test runner."""
    return CliRunner()


class TestCLIRoot:
    """Test the root CLI command."""

    def test_help(self, runner: CliRunner) -> None:
        """Test --help flag."""
        result = runner.invoke(cli, ["--help"])
        assert result.exit_code == 0
        assert "Confluence Assistant Skills CLI" in result.output
        assert "page" in result.output
        assert "space" in result.output
        assert "search" in result.output

    def test_version(self, runner: CliRunner) -> None:
        """Test --version flag."""
        result = runner.invoke(cli, ["--version"])
        assert result.exit_code == 0
        assert "confluence-as, version" in result.output

    def test_no_command_shows_help(self, runner: CliRunner) -> None:
        """Test that no command shows help."""
        result = runner.invoke(cli, [])
        assert result.exit_code == 0
        assert "Usage:" in result.output


class TestPageCommands:
    """Test page command group."""

    def test_page_help(self, runner: CliRunner) -> None:
        """Test page --help."""
        result = runner.invoke(cli, ["page", "--help"])
        assert result.exit_code == 0
        assert "Manage Confluence pages" in result.output
        assert "get" in result.output
        assert "create" in result.output
        assert "update" in result.output
        assert "delete" in result.output

    def test_page_get(self, runner: CliRunner) -> None:
        """Test page get command."""
        with patch("confluence_as.cli.cli_utils.get_confluence_client") as mock:
            client = MagicMock()
            mock.return_value = client
            client.get.return_value = {
                "id": "12345",
                "title": "Test Page",
                "status": "current",
                "spaceId": "123",
                "_links": {"webui": "/wiki/test"},
            }
            result = runner.invoke(cli, ["page", "get", "12345"])
            assert result.exit_code == 0
            client.get.assert_called()

    def test_page_get_with_body(self, runner: CliRunner) -> None:
        """Test page get command with --body option."""
        with patch("confluence_as.cli.cli_utils.get_confluence_client") as mock:
            client = MagicMock()
            mock.return_value = client
            client.get.return_value = {
                "id": "12345",
                "title": "Test Page",
                "status": "current",
                "spaceId": "123",
                "body": {"storage": {"value": "<p>Content</p>"}},
                "_links": {"webui": "/wiki/test"},
            }
            result = runner.invoke(cli, ["page", "get", "12345", "--body"])
            assert result.exit_code == 0

    def test_page_create(self, runner: CliRunner) -> None:
        """Test page create command."""
        with patch("confluence_as.cli.cli_utils.get_confluence_client") as mock:
            client = MagicMock()
            mock.return_value = client
            # Mock space lookup by key
            client.paginate.return_value = iter(
                [{"id": "100", "key": "DOCS", "name": "Documentation"}]
            )
            # Mock page creation
            client.post.return_value = {
                "id": "12345",
                "title": "Test Page",
                "status": "current",
                "spaceId": "100",
                "_links": {"webui": "/wiki/test"},
            }
            result = runner.invoke(
                cli,
                [
                    "page",
                    "create",
                    "--space",
                    "DOCS",
                    "--title",
                    "Test Page",
                    "--body",
                    "Test content",
                ],
            )
            assert result.exit_code == 0
            client.post.assert_called()

    def test_page_delete(self, runner: CliRunner) -> None:
        """Test page delete command."""
        with patch("confluence_as.cli.cli_utils.get_confluence_client") as mock:
            client = MagicMock()
            mock.return_value = client
            # Mock getting page info first
            client.get.return_value = {
                "id": "12345",
                "title": "Test Page",
                "status": "current",
            }
            client.delete.return_value = None
            result = runner.invoke(cli, ["page", "delete", "12345", "--force"])
            assert result.exit_code == 0
            client.delete.assert_called()


class TestSpaceCommands:
    """Test space command group."""

    def test_space_help(self, runner: CliRunner) -> None:
        """Test space --help."""
        result = runner.invoke(cli, ["space", "--help"])
        assert result.exit_code == 0
        assert "Manage Confluence spaces" in result.output

    def test_space_list(self, runner: CliRunner) -> None:
        """Test space list command."""
        with patch("confluence_as.cli.cli_utils.get_confluence_client") as mock:
            client = MagicMock()
            mock.return_value = client
            client.paginate.return_value = iter(
                [
                    {
                        "id": "1",
                        "key": "DOCS",
                        "name": "Documentation",
                        "type": "global",
                    },
                    {
                        "id": "2",
                        "key": "KB",
                        "name": "Knowledge Base",
                        "type": "global",
                    },
                ]
            )
            result = runner.invoke(cli, ["space", "list"])
            assert result.exit_code == 0
            client.paginate.assert_called()

    def test_space_get(self, runner: CliRunner) -> None:
        """Test space get command."""
        with patch("confluence_as.cli.cli_utils.get_confluence_client") as mock:
            client = MagicMock()
            mock.return_value = client
            client.paginate.return_value = iter(
                [{"id": "1", "key": "DOCS", "name": "Documentation", "type": "global"}]
            )
            result = runner.invoke(cli, ["space", "get", "DOCS"])
            assert result.exit_code == 0
            client.paginate.assert_called()


class TestSearchCommands:
    """Test search command group."""

    def test_search_help(self, runner: CliRunner) -> None:
        """Test search --help."""
        result = runner.invoke(cli, ["search", "--help"])
        assert result.exit_code == 0
        assert "Search Confluence content" in result.output

    def test_search_cql(self, runner: CliRunner) -> None:
        """Test search cql command."""
        with patch("confluence_as.cli.cli_utils.get_confluence_client") as mock:
            client = MagicMock()
            mock.return_value = client
            client.paginate.return_value = iter(
                [{"content": {"id": "1", "title": "Page 1", "type": "page"}}]
            )
            result = runner.invoke(cli, ["search", "cql", "space = DOCS"])
            assert result.exit_code == 0
            client.paginate.assert_called()

    def test_search_cql_with_options(self, runner: CliRunner) -> None:
        """Test search cql command with options."""
        with patch("confluence_as.cli.cli_utils.get_confluence_client") as mock:
            client = MagicMock()
            mock.return_value = client
            client.paginate.return_value = iter([])
            result = runner.invoke(
                cli,
                ["search", "cql", "space = DOCS", "--limit", "50"],
            )
            assert result.exit_code == 0


class TestCommentCommands:
    """Test comment command group."""

    def test_comment_list(self, runner: CliRunner) -> None:
        """Test comment list command."""
        with patch("confluence_as.cli.cli_utils.get_confluence_client") as mock:
            client = MagicMock()
            mock.return_value = client
            client.get.return_value = {"results": [], "_links": {}}
            result = runner.invoke(cli, ["comment", "list", "12345"])
            assert result.exit_code == 0
            client.get.assert_called()

    def test_comment_add(self, runner: CliRunner) -> None:
        """Test comment add command."""
        with patch("confluence_as.cli.cli_utils.get_confluence_client") as mock:
            client = MagicMock()
            mock.return_value = client
            client.post.return_value = {
                "id": "999",
                "body": {"storage": {"value": "Test comment"}},
            }
            result = runner.invoke(cli, ["comment", "add", "12345", "Test comment"])
            assert result.exit_code == 0
            client.post.assert_called()


class TestLabelCommands:
    """Test label command group."""

    def test_label_add_single(self, runner: CliRunner) -> None:
        """Test label add command with single label (positional argument)."""
        with patch("confluence_as.cli.cli_utils.get_confluence_client") as mock:
            client = MagicMock()
            mock.return_value = client
            client.post.return_value = {"results": [{"name": "documentation"}]}
            result = runner.invoke(cli, ["label", "add", "12345", "documentation"])
            assert result.exit_code == 0
            client.post.assert_called()

    def test_label_add_multiple(self, runner: CliRunner) -> None:
        """Test label add command with multiple labels (positional arguments)."""
        with patch("confluence_as.cli.cli_utils.get_confluence_client") as mock:
            client = MagicMock()
            mock.return_value = client
            client.post.return_value = {
                "results": [{"name": "doc"}, {"name": "approved"}]
            }
            result = runner.invoke(
                cli, ["label", "add", "12345", "doc", "approved", "v2"]
            )
            assert result.exit_code == 0
            client.post.assert_called()

    def test_label_add_requires_at_least_one_label(self, runner: CliRunner) -> None:
        """Test label add command requires at least one label."""
        result = runner.invoke(cli, ["label", "add", "12345"])
        assert result.exit_code != 0
        # Should fail with validation error about missing labels
        assert "label" in result.output.lower() or "required" in result.output.lower()

    def test_label_remove(self, runner: CliRunner) -> None:
        """Test label remove command (positional arguments)."""
        with patch("confluence_as.cli.cli_utils.get_confluence_client") as mock:
            client = MagicMock()
            mock.return_value = client
            client.delete.return_value = None
            result = runner.invoke(cli, ["label", "remove", "12345", "draft"])
            assert result.exit_code == 0
            client.delete.assert_called()

    def test_label_remove_requires_label_name(self, runner: CliRunner) -> None:
        """Test label remove command requires label name argument."""
        result = runner.invoke(cli, ["label", "remove", "12345"])
        assert result.exit_code != 0
        assert "Missing argument" in result.output


class TestAttachmentCommands:
    """Test attachment command group."""

    def test_attachment_list(self, runner: CliRunner) -> None:
        """Test attachment list command."""
        with patch("confluence_as.cli.cli_utils.get_confluence_client") as mock:
            client = MagicMock()
            mock.return_value = client
            client.get.return_value = {"results": [], "_links": {}}
            result = runner.invoke(cli, ["attachment", "list", "12345"])
            assert result.exit_code == 0
            client.get.assert_called()


class TestHierarchyCommands:
    """Test hierarchy command group."""

    def test_hierarchy_children(self, runner: CliRunner) -> None:
        """Test hierarchy children command."""
        with patch("confluence_as.cli.cli_utils.get_confluence_client") as mock:
            client = MagicMock()
            mock.return_value = client
            client.get.return_value = {"results": [], "_links": {}}
            result = runner.invoke(cli, ["hierarchy", "children", "12345"])
            assert result.exit_code == 0
            client.get.assert_called()

    def test_hierarchy_tree(self, runner: CliRunner) -> None:
        """Test hierarchy tree command."""
        with patch("confluence_as.cli.cli_utils.get_confluence_client") as mock:
            client = MagicMock()
            mock.return_value = client
            # Mock get page
            client.get.side_effect = [
                {"id": "12345", "title": "Root Page", "status": "current"},
                {"results": [], "_links": {}},  # Children request
            ]
            result = runner.invoke(
                cli, ["hierarchy", "tree", "12345", "--max-depth", "5"]
            )
            assert result.exit_code == 0


class TestAnalyticsCommands:
    """Test analytics command group."""

    def test_analytics_views(self, runner: CliRunner) -> None:
        """Test analytics views command."""
        with patch("confluence_as.cli.cli_utils.get_confluence_client") as mock:
            client = MagicMock()
            mock.return_value = client
            client.get.return_value = {"id": "12345", "count": 100}
            result = runner.invoke(cli, ["analytics", "views", "12345"])
            assert result.exit_code == 0
            client.get.assert_called()


class TestWatchCommands:
    """Test watch command group."""

    def test_watch_page(self, runner: CliRunner) -> None:
        """Test watch page command."""
        with patch("confluence_as.cli.cli_utils.get_confluence_client") as mock:
            client = MagicMock()
            mock.return_value = client
            client.post.return_value = {}
            result = runner.invoke(cli, ["watch", "page", "12345"])
            assert result.exit_code == 0
            client.post.assert_called()


class TestTemplateCommands:
    """Test template command group."""

    def test_template_list(self, runner: CliRunner) -> None:
        """Test template list command."""
        with patch("confluence_as.cli.cli_utils.get_confluence_client") as mock:
            client = MagicMock()
            mock.return_value = client
            client.paginate.return_value = iter([])
            result = runner.invoke(cli, ["template", "list"])
            assert result.exit_code == 0
            client.paginate.assert_called()


class TestPropertyCommands:
    """Test property command group."""

    def test_property_set(self, runner: CliRunner) -> None:
        """Test property set command."""
        with patch("confluence_as.cli.cli_utils.get_confluence_client") as mock:
            client = MagicMock()
            mock.return_value = client
            # Mock get - first call gets page, second could be property check
            client.get.return_value = {
                "id": "12345",
                "title": "Test Page",
                "status": "current",
            }
            client.post.return_value = {"key": "mykey", "value": "myvalue"}
            result = runner.invoke(
                cli, ["property", "set", "12345", "mykey", "--value", "myvalue"]
            )
            assert result.exit_code == 0


class TestPermissionCommands:
    """Test permission command group."""

    def test_permission_page_get(self, runner: CliRunner) -> None:
        """Test permission page get command."""
        with patch("confluence_as.cli.cli_utils.get_confluence_client") as mock:
            client = MagicMock()
            mock.return_value = client
            client.get.return_value = {"results": [], "_links": {}}
            result = runner.invoke(cli, ["permission", "page", "get", "12345"])
            assert result.exit_code == 0
            client.get.assert_called()

    def test_permission_space_get(self, runner: CliRunner) -> None:
        """Test permission space get command."""
        with patch("confluence_as.cli.cli_utils.get_confluence_client") as mock:
            client = MagicMock()
            mock.return_value = client
            # Mock space lookup
            client.paginate.return_value = iter([{"id": "100", "key": "DOCS"}])
            # Mock permissions
            client.get.return_value = {"results": [], "_links": {}}
            result = runner.invoke(cli, ["permission", "space", "get", "DOCS"])
            assert result.exit_code == 0


class TestJiraCommands:
    """Test jira command group."""

    def test_jira_link(self, runner: CliRunner) -> None:
        """Test jira link command."""
        with patch("confluence_as.cli.cli_utils.get_confluence_client") as mock:
            client = MagicMock()
            mock.return_value = client
            # Mock page get
            client.get.return_value = {
                "id": "12345",
                "title": "Test Page",
                "body": {"storage": {"value": "<p>Content</p>"}},
                "version": {"number": 1},
            }
            # Mock page update
            client.put.return_value = {"id": "12345", "title": "Test Page"}
            result = runner.invoke(
                cli,
                [
                    "jira",
                    "link",
                    "12345",
                    "PROJ-123",
                    "--jira-url",
                    "https://jira.example.com",
                ],
            )
            assert result.exit_code == 0


class TestAdminCommands:
    """Test admin command group."""

    def test_admin_help(self, runner: CliRunner) -> None:
        """Test admin help output."""
        result = runner.invoke(cli, ["admin", "--help"])
        assert result.exit_code == 0
        assert "user" in result.output
        assert "group" in result.output
        assert "space" in result.output
        assert "template" in result.output

    def test_admin_user_search(self, runner: CliRunner) -> None:
        """Test admin user search command."""
        with patch("confluence_as.cli.cli_utils.get_confluence_client") as mock:
            client = MagicMock()
            mock.return_value = client
            client.get.return_value = {
                "results": [
                    {
                        "accountId": "123",
                        "displayName": "Test User",
                        "email": "test@example.com",
                    }
                ]
            }
            result = runner.invoke(cli, ["admin", "user", "search", "test"])
            assert result.exit_code == 0

    def test_admin_group_list(self, runner: CliRunner) -> None:
        """Test admin group list command."""
        with patch("confluence_as.cli.cli_utils.get_confluence_client") as mock:
            client = MagicMock()
            mock.return_value = client
            client.get.return_value = {
                "results": [{"name": "confluence-users", "id": "group-1"}],
                "_links": {},
            }
            result = runner.invoke(cli, ["admin", "group", "list"])
            assert result.exit_code == 0

    def test_admin_template_list(self, runner: CliRunner) -> None:
        """Test admin template list command."""
        with patch("confluence_as.cli.cli_utils.get_confluence_client") as mock:
            client = MagicMock()
            mock.return_value = client
            client.paginate.return_value = iter([{"id": "100", "key": "DOCS"}])
            client.get.return_value = {
                "results": [{"templateId": "1", "name": "Meeting Notes"}],
                "_links": {},
            }
            result = runner.invoke(
                cli, ["admin", "template", "list", "--space", "DOCS"]
            )
            assert result.exit_code == 0


class TestBulkCommands:
    """Test bulk command group."""

    def test_bulk_help(self, runner: CliRunner) -> None:
        """Test bulk help output."""
        result = runner.invoke(cli, ["bulk", "--help"])
        assert result.exit_code == 0
        assert "label" in result.output
        assert "move" in result.output
        assert "delete" in result.output

    def test_bulk_label_add_dry_run(self, runner: CliRunner) -> None:
        """Test bulk label add with dry-run."""
        with patch("confluence_as.cli.cli_utils.get_confluence_client") as mock:
            client = MagicMock()
            mock.return_value = client
            client.paginate.return_value = iter(
                [
                    {"content": {"id": "1", "title": "Page 1"}},
                    {"content": {"id": "2", "title": "Page 2"}},
                ]
            )
            result = runner.invoke(
                cli,
                [
                    "bulk",
                    "label",
                    "add",
                    "--labels",
                    "test-label",
                    "--cql",
                    "space=TEST",
                    "--dry-run",
                ],
            )
            assert result.exit_code == 0
            assert "dry" in result.output.lower() or "would" in result.output.lower()

    def test_bulk_delete_dry_run(self, runner: CliRunner) -> None:
        """Test bulk delete with dry-run."""
        with patch("confluence_as.cli.cli_utils.get_confluence_client") as mock:
            client = MagicMock()
            mock.return_value = client
            client.paginate.return_value = iter(
                [
                    {"content": {"id": "1", "title": "Page 1"}},
                ]
            )
            result = runner.invoke(
                cli,
                [
                    "bulk",
                    "delete",
                    "--cql",
                    "space=TEST AND label=delete-me",
                    "--dry-run",
                ],
            )
            assert result.exit_code == 0


class TestOpsCommands:
    """Test ops command group."""

    def test_ops_help(self, runner: CliRunner) -> None:
        """Test ops help output."""
        result = runner.invoke(cli, ["ops", "--help"])
        assert result.exit_code == 0
        assert "cache" in result.output
        assert "health" in result.output

    def test_ops_cache_status(self, runner: CliRunner) -> None:
        """Test ops cache-status command."""
        result = runner.invoke(cli, ["ops", "cache-status"])
        assert result.exit_code == 0
        # Should output cache statistics
        assert "cache" in result.output.lower() or "status" in result.output.lower()

    def test_ops_health_check(self, runner: CliRunner) -> None:
        """Test ops health-check command."""
        with patch("confluence_as.cli.cli_utils.get_confluence_client") as mock:
            client = MagicMock()
            mock.return_value = client
            client.get.return_value = {"accountId": "123", "displayName": "Test User"}
            result = runner.invoke(cli, ["ops", "health-check"])
            assert result.exit_code == 0


class TestGlobalOptions:
    """Test global CLI options."""

    def test_output_option(self, runner: CliRunner) -> None:
        """Test --output global option."""
        with patch("confluence_as.cli.cli_utils.get_confluence_client") as mock:
            client = MagicMock()
            mock.return_value = client
            client.paginate.return_value = iter([])
            result = runner.invoke(cli, ["--output", "json", "space", "list"])
            assert result.exit_code == 0


class TestErrorHandling:
    """Test CLI error handling."""

    def test_api_error_handling(self, runner: CliRunner) -> None:
        """Test that API errors are handled gracefully."""
        with patch("confluence_as.cli.cli_utils.get_confluence_client") as mock:
            client = MagicMock()
            mock.return_value = client
            from confluence_as import NotFoundError

            client.get.side_effect = NotFoundError("Page not found")
            result = runner.invoke(cli, ["page", "get", "99999"])
            assert result.exit_code != 0
            assert (
                "not found" in result.output.lower() or "error" in result.output.lower()
            )

    def test_missing_required_argument(self, runner: CliRunner) -> None:
        """Test missing required argument."""
        result = runner.invoke(cli, ["page", "get"])
        assert result.exit_code != 0
        assert "Missing argument" in result.output or "Error" in result.output


class TestGlobalOutputOption:
    """Regression tests: global -o/--output propagates to subcommands."""

    PAGE = {
        "id": "12345",
        "title": "Test Page",
        "status": "current",
        "spaceId": "123",
        "_links": {"webui": "/wiki/test"},
    }

    def _invoke(self, runner: CliRunner, args: list[str]):
        with patch("confluence_as.cli.cli_utils.get_confluence_client") as mock:
            client = MagicMock()
            mock.return_value = client
            client.get.return_value = dict(self.PAGE)
            return runner.invoke(cli, args)

    def test_global_output_json(self, runner: CliRunner) -> None:
        """Global -o json makes subcommands emit JSON."""
        result = self._invoke(runner, ["-o", "json", "page", "get", "12345"])
        assert result.exit_code == 0
        assert '"id": "12345"' in result.output

    def test_global_and_local_placements_equivalent(self, runner: CliRunner) -> None:
        """-o json before or after the subcommand produces the same output."""
        global_result = self._invoke(runner, ["-o", "json", "page", "get", "12345"])
        local_result = self._invoke(runner, ["page", "get", "12345", "-o", "json"])
        assert global_result.exit_code == local_result.exit_code == 0
        assert global_result.output == local_result.output

    def test_local_output_overrides_global(self, runner: CliRunner) -> None:
        """An explicit subcommand -o text wins over a global -o json."""
        result = self._invoke(
            runner, ["-o", "json", "page", "get", "12345", "-o", "text"]
        )
        assert result.exit_code == 0
        assert '"id": "12345"' not in result.output
        assert "Test Page" in result.output

    def test_default_remains_text(self, runner: CliRunner) -> None:
        """With no --output anywhere, text output is used."""
        result = self._invoke(runner, ["page", "get", "12345"])
        assert result.exit_code == 0
        assert '"id": "12345"' not in result.output


class TestPageCreate404Disambiguation:
    """Regression tests: page create 404 permission-denied vs genuine 404."""

    SPACE = {"id": "100", "key": "DOCS", "name": "Documentation"}

    CREATE_ARGS = [
        "page",
        "create",
        "--space",
        "DOCS",
        "--title",
        "Test Page",
        "--body",
        "content",
    ]

    def _client_probe_get(self, account_id: str = "user-1"):
        def _get(endpoint, **kwargs):
            if endpoint == "/rest/api/user/current":
                return {"accountId": account_id, "displayName": "User One"}
            if endpoint == "/rest/api/user/memberof":
                return {"results": [{"id": "group-1", "name": "team"}]}
            raise AssertionError(f"unexpected GET {endpoint}")

        return _get

    def test_missing_create_grant_reports_permission_error(
        self, runner: CliRunner
    ) -> None:
        """A 404 with no create-page grant surfaces as a permission problem."""
        from confluence_as import NotFoundError

        with patch("confluence_as.cli.cli_utils.get_confluence_client") as mock:
            client = MagicMock()
            mock.return_value = client
            client.paginate.side_effect = [iter([self.SPACE]), iter([])]
            client.post.side_effect = NotFoundError("Not found")
            client.get.side_effect = self._client_probe_get()
            result = runner.invoke(cli, self.CREATE_ARGS)
        assert result.exit_code != 0
        assert "no create-page permission" in result.stderr

    def test_genuine_404_is_preserved_when_create_granted(
        self, runner: CliRunner
    ) -> None:
        """A 404 with a create grant present stays a not-found error."""
        from confluence_as import NotFoundError

        create_grant = {
            "principal": {"type": "user", "id": "user-1"},
            "operation": {"key": "create", "targetType": "page"},
        }
        with patch("confluence_as.cli.cli_utils.get_confluence_client") as mock:
            client = MagicMock()
            mock.return_value = client
            client.paginate.side_effect = [iter([self.SPACE]), iter([create_grant])]
            client.post.side_effect = NotFoundError("Parent page not found")
            client.get.side_effect = self._client_probe_get()
            result = runner.invoke(cli, self.CREATE_ARGS)
        assert result.exit_code != 0
        assert "no create-page permission" not in result.stderr
        assert "not found" in result.stderr.lower()

    def test_unknown_grants_preserve_not_found(self, runner: CliRunner) -> None:
        """If grants cannot be read, the original 404 is re-raised."""
        from confluence_as import ConfluenceError, NotFoundError

        with patch("confluence_as.cli.cli_utils.get_confluence_client") as mock:
            client = MagicMock()
            mock.return_value = client
            client.paginate.side_effect = [
                iter([self.SPACE]),
                ConfluenceError("permissions unreadable"),
            ]
            client.post.side_effect = NotFoundError("Not found")
            client.get.side_effect = self._client_probe_get()
            result = runner.invoke(cli, self.CREATE_ARGS)
        assert result.exit_code != 0
        assert "no create-page permission" not in result.stderr
        assert "not found" in result.stderr.lower()


class TestAdminPermissionsCheck:
    """Regression tests: admin permissions check derives real grant results."""

    SPACE = {"id": "100", "key": "DOCS", "name": "Documentation"}

    GRANTS = [
        {
            "principal": {"type": "user", "id": "user-1"},
            "operation": {"key": "read", "targetType": "space"},
        },
        {
            "principal": {"type": "group", "id": "group-1"},
            "operation": {"key": "create", "targetType": "page"},
        },
        {
            "principal": {"type": "role", "id": "some-role"},
            "operation": {"key": "export", "targetType": "space"},
        },
    ]

    def _client(self):
        client = MagicMock()

        def _get(endpoint, **kwargs):
            if endpoint == "/rest/api/user/current":
                return {"accountId": "user-1", "displayName": "User One"}
            if endpoint == "/rest/api/user/memberof":
                return {"results": [{"id": "group-1", "name": "team"}]}
            raise AssertionError(f"unexpected GET {endpoint}")

        client.get.side_effect = _get
        client.paginate.side_effect = [iter([self.SPACE]), iter(self.GRANTS)]
        return client

    def test_yes_no_unknown_reported_from_grants(self, runner: CliRunner) -> None:
        """User grant -> Yes, group grant -> Yes, none -> No, role -> Unknown."""
        with patch("confluence_as.cli.cli_utils.get_confluence_client") as mock:
            mock.return_value = self._client()
            result = runner.invoke(
                cli, ["admin", "permissions", "check", "--space", "DOCS"]
            )
        assert result.exit_code == 0
        assert "[+] read: Yes" in result.output
        assert "[+] create: Yes" in result.output
        assert "[-] delete: No" in result.output
        assert "[?] export: Unknown" in result.output

    def test_json_output_uses_null_for_unknown(self, runner: CliRunner) -> None:
        """JSON output reports true/false/null per operation."""
        with patch("confluence_as.cli.cli_utils.get_confluence_client") as mock:
            mock.return_value = self._client()
            result = runner.invoke(
                cli,
                ["admin", "permissions", "check", "--space", "DOCS", "-o", "json"],
            )
        assert result.exit_code == 0
        assert '"operation": "read"' in result.output
        assert '"has_permission": true' in result.output
        assert '"has_permission": false' in result.output
        assert '"has_permission": null' in result.output

    def test_unreadable_grants_report_unknown(self, runner: CliRunner) -> None:
        """If the grants endpoint fails, operations report Unknown."""
        from confluence_as import PermissionError

        client = MagicMock()

        def _get(endpoint, **kwargs):
            if endpoint == "/rest/api/user/current":
                return {"accountId": "user-1", "displayName": "User One"}
            if endpoint == "/rest/api/user/memberof":
                return {"results": []}
            raise AssertionError(f"unexpected GET {endpoint}")

        client.get.side_effect = _get
        client.paginate.side_effect = [
            iter([self.SPACE]),
            PermissionError("cannot read grants"),
        ]
        with patch("confluence_as.cli.cli_utils.get_confluence_client") as mock:
            mock.return_value = client
            result = runner.invoke(
                cli, ["admin", "permissions", "check", "--space", "DOCS"]
            )
        assert result.exit_code == 0
        assert "[?] read: Unknown" in result.output
        assert "Yes" not in result.output.replace("Your Groups", "")


class TestGetCurrentUserSpaceOperations:
    """Unit tests for the grant-derivation helper."""

    def _client(self, grants, memberof_error=None):
        from confluence_as import ConfluenceError

        client = MagicMock()

        def _get(endpoint, **kwargs):
            if endpoint == "/rest/api/user/current":
                return {"accountId": "user-1"}
            if endpoint == "/rest/api/user/memberof":
                if memberof_error:
                    raise memberof_error
                return {"results": [{"id": "group-1", "name": "team"}]}
            raise ConfluenceError(f"unexpected GET {endpoint}")

        client.get.side_effect = _get
        client.paginate.return_value = iter(grants)
        return client

    def test_user_grant_is_yes(self):
        from confluence_as.cli.helpers import get_current_user_space_operations

        grants = [
            {
                "principal": {"type": "user", "id": "user-1"},
                "operation": {"key": "read", "targetType": "space"},
            }
        ]
        info = get_current_user_space_operations(self._client(grants), "100")
        assert info["operations"]["read"] is True

    def test_group_grant_is_yes(self):
        from confluence_as.cli.helpers import get_current_user_space_operations

        grants = [
            {
                "principal": {"type": "group", "id": "group-1"},
                "operation": {"key": "create", "targetType": "page"},
            }
        ]
        info = get_current_user_space_operations(self._client(grants), "100")
        assert info["operations"]["create"] is True

    def test_no_grant_is_no(self):
        from confluence_as.cli.helpers import get_current_user_space_operations

        info = get_current_user_space_operations(self._client([]), "100")
        assert info["operations"]["read"] is False
        assert info["operations"]["create"] is False

    def test_role_principal_is_unknown(self):
        from confluence_as.cli.helpers import get_current_user_space_operations

        grants = [
            {
                "principal": {"type": "role", "id": "anyone"},
                "operation": {"key": "read", "targetType": "space"},
            }
        ]
        info = get_current_user_space_operations(self._client(grants), "100")
        assert info["operations"]["read"] is None

    def test_group_grant_with_unknown_membership_is_unknown(self):
        from confluence_as import PermissionError
        from confluence_as.cli.helpers import get_current_user_space_operations

        grants = [
            {
                "principal": {"type": "group", "id": "group-1"},
                "operation": {"key": "read", "targetType": "space"},
            }
        ]
        client = self._client(grants, memberof_error=PermissionError("denied"))
        info = get_current_user_space_operations(client, "100")
        assert info["operations"]["read"] is None
        # Operations without any grant are still definitively No.
        assert info["operations"]["create"] is False

    def test_unreadable_grants_are_all_unknown(self):
        from confluence_as import ConfluenceError
        from confluence_as.cli.helpers import get_current_user_space_operations

        client = self._client([])
        client.paginate.side_effect = ConfluenceError("nope")
        info = get_current_user_space_operations(client, "100")
        assert all(v is None for v in info["operations"].values())


class TestMockModeCLI:
    """End-to-end mock mode: commands must work, not crash on paginate."""

    def test_space_list_works_in_mock_mode(
        self, runner: CliRunner, monkeypatch
    ) -> None:
        monkeypatch.setenv("CONFLUENCE_MOCK_MODE", "true")
        result = runner.invoke(cli, ["space", "list"])
        assert result.exit_code == 0
        assert "TEST" in result.output

    def test_page_create_works_in_mock_mode(
        self, runner: CliRunner, monkeypatch
    ) -> None:
        monkeypatch.setenv("CONFLUENCE_MOCK_MODE", "true")
        result = runner.invoke(
            cli,
            [
                "page",
                "create",
                "--space",
                "TEST",
                "--title",
                "Mock Page",
                "--body",
                "x",
            ],
        )
        assert result.exit_code == 0
        assert "Mock Page" in result.output


class TestGrantDerivationHardening:
    """Regression tests from review: grant semantics must be precise."""

    def _client(self, grants, memberof=None, get_error=None):
        client = MagicMock()

        def _get(endpoint, **kwargs):
            if get_error is not None:
                raise get_error
            if endpoint == "/rest/api/user/current":
                return {"accountId": "user-1", "displayName": "User One"}
            if endpoint == "/rest/api/user/memberof":
                return memberof or {"results": [{"id": "group-1", "name": "team"}]}
            raise AssertionError(f"unexpected GET {endpoint}")

        client.get.side_effect = _get
        client.paginate.return_value = iter(grants)
        return client

    def test_other_users_grant_is_definitively_no(self):
        """A grant held by a different user must report No, not Unknown."""
        from confluence_as.cli.helpers import get_current_user_space_operations

        grants = [
            {
                "principal": {"type": "user", "id": "someone-else"},
                "operation": {"key": "delete", "targetType": "page"},
            }
        ]
        info = get_current_user_space_operations(self._client(grants), "100")
        assert info["operations"]["delete"] is False

    def test_incomplete_group_listing_reports_unknown_for_group_grants(self):
        """If group membership may be truncated, group grants are Unknown."""
        from confluence_as.cli.helpers import get_current_user_space_operations

        grants = [
            {
                "principal": {"type": "group", "id": "group-on-page-2"},
                "operation": {"key": "read", "targetType": "space"},
            }
        ]
        memberof = {
            "results": [{"id": "group-1", "name": "team"}],
            "size": 1,
            "_links": {"next": "/rest/api/user/memberof?start=1"},
        }
        info = get_current_user_space_operations(
            self._client(grants, memberof=memberof), "100"
        )
        assert info["operations"]["read"] is None
        # Operations with no grants at all remain definitively No.
        assert info["operations"]["create"] is False

    def test_helper_reports_display_name(self):
        """The helper exposes the current user's display name."""
        from confluence_as.cli.helpers import get_current_user_space_operations

        info = get_current_user_space_operations(self._client([]), "100")
        assert info["display_name"] == "User One"


class TestPageCreateProbeShield:
    """The 404 grant probe must never replace the original error."""

    SPACE = {"id": "100", "key": "DOCS", "name": "Documentation"}

    def test_transport_error_during_probe_preserves_not_found(
        self, runner: CliRunner
    ) -> None:
        from confluence_as import NotFoundError

        with patch("confluence_as.cli.cli_utils.get_confluence_client") as mock:
            client = MagicMock()
            mock.return_value = client
            client.paginate.side_effect = [iter([self.SPACE])]
            client.post.side_effect = NotFoundError("Not found")
            # Probe's first call blows up with a non-Confluence error.
            client.get.side_effect = RuntimeError("connection reset")
            result = runner.invoke(
                cli,
                [
                    "page",
                    "create",
                    "--space",
                    "DOCS",
                    "--title",
                    "T",
                    "--body",
                    "x",
                ],
            )
        assert result.exit_code != 0
        assert "not found" in result.stderr.lower()
        assert "connection reset" not in result.stderr


class TestAdminCheckIdentityDegrade:
    """admin permissions check degrades to Unknown when identity fails."""

    SPACE = {"id": "100", "key": "DOCS", "name": "Documentation"}

    def test_identity_failure_reports_unknown(self, runner: CliRunner) -> None:
        from confluence_as import PermissionError

        client = MagicMock()

        def _get(endpoint, **kwargs):
            raise PermissionError("restricted token")

        client.get.side_effect = _get
        client.paginate.side_effect = [iter([self.SPACE]), iter([])]
        with patch("confluence_as.cli.cli_utils.get_confluence_client") as mock:
            mock.return_value = client
            result = runner.invoke(
                cli, ["admin", "permissions", "check", "--space", "DOCS"]
            )
        assert result.exit_code == 0
        assert "[?] read: Unknown" in result.output
        assert "User: Unknown" in result.output
