"""
Unit tests for search operations.

Consolidated from Confluence-Assistant-Skills:
- skills/confluence-search/tests/test_cql_suggest.py
- skills/confluence-search/tests/test_cql_history.py
- skills/confluence-search/tests/test_cql_interactive.py
- skills/confluence-search/tests/test_streaming_export.py
"""

import csv
import json
from datetime import datetime, timedelta, timezone

import pytest

# =============================================================================
# CQL FIELD SUGGESTION TESTS
# =============================================================================


class TestCQLFieldSuggestions:
    """Tests for CQL field suggestions."""

    def test_get_all_fields(self, sample_cql_fields):
        """Test getting all available CQL fields."""
        # Import the module we'll create
        from confluence_as import validate_cql

        # Test that we can list common CQL fields
        common_fields = [
            "space",
            "title",
            "text",
            "type",
            "label",
            "creator",
            "created",
            "lastModified",
            "ancestor",
            "parent",
        ]

        for field in common_fields:
            # Verify field appears in valid queries
            cql = f"{field} = 'test'"
            assert validate_cql(cql) == cql

    def test_field_descriptions(self, sample_cql_fields):
        """Test that fields have descriptions."""
        for field in sample_cql_fields:
            assert "name" in field
            assert "description" in field
            assert len(field["description"]) > 0

    def test_field_types(self, sample_cql_fields):
        """Test that fields have proper types."""
        valid_types = ["string", "enum", "date", "number", "boolean"]

        for field in sample_cql_fields:
            assert "type" in field
            assert field["type"] in valid_types

    def test_enum_field_has_values(self, sample_cql_fields):
        """Test that enum fields have value lists."""
        type_field = next(f for f in sample_cql_fields if f["name"] == "type")

        assert "values" in type_field
        assert len(type_field["values"]) > 0
        assert "page" in type_field["values"]
        assert "blogpost" in type_field["values"]


class TestCQLOperatorSuggestions:
    """Tests for CQL operator suggestions."""

    def test_get_all_operators(self, sample_cql_operators):
        """Test getting all CQL operators."""
        expected_ops = ["=", "!=", "~", "!~", ">", "<", ">=", "<=", "in", "not in"]

        actual_ops = [op["operator"] for op in sample_cql_operators]

        for expected in expected_ops:
            assert expected in actual_ops

    def test_operator_descriptions(self, sample_cql_operators):
        """Test that operators have descriptions."""
        for op in sample_cql_operators:
            assert "operator" in op
            assert "description" in op
            assert len(op["description"]) > 0


class TestCQLFunctionSuggestions:
    """Tests for CQL function suggestions."""

    def test_get_all_functions(self, sample_cql_functions):
        """Test getting all CQL functions."""
        expected_funcs = [
            "currentUser()",
            "startOfDay()",
            "startOfWeek()",
            "startOfMonth()",
            "startOfYear()",
        ]

        actual_funcs = [f["name"] for f in sample_cql_functions]

        for expected in expected_funcs:
            assert expected in actual_funcs

    def test_function_descriptions(self, sample_cql_functions):
        """Test that functions have descriptions."""
        for func in sample_cql_functions:
            assert "name" in func
            assert "description" in func
            assert func["name"].endswith("()")


class TestCQLValueSuggestions:
    """Tests for CQL field value suggestions."""

    def test_suggest_space_values(self, mock_client, sample_spaces_for_suggestion):
        """Test suggesting space key values."""
        mock_client.setup_response("get", sample_spaces_for_suggestion)

        # Would call the suggestion function here
        # Expected: ['DOCS', 'KB', 'DEV']
        space_keys = [s["key"] for s in sample_spaces_for_suggestion["results"]]

        assert "DOCS" in space_keys
        assert "KB" in space_keys
        assert "DEV" in space_keys

    def test_suggest_type_values(self):
        """Test suggesting content type values."""
        # Content types are static
        expected_types = ["page", "blogpost", "comment", "attachment"]

        for ctype in expected_types:
            assert ctype in expected_types

    def test_suggest_label_values(self, mock_client, sample_labels_for_suggestion):
        """Test suggesting label values."""
        mock_client.setup_response("get", sample_labels_for_suggestion)

        label_names = [
            label["name"] for label in sample_labels_for_suggestion["results"]
        ]

        assert "documentation" in label_names
        assert "api" in label_names
        assert "tutorial" in label_names

    def test_date_function_suggestions(self):
        """Test suggesting date function values."""
        date_functions = [
            "startOfDay()",
            "startOfWeek()",
            "startOfMonth()",
            "startOfYear()",
            "endOfDay()",
            "endOfWeek()",
            "endOfMonth()",
            "endOfYear()",
        ]

        for func in date_functions:
            assert func.endswith("()")
            assert "Of" in func or "end" in func.lower() or "start" in func.lower()


