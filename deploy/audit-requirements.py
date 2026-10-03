"""Export installed packages for advisory lookup, without dependency resolution.

The local OASIS metadata patch keeps upstream source; its upstream version is
queried. PyTorch's +cpu wheel is queried under the same public release number.
The application's own source is covered by code review and regression tests.
"""
from importlib.metadata import distributions

packages = {}
for package in distributions():
    name = package.metadata["Name"]
    if name.lower() == "mirofish-backend":
        continue
    version = package.version
    if name.lower() in {"torch", "camel-oasis"}:
        version = version.split("+", 1)[0]
    packages[name] = version
for name, version in sorted(packages.items(), key=lambda item: item[0].lower()):
    print(f"{name}=={version}")
