#!/usr/bin/env python3

import argparse
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


ROOT = Path(__file__).resolve().parents[1]
DESCRIPTION = "Detect a RoPro release, verify patch compatibility, and add an audit profile."
sys.path.insert(0, str(ROOT))
import patch_ropro


def github_output(**values) -> None:
    output_path = os.environ.get("GITHUB_OUTPUT")
    if not output_path:
        return
    with Path(output_path).open("a", encoding="utf-8", newline="\n") as stream:
        for key, value in values.items():
            normalized = str(value).replace("\r", " ").replace("\n", " ")
            stream.write(f"{key}={normalized}\n")


def build_profile(source: Path) -> dict:
    manifest = json.loads((source / "manifest.json").read_text(encoding="utf-8"))
    actual_id = patch_ropro.extension_id(manifest)
    if actual_id != patch_ropro.EXPECTED_ID:
        raise RuntimeError(f"Unexpected extension ID: {actual_id}")
    version = manifest.get("version")
    if not isinstance(version, str) or not version:
        raise RuntimeError("Candidate manifest has no version")
    patch_ropro.validate_anchor_compatibility(source)
    hashes = {}
    for relative in patch_ropro.MODIFIED_SOURCE_FILES:
        path = source / relative
        if not path.is_file():
            raise RuntimeError(f"Candidate is missing {relative}")
        hashes[relative] = patch_ropro.source_digest(path, relative)
    return {
        "extension_id": actual_id,
        "hashes": hashes,
        "schema": 1,
        "version": version,
    }


def refresh_manifest(relative: str, path: Path) -> None:
    manifest_path = ROOT / "MANIFEST.sha256"
    entries = {}
    for line in manifest_path.read_text(encoding="utf-8").splitlines():
        if line:
            digest, name = line.split("  ", 1)
            entries[name] = digest
    entries[relative] = patch_ropro.sha256(path)
    rendered = "".join(f"{entries[name]}  {name}\n" for name in sorted(entries))
    with manifest_path.open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(rendered)


def verify_candidate(source: Path) -> None:
    config = dict(patch_ropro.SCENARIO_PRESETS["max-access"])
    patch_ropro.patch_in_place(source, config, "audited")
    node = shutil.which("node")
    if node:
        for relative in (
            "background.js",
            "js/page/options.js",
            "js/page/friends.js",
            "js/shared/roproApiAdapter.js",
        ):
            subprocess.run([node, "--check", str(source / relative)], check=True)


def main() -> int:
    parser = argparse.ArgumentParser(description=DESCRIPTION)
    parser.add_argument("--source", type=Path, help="inspect an unpacked source instead of the Web Store")
    parser.add_argument("--write", action="store_true", help="add a compatible audit profile")
    args = parser.parse_args()

    github_output(changed="false", compatible="false", version="unknown")
    with tempfile.TemporaryDirectory(prefix="ropro-release-audit-") as temporary:
        if args.source is None:
            source = Path(temporary) / "source"
            source.mkdir()
            patch_ropro.extract_package(patch_ropro.download_package(), source)
        else:
            source = args.source.expanduser().resolve()
        patch_ropro.normalize_package_manifest(source)
        try:
            profile = build_profile(source)
        except Exception as error:
            github_output(compatible="false", message=str(error))
            print(f"Candidate is not anchor-compatible: {error}", file=sys.stderr)
            return 2

        version = profile["version"]
        github_output(compatible="true", version=version)
        profile_path = patch_ropro.AUDITS_DIR / f"{version}.json"
        rendered = json.dumps(profile, indent=2, sort_keys=True) + "\n"
        if profile_path.exists():
            if profile_path.read_text(encoding="utf-8") != rendered:
                github_output(message="published bytes differ from the existing audited version")
                print(f"RoPro {version} differs from its existing audit profile", file=sys.stderr)
                return 3
            print(f"RoPro {version} is already audited")
            return 0
        if not args.write:
            github_output(changed="true", message="compatible release requires a new profile")
            print(f"RoPro {version} is compatible and requires a new audit profile")
            return 0


        patch_ropro.AUDITS_DIR.mkdir(parents=True, exist_ok=True)
        manifest_path = ROOT / "MANIFEST.sha256"
        original_manifest = manifest_path.read_bytes()
        with profile_path.open("w", encoding="utf-8", newline="\n") as stream:
            stream.write(rendered)
        relative = profile_path.relative_to(ROOT).as_posix()
        try:
            refresh_manifest(relative, profile_path)
            verify_candidate(source)
        except Exception:
            profile_path.unlink(missing_ok=True)
            manifest_path.write_bytes(original_manifest)
            raise
        github_output(changed="true", message="compatible audit profile generated")
        print(f"Added and verified audit profile for RoPro {version}")
        return 0


if __name__ == "__main__":
    raise SystemExit(main())
