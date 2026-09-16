import fnmatch
import re
from pathlib import Path

try:
    import tomllib
except ModuleNotFoundError:
    import tomli as tomllib

ROOT = Path(__file__).resolve().parents[1]


def test_runtime_assets_are_declared_in_both_distribution_formats():
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())
    package_patterns = project["tool"]["setuptools"]["package-data"]["*"]
    manifest = (ROOT / "MANIFEST.in").read_text()
    manifest_patterns = [
        pattern
        for line in manifest.splitlines()
        if line.startswith("recursive-include revolut_bank_feed ")
        for pattern in line.split()[2:]
    ]
    for asset in (ROOT / "revolut_bank_feed").rglob("*"):
        if asset.is_file() and asset.suffix in {".json", ".js", ".txt", ".svg", ".png", ".css", ".html"}:
            assert any(fnmatch.fnmatch(asset.name, pattern) for pattern in package_patterns), asset
            assert any(fnmatch.fnmatch(asset.name, pattern) for pattern in manifest_patterns), asset


def test_package_and_app_versions_agree():
    project = tomllib.loads((ROOT / "pyproject.toml").read_text())["project"]
    module = (ROOT / "revolut_bank_feed/__init__.py").read_text()
    assert re.search(r'__version__\s*=\s*[\'"]' + re.escape(project["version"]) + r'[\'"]', module)