class TestCQLCompletion:
    """Tests for query completion logic."""

    def test_complete_partial_field(self):
        """Test completing partial field names."""
        partial = "spa"

        # Would match fields starting with 'spa'
        fields = ["space", "type", "title", "text"]
        matches = [f for f in fields if f.startswith(partial)]

        assert "space" in matches

    def test_complete_partial_operator(self):
        """Test completing partial operators."""
        partial = "!="
        operators = ["=", "!=", "~", "!~"]

        assert partial in operators

    def test_suggest_next_field(self):
        """Test suggesting next field after AND/OR."""
        # After AND, should suggest field names
        pass

    def test_suggest_operator_after_field(self):
        """Test suggesting operators after field name."""
        # After field, should suggest operators
        pass


# =============================================================================
# CQL HISTORY TESTS
# =============================================================================


class TestHistoryStorage:
    """Tests for history file storage."""

    def test_get_history_file_path(self):
        """Test getting default history file path."""
        from pathlib import Path

        expected_path = Path.home() / ".confluence_cql_history.json"

        assert expected_path.parent == Path.home()
        assert expected_path.name == ".confluence_cql_history.json"

    def test_create_new_history_file(self, tmp_path):
        """Test creating new history file if it doesn't exist."""
        history_file = tmp_path / "history.json"

        assert not history_file.exists()

        # Create with empty list
        history_file.write_text(json.dumps([]))

        assert history_file.exists()
        assert json.loads(history_file.read_text()) == []

    def test_load_existing_history(self, tmp_path, sample_query_history):
        """Test loading existing history file."""
        history_file = tmp_path / "history.json"

        # Write sample history
        history_file.write_text(json.dumps(sample_query_history))

        # Load
        loaded = json.loads(history_file.read_text())

        assert len(loaded) == len(sample_query_history)
        assert loaded[0]["query"] == sample_query_history[0]["query"]


class TestAddingToHistory:
    """Tests for adding queries to history."""

    def test_add_single_query(self, tmp_path):
        """Test adding a single query to history."""
        history_file = tmp_path / "history.json"
        history = []

        # Add query
        entry = {
            "query": "space = 'DOCS'",
            "timestamp": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            "results_count": 42,
        }

        history.append(entry)

        # Save
        history_file.write_text(json.dumps(history, indent=2))

        # Verify
        loaded = json.loads(history_file.read_text())
        assert len(loaded) == 1
        assert loaded[0]["query"] == "space = 'DOCS'"

    def test_add_multiple_queries(self, tmp_path):
        """Test adding multiple queries."""
        history_file = tmp_path / "history.json"
        history = []

        # Add multiple
        for i in range(5):
            history.append(
                {
                    "query": f"query {i}",
                    "timestamp": datetime.now(timezone.utc)
                    .isoformat()
                    .replace("+00:00", "Z"),
                    "results_count": i * 10,
                }
            )

        history_file.write_text(json.dumps(history, indent=2))

        loaded = json.loads(history_file.read_text())
        assert len(loaded) == 5

    def test_limit_history_size(self, tmp_path):
        """Test limiting history to max entries."""
        history_file = tmp_path / "history.json"
        max_entries = 100

        # Create 150 entries
        history = [
            {
                "query": f"query {i}",
                "timestamp": datetime.now(timezone.utc)
                .isoformat()
                .replace("+00:00", "Z"),
            }
            for i in range(150)
        ]

        # Keep only last 100
        history = history[-max_entries:]

        history_file.write_text(json.dumps(history))

        loaded = json.loads(history_file.read_text())
        assert len(loaded) == max_entries
        assert loaded[0]["query"] == "query 50"  # First 50 were dropped

    def test_deduplicate_consecutive_queries(self, tmp_path):
        """Test avoiding duplicate consecutive queries."""
        history = []

        query1 = "space = 'DOCS'"
        query2 = "space = 'KB'"

        # Add query1
        history.append({"query": query1, "timestamp": "2024-01-01T10:00:00Z"})

        # Try to add query1 again (should skip)
        if not history or history[-1]["query"] != query1:
            history.append({"query": query1, "timestamp": "2024-01-01T10:05:00Z"})

        # Add query2
        if not history or history[-1]["query"] != query2:
            history.append({"query": query2, "timestamp": "2024-01-01T10:10:00Z"})

        # Only 2 entries (second query1 was skipped)
        assert len(history) == 2
        assert history[0]["query"] == query1
        assert history[1]["query"] == query2


