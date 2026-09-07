"""Packaging and loading contracts for the vendored specification pipeline."""

import json
import shutil
import statistics
import subprocess
import sys
import tarfile
import time
import zipfile
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
SPECS = ROOT / "src/confluence_as/specs"


@pytest.fixture(scope="module")
def built_product(tmp_path_factory):
    """Use the actual backend/config, with no network or installation."""
    root = tmp_path_factory.mktemp("confluence-build")
    for name in ("pyproject.toml", "hatch_build.py", "README.md", "LICENSE"):
        shutil.copyfile(ROOT / name, root / name)
    shutil.copytree(
        ROOT / "src",
        root / "src",
        ignore=shutil.ignore_patterns("__pycache__", "_generated"),
    )
    artifacts = root / "dist"
    artifacts.mkdir()
    for kind in ("wheel", "editable", "sdist"):
        out = artifacts / kind
        out.mkdir()
        result = subprocess.run(
            [
                sys.executable,
                "-c",
                f"from hatchling.build import build_{kind}; print(build_{kind}({str(out)!r}))",
            ],
            cwd=root,
            capture_output=True,
            text=True,
            timeout=60,
        )
        assert result.returncode == 0, result.stdout + result.stderr
    return root


def test_wheel_ships_two_deterministic_indexes(built_product, tmp_path):
    from as_engine.build import compile_product

    compile_product(SPECS, tmp_path)
    wheel = next((built_product / "dist/wheel").glob("*.whl"))
    with zipfile.ZipFile(wheel) as archive:
        for doc_id, count in (("v2", 218), ("v1", 130)):
            name = f"{doc_id}.index.json"
            data = archive.read(f"confluence_as/_generated/{name}")
            assert data == (tmp_path / name).read_bytes()
            assert len(json.loads(data)["operations"]) == count
        assert "confluence_as/_generated/catalog.json" in archive.namelist()


def test_editable_backend_persists_loadable_indexes(built_product):
    wheel = next((built_product / "dist/editable").glob("*.whl"))
    with zipfile.ZipFile(wheel) as archive:
        pth = "\n".join(
            archive.read(name).decode()
            for name in archive.namelist()
            if name.endswith(".pth")
        )
    assert str(built_product / "src") in pth
    code = (
        "from as_engine.index import load_index; "
        f"index=load_index({str(built_product / 'src/confluence_as/_generated/v2.index.json')!r}); "
        "assert len(index.operations)==218"
    )
    result = subprocess.run(
        [sys.executable, "-c", code], capture_output=True, text=True, timeout=10
    )
    assert result.returncode == 0, result.stderr


def test_sdist_contains_sources_and_hook_not_compiled_indexes(built_product):
    with tarfile.open(next((built_product / "dist/sdist").glob("*.tar.gz"))) as archive:
        names = archive.getnames()
    assert any(name.endswith("/hatch_build.py") for name in names)
    assert any(name.endswith("/specs/manifest.json") for name in names)
    assert not any("/_generated/" in name for name in names)


def test_v2_fresh_process_load_budget(built_product):
    path = built_product / "src/confluence_as/_generated/v2.index.json"
    code = (
        "from as_engine.index import load_index; "
        f"index=load_index({str(path)!r}); assert len(index.operations)==218"
    )
    samples = []
    for _ in range(5):
        start = time.perf_counter()
        result = subprocess.run(
            [sys.executable, "-c", code], capture_output=True, text=True, timeout=5
        )
        samples.append((time.perf_counter() - start) * 1000)
        assert result.returncode == 0, result.stderr
    median = statistics.median(samples)
    print(f"v2 fresh-process load median_ms={median:.3f}; samples_ms={samples}")
    # Shared CI hosts vary; the reference-machine acceptance is separately
    # reported against 150 ms. This still catches expensive runtime imports.
    assert median < 500, f"fresh-process load regressed: {median:.3f} ms"
