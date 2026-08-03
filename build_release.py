#!/usr/bin/env python3

import argparse
import gzip
import hashlib
import io
from pathlib import Path
import tarfile
import zipfile


ROOT = Path(__file__).resolve().parent
DESCRIPTION = "Build deterministic portable distributions of this team kit."
PREFIX = "ropro-bypass"
ZIP_TIME = (2026, 7, 24, 0, 0, 0)
EPOCH = 1784851200


def source_files():
    manifest = ROOT / "MANIFEST.sha256"
    paths = [ROOT / line.split("  ", 1)[1] for line in manifest.read_text(encoding="utf-8").splitlines() if line]
    paths.append(manifest)
    return sorted(paths, key=lambda path: path.relative_to(ROOT).as_posix())


def sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def build_zip(target: Path, files) -> None:
    with zipfile.ZipFile(target, "x", compression=zipfile.ZIP_STORED) as archive:
        for path in files:
            relative = path.relative_to(ROOT).as_posix()
            info = zipfile.ZipInfo(f"{PREFIX}/{relative}", ZIP_TIME)
            info.create_system = 3
            mode = 0o100755 if path.name in {"patch_ropro.py", "build_release.py", "quickstart.sh", "quickstart.command"} else 0o100644
            info.external_attr = mode << 16
            archive.writestr(info, path.read_bytes(), compress_type=zipfile.ZIP_STORED)


def build_tar_gz(target: Path, files) -> None:
    tar_buffer = io.BytesIO()
    with tarfile.open(fileobj=tar_buffer, mode="w", format=tarfile.PAX_FORMAT) as archive:
        for path in files:
            relative = path.relative_to(ROOT).as_posix()
            data = path.read_bytes()
            info = tarfile.TarInfo(f"{PREFIX}/{relative}")
            info.size = len(data)
            info.mtime = EPOCH
            info.uid = 0
            info.gid = 0
            info.uname = ""
            info.gname = ""
            info.mode = 0o755 if path.name in {"patch_ropro.py", "build_release.py", "quickstart.sh", "quickstart.command"} else 0o644
            archive.addfile(info, io.BytesIO(data))
    target.write_bytes(gzip.compress(tar_buffer.getvalue(), compresslevel=9, mtime=0))


def main() -> None:
    parser = argparse.ArgumentParser(description=DESCRIPTION)
    parser.add_argument("--output-dir", type=Path, default=Path("dist"))
    args = parser.parse_args()
    output = args.output_dir.resolve()
    output.mkdir(parents=True, exist_ok=True)
    zip_path = output / f"{PREFIX}.zip"
    tar_path = output / f"{PREFIX}.tar.gz"
    for path in (zip_path, tar_path, output / "SHA256SUMS"):
        if path.exists():
            raise SystemExit(f"Refusing to overwrite existing artifact: {path}")
    files = source_files()
    build_zip(zip_path, files)
    build_tar_gz(tar_path, files)
    checksums = f"{sha256(zip_path)}  {zip_path.name}\n{sha256(tar_path)}  {tar_path.name}\n"
    with (output / "SHA256SUMS").open("w", encoding="utf-8", newline="\n") as stream:
        stream.write(checksums)
    print(checksums, end="")


if __name__ == "__main__":
    main()