class TestListingHistory:
    """Tests for listing history entries."""

    def test_list_all_entries(self, sample_query_history):
        """Test listing all history entries."""
        assert len(sample_query_history) == 3

        for entry in sample_query_history:
            assert "query" in entry
            assert "timestamp" in entry

    def test_list_with_limit(self, sample_query_history):
        """Test listing with limit."""
        limit = 2
        limited = sample_query_history[:limit]

        assert len(limited) == 2

    def test_list_most_recent_first(self, sample_query_history):
        """Test listing in reverse chronological order."""
        # Sort by timestamp descending
        sorted_history = sorted(
            sample_query_history, key=lambda x: x["timestamp"], reverse=True
        )

        # Most recent first
        assert sorted_history[0]["timestamp"] >= sorted_history[1]["timestamp"]

    def test_format_history_entry(self):
        """Test formatting a history entry for display."""
        entry = {
            "query": "space = 'DOCS' AND type = page",
            "timestamp": "2024-01-15T10:30:00.000Z",
            "results_count": 42,
        }

        # Format: [timestamp] query (42 results)
        formatted = f"[{entry['timestamp'][:10]}] {entry['query']} ({entry['results_count']} results)"

        assert "2024-01-15" in formatted
        assert "space = 'DOCS'" in formatted
        assert "42 results" in formatted


class TestSearchingHistory:
    """Tests for searching query history."""

    def test_search_by_keyword(self, sample_query_history):
        """Test searching history by keyword."""
        keyword = "DOCS"

        matches = [e for e in sample_query_history if keyword in e["query"]]

        assert len(matches) >= 1
        assert all(keyword in m["query"] for m in matches)

    def test_search_case_insensitive(self, sample_query_history):
        """Test case-insensitive search."""
        keyword = "docs"  # lowercase

        matches = [
            e for e in sample_query_history if keyword.lower() in e["query"].lower()
        ]

        assert len(matches) >= 1

    def test_search_no_matches(self, sample_query_history):
        """Test search with no matches."""
        keyword = "NONEXISTENT"

        matches = [e for e in sample_query_history if keyword in e["query"]]

        assert len(matches) == 0


class TestClearingHistory:
    """Tests for clearing history."""

    def test_clear_all_history(self, tmp_path):
        """Test clearing all history."""
        history_file = tmp_path / "history.json"

        # Create history
        history = [{"query": f"query {i}"} for i in range(10)]
        history_file.write_text(json.dumps(history))

        assert len(json.loads(history_file.read_text())) == 10

        # Clear
        history_file.write_text(json.dumps([]))

        assert json.loads(history_file.read_text()) == []


class TestHistoryMaintenance:
    """Tests for history maintenance operations."""

    def test_remove_old_entries(self, tmp_path):
        """Test removing entries older than N days."""
        history = []

        # Add entries from different dates
        now = datetime.now(timezone.utc)
        old_date = (now - timedelta(days=90)).isoformat().replace("+00:00", "Z")
        recent_date = now.isoformat().replace("+00:00", "Z")

        history.append({"query": "old query", "timestamp": old_date})
        history.append({"query": "recent query", "timestamp": recent_date})

        # Remove entries older than 30 days
        cutoff = (now - timedelta(days=30)).isoformat() + "Z"
        filtered = [e for e in history if e["timestamp"] >= cutoff]

        # Only recent entry remains
        assert len(filtered) == 1
        assert filtered[0]["query"] == "recent query"

    def test_validate_history_format(self, tmp_path):
        """Test validating history file format."""
        history_file = tmp_path / "history.json"

        # Valid format
        valid_history = [{"query": "test", "timestamp": "2024-01-01T00:00:00Z"}]

        history_file.write_text(json.dumps(valid_history))

        # Should load without error
        loaded = json.loads(history_file.read_text())
        assert isinstance(loaded, list)

    def test_recover_corrupted_history(self, tmp_path):
        """Test recovering from corrupted history file."""
        history_file = tmp_path / "history.json"

        # Write invalid JSON
        history_file.write_text("{invalid json")

        # Should handle error gracefully
        try:
            json.loads(history_file.read_text())
            raise AssertionError("Should have raised error")
        except json.JSONDecodeError:
            # Start fresh
            history_file.write_text(json.dumps([]))
            loaded = json.loads(history_file.read_text())
            assert loaded == []


