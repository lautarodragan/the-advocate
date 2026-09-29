"""The Rust projects' layers only depend downwards.

The workspace keeps each project in the directory of its layer: `snes/`
knows the console's formats and nothing of RPG Maker, `rm2k/` knows RPG
Maker and nothing of the console, and `rm2k-snes/` is what joins the two.
So `rm2k-snes/` may depend on anything, and the other two only on
themselves. Nothing but this test stops a `path` dependency from going the
other way —cargo compiles it happily—, and once one does, the layer it
reaches into cannot be taken anywhere without the other.

What each project depends on is cargo's answer, `cargo metadata`, and not a
reading of the `Cargo.toml` files by hand: it counts every kind of
dependency, however it is written. `--no-deps` lists only the workspace, so
it reads no registry and needs no network.
"""

import json
import os
import subprocess

import pytest

from common import project


# What each layer may depend on, besides itself.
BELOW = {
    "snes": set(),
    "rm2k": set(),
    "rm2k-snes": {"snes", "rm2k"},
}


def _layer(path):
    """The layer a path inside the tools belongs to: its first directory."""
    return os.path.relpath(path, project.tools()).split(os.sep)[0]


@pytest.fixture(scope="module")
def packages():
    output = subprocess.run(
        ["cargo", "metadata", "--format-version", "1", "--no-deps"],
        cwd=project.tools(), check=True, capture_output=True, text=True).stdout
    return json.loads(output)["packages"]


def test_every_project_is_in_a_layer(packages):
    outside = sorted(p["name"] for p in packages
                     if _layer(p["manifest_path"]) not in BELOW)
    assert not outside, (
        "these projects are not inside snes/, rm2k/ or rm2k-snes/: %s"
        % ", ".join(outside))


def test_the_layers_only_depend_downwards(packages):
    wrong = []
    for p in packages:
        source = _layer(p["manifest_path"])
        for d in p["dependencies"]:
            # Only a `path` dependency is one of ours: cargo gives it the
            # directory whether it is written in the crate or inherited
            # from the workspace, and the registry's have none.
            path = d.get("path")
            if path is None:
                continue
            target = _layer(path)
            if target != source and target not in BELOW.get(source, set()):
                wrong.append("%s (%s/) depends on %s (%s/)"
                             % (p["name"], source, d["name"], target))
    assert not wrong, "a layer depends upwards or sideways:\n" + "\n".join(wrong)


def test_the_lower_layers_do_not_read_the_project_file():
    """Knowing `rm2k-snes.toml` is knowing the layer above without depending
    on it: copying its format instead of using `rm2k-project`. Until
    2026-09-29 `rm2k-render` looked for the file itself, to find the dump;
    `cargo metadata` does not see that, a grep does."""
    found = []
    for layer in ("snes", "rm2k"):
        for root, dirs, files in os.walk(os.path.join(project.tools(), layer)):
            dirs[:] = [d for d in dirs if d != "target"]
            for name in files:
                if not name.endswith((".rs", ".toml")):
                    continue
                path = os.path.join(root, name)
                with open(path, encoding="utf-8") as handle:
                    if "rm2k-snes.toml" in handle.read():
                        found.append(os.path.relpath(path, project.tools()))
    assert not found, (
        "these name rm2k-snes.toml, which only rm2k-snes/ may know: %s"
        % ", ".join(sorted(found)))
