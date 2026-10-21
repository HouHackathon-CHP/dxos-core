"""Fail CI when an explicitly selected Python dependency has not been reviewed.

This checks package metadata, not bundled assets or transitive dependencies.
Update REVIEWED only after checking the exact new release and OSI's license list.
"""

import re
from importlib.metadata import PackageNotFoundError, distribution
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
REQUIREMENTS = ("gateway/requirements.txt", "data/requirements.txt", "workflow/requirements.txt")
REVIEWED = {
    "boto3": ("1.43.116", "Apache-2.0"),
    "fastapi": ("0.158.1", "MIT"),
    "httpx": ("0.28.1", "BSD-3-Clause"),
    "pyjwt": ("2.15.1", "MIT"),
    "psycopg": ("3.3.6", "LGPL-3.0-only"),
    "python-multipart": ("0.0.32", "Apache-2.0"),
    "sqlalchemy": ("2.1.6", "MIT"),
    "uvicorn": ("0.54.0", "BSD-3-Clause"),
}
PIN = re.compile(r"^([A-Za-z0-9_.-]+)(?:\[[A-Za-z0-9_,.-]+\])?==([^\s#]+)$")


def normalize(name: str) -> str:
    return re.sub(r"[-_.]+", "-", name).lower()


def main() -> None:
    declared = {}
    for relative in REQUIREMENTS:
        for raw in (ROOT / relative).read_text(encoding="utf-8").splitlines():
            line = raw.strip()
            if not line or line.startswith("#"):
                continue
            match = PIN.fullmatch(line)
            if not match:
                raise SystemExit(f"Unpinned or unsupported requirement in {relative}: {line}")
            name, version = normalize(match[1]), match[2]
            if name in declared and declared[name] != version:
                raise SystemExit(f"Conflicting versions of {name}: {declared[name]}, {version}")
            declared[name] = version

    if declared.keys() != REVIEWED.keys():
        missing = sorted(declared.keys() - REVIEWED.keys())
        removed = sorted(REVIEWED.keys() - declared.keys())
        raise SystemExit(f"Dependency review must be updated. New: {missing}; removed: {removed}")

    for name, (approved_version, approved_license) in REVIEWED.items():
        if declared[name] != approved_version:
            raise SystemExit(f"Review new {name} version before use: {declared[name]}")
        try:
            package = distribution(name)
        except PackageNotFoundError as exc:
            raise SystemExit(f"Install requirements before checking licenses: {name}") from exc
        observed = package.metadata.get("License-Expression") or package.metadata.get("License")
        if package.version != approved_version or observed != approved_license:
            raise SystemExit(
                f"{name} {package.version}: expected {approved_version} / {approved_license}, got {observed}"
            )
    print(f"PASS: {len(REVIEWED)} directly selected Python packages match reviewed versions and licenses")


if __name__ == "__main__":
    main()