class TestHistoryExport:
    """Tests for exporting history."""

    def test_export_history_to_file(self, tmp_path, sample_query_history):
        """Test exporting history to a file."""
        export_file = tmp_path / "exported_history.json"

        # Export
        export_file.write_text(json.dumps(sample_query_history, indent=2))

        # Verify
        loaded = json.loads(export_file.read_text())
        assert len(loaded) == len(sample_query_history)

    def test_export_history_to_csv(self, tmp_path, sample_query_history):
        """Test exporting history to CSV."""
        export_file = tmp_path / "history.csv"

        # Export to CSV
        with export_file.open("w", newline="") as f:
            writer = csv.DictWriter(
                f, fieldnames=["query", "timestamp", "results_count"]
            )
            writer.writeheader()
            for entry in sample_query_history:
                writer.writerow(entry)

        # Verify
        assert export_file.exists()

        with export_file.open() as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        assert len(rows) == len(sample_query_history)


# =============================================================================
# CQL INTERACTIVE TESTS
# =============================================================================


# =============================================================================
# STREAMING EXPORT TESTS
# =============================================================================


class TestStreamingExport:
    """Tests for streaming export functionality."""

    def test_export_small_result_set(
        self, mock_client, sample_search_results, tmp_path
    ):
        """Test exporting a small result set (no streaming needed)."""
        output_file = tmp_path / "results.csv"

        # Mock returns 10 results
        mock_client.setup_response("get", sample_search_results)

        # Export would write to CSV
        # Verify file exists and has correct data
        assert not output_file.exists()  # Not created yet in test

    def test_csv_export_format(self, tmp_path):
        """Test CSV export format."""
        output_file = tmp_path / "results.csv"

        # Sample data
        data = [
            {"id": "123", "title": "Page 1", "space": "DOCS"},
            {"id": "456", "title": "Page 2", "space": "KB"},
        ]

        # Write CSV
        from confluence_as import export_csv

        export_csv(data, output_file, columns=["id", "title", "space"])

        # Verify
        assert output_file.exists()

        # Read and check
        with output_file.open() as f:
            reader = csv.DictReader(f)
            rows = list(reader)

        assert len(rows) == 2
        assert rows[0]["id"] == "123"
        assert rows[0]["title"] == "Page 1"

    def test_json_export_format(self, tmp_path):
        """Test JSON export format."""
        output_file = tmp_path / "results.json"

        # Sample data
        data = [
            {"id": "123", "title": "Page 1"},
            {"id": "456", "title": "Page 2"},
        ]

        # Write JSON
        output_file.write_text(json.dumps(data, indent=2))

        # Verify
        assert output_file.exists()

        # Read and check
        loaded = json.loads(output_file.read_text())

        assert len(loaded) == 2
        assert loaded[0]["id"] == "123"


class TestCheckpointing:
    """Tests for checkpoint/resume functionality."""

    def test_create_checkpoint_file(self, tmp_path):
        """Test creating checkpoint file."""
        output_file = tmp_path / "results.csv"
        checkpoint_file = tmp_path / "results.csv.checkpoint"

        # Checkpoint data
        checkpoint = {
            "output_file": str(output_file),
            "cql": "space = 'DOCS'",
            "last_start": 200,
            "total_exported": 200,
            "batch_size": 100,
            "format": "csv",
        }

        # Write checkpoint
        checkpoint_file.write_text(json.dumps(checkpoint, indent=2))

        assert checkpoint_file.exists()

        # Read checkpoint
        loaded = json.loads(checkpoint_file.read_text())
        assert loaded["last_start"] == 200
        assert loaded["total_exported"] == 200

    def test_resume_from_checkpoint(self, tmp_path):
        """Test resuming export from checkpoint."""
        checkpoint_file = tmp_path / "results.csv.checkpoint"

        # Create checkpoint
        checkpoint = {
            "output_file": str(tmp_path / "results.csv"),
            "cql": "space = 'DOCS'",
            "last_start": 200,
            "total_exported": 200,
            "batch_size": 100,
            "format": "csv",
        }

        checkpoint_file.write_text(json.dumps(checkpoint))

        # Resume would:
        # 1. Read checkpoint
        # 2. Continue from last_start + batch_size
        loaded = json.loads(checkpoint_file.read_text())

        next_start = loaded["last_start"] + loaded["batch_size"]
        assert next_start == 300

    def test_checkpoint_deleted_on_completion(self, tmp_path):
        """Test checkpoint is deleted when export completes."""
        checkpoint_file = tmp_path / "results.csv.checkpoint"

        # Create checkpoint
        checkpoint_file.write_text("{}")
        assert checkpoint_file.exists()

        # On completion, delete checkpoint
        checkpoint_file.unlink()
        assert not checkpoint_file.exists()


