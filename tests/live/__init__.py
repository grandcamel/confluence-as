"""Confluence live tests. See tests/live/README.md for the guarded SBX tranche.

Only the supervisor may run the selected suite through confluence-dev-host.
Only run_sbx.py supports live admission. Raw pytest --live may import external
plugins/conftests before its diagnostic and is unsupported. Legacy domains stay held.
The launcher uses explicit package paths and importlib mode without placing the
repository root on sys.path.
"""
