"""Test suite for Confluence CLI.

Root and global option contracts, plus retained library decision helpers.
Survivor execution is covered through Surface in test_wrapper_* modules.
"""

from __future__ import annotations

from unittest.mock import MagicMock

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


class TestSearchCommands:
    """Test search command group."""

    def test_search_help(self, runner: CliRunner) -> None:
        """Test search --help."""
        result = runner.invoke(cli, ["search", "--help"])
        assert result.exit_code == 0
        assert "Search Confluence content" in result.output


class TestAdminCommands:
    """Test admin command group."""

    def test_admin_help(self, runner: CliRunner) -> None:
        """Test admin help output."""
        result = runner.invoke(cli, ["admin", "--help"])
        assert result.exit_code == 0
        assert "user" in result.output
        assert "group" in result.output
        assert "template" in result.output


class TestBulkCommands:
    """Test bulk command group."""

    def test_bulk_help(self, runner: CliRunner) -> None:
        """Test bulk help output."""
        result = runner.invoke(cli, ["bulk", "--help"])
        assert result.exit_code == 0
        assert "label" in result.output
        assert "move" in result.output
        assert "delete" in result.output


class TestOpsCommands:
    """Test ops command group."""

    def test_ops_help(self, runner: CliRunner) -> None:
        """Test ops help output."""
        result = runner.invoke(cli, ["ops", "--help"])
        assert result.exit_code == 0
        assert "cache" in result.output
        assert "health" in result.output


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


class TestGlobalOutputOption:
    """Global output inheritance is independent of any removed API verb."""

    def test_global_and_local_placements_equivalent(self, runner):
        import json

        before = runner.invoke(cli, ["-o", "json", "search", "suggest", "--fields"])
        after = runner.invoke(cli, ["search", "suggest", "--fields", "-o", "json"])
        assert before.exit_code == after.exit_code == 0
        assert before.output == after.output
        assert isinstance(json.loads(before.stdout), dict)

    def test_local_output_overrides_global(self, runner):
        result = runner.invoke(
            cli, ["-o", "json", "search", "suggest", "--fields", "-o", "text"]
        )
        default = runner.invoke(cli, ["search", "suggest", "--fields"])
        assert result.exit_code == default.exit_code == 0
        assert result.output == default.output
        assert "CQL" in result.output