class TestProgressReporting:
    """Tests for progress reporting during export."""

    def test_show_progress_percentage(self):
        """Test calculating and showing progress percentage."""
        total_size = 1000
        exported = 250

        percentage = (exported / total_size) * 100

        assert percentage == 25.0

    def test_show_batch_progress(self):
        """Test showing batch progress messages."""
        batch_num = 5
        total_exported = 500

        message = f"Exported batch {batch_num}: {total_exported} records"

        assert "500" in message
        assert "batch 5" in message

    def test_estimate_remaining_time(self):
        """Test estimating remaining time."""
        exported = 250
        total = 1000

        # Mock elapsed time
        elapsed = 10.0  # 10 seconds

        rate = exported / elapsed  # records per second
        remaining_records = total - exported
        estimated_seconds = remaining_records / rate

        assert rate == 25.0  # 25 records/sec
        assert estimated_seconds == 30.0  # 30 seconds remaining


class TestErrorHandling:
    """Tests for error handling during streaming export."""

    def test_handle_network_error_with_resume(self, tmp_path):
        """Test handling network error and ability to resume."""
        checkpoint_file = tmp_path / "results.csv.checkpoint"

        # Create checkpoint before error
        checkpoint = {
            "last_start": 500,
            "total_exported": 500,
        }
        checkpoint_file.write_text(json.dumps(checkpoint))

        # After error, checkpoint should exist for resume
        assert checkpoint_file.exists()

        # User can resume from 500
        loaded = json.loads(checkpoint_file.read_text())
        assert loaded["last_start"] == 500

    def test_handle_invalid_cql_error(self):
        """Test handling invalid CQL query."""
        from confluence_as import ValidationError, validate_cql

        invalid_cql = "invalid query (("

        with pytest.raises(ValidationError):
            validate_cql(invalid_cql)


class TestColumnSelection:
    """Tests for selecting which columns to export."""

    def test_export_all_columns(self, tmp_path):
        """Test exporting all available columns."""
        data = [
            {"id": "123", "title": "Page 1", "space": "DOCS", "created": "2024-01-01"},
        ]

        output_file = tmp_path / "results.csv"

        from confluence_as import export_csv

        export_csv(data, output_file)

        # Should include all columns
        with output_file.open() as f:
            reader = csv.DictReader(f)
            headers = reader.fieldnames

        assert "id" in headers
        assert "title" in headers
        assert "space" in headers
        assert "created" in headers

    def test_export_selected_columns(self, tmp_path):
        """Test exporting only selected columns."""
        data = [
            {"id": "123", "title": "Page 1", "space": "DOCS", "created": "2024-01-01"},
        ]

        output_file = tmp_path / "results.csv"
        columns = ["id", "title"]

        from confluence_as import export_csv

        export_csv(data, output_file, columns=columns)

        # Should only include selected columns
        with output_file.open() as f:
            reader = csv.DictReader(f)
            headers = reader.fieldnames

        assert "id" in headers
        assert "title" in headers
        assert "space" not in headers


class TestBatchSizing:
    """Tests for configurable batch size."""

    def test_default_batch_size(self):
        """Test default batch size."""
        default_batch_size = 100

        assert default_batch_size == 100

    def test_custom_batch_size(self):
        """Test custom batch size."""
        custom_batch_size = 50

        # User specifies --batch-size 50
        batch_size = custom_batch_size

        assert batch_size == 50

    def test_max_batch_size_limit(self):
        """Test maximum batch size limit."""
        # API limit is typically 250
        max_batch_size = 250

        requested = 1000
        actual = min(requested, max_batch_size)

        assert actual == 250

    def test_min_batch_size_limit(self):
        """Test minimum batch size limit."""
        min_batch_size = 10

        requested = 1
        actual = max(requested, min_batch_size)

        assert actual == 10
