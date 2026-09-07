"""Compile pinned Base Documents for wheels and persistent editable installs."""

from pathlib import Path

from hatchling.builders.hooks.plugin.interface import BuildHookInterface


class CustomBuildHook(BuildHookInterface):
    def initialize(self, version, build_data):
        # Sdists carry pristine inputs and this hook, never compiled indexes.
        if self.target_name != "wheel":
            return

        from as_engine.build import compile_product

        package = Path(self.root) / "src" / "confluence_as"
        generated = package / "_generated"
        catalog = compile_product(package / "specs", generated)
        names = ["catalog.json", *(entry["file"] for entry in catalog["documents"])]
        for name in sorted(names):
            path = generated / name
            build_data.setdefault("force_include", {})[str(path)] = (
                f"confluence_as/_generated/{path.name}"
            )
