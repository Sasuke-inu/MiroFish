"""Patch only dependency metadata in the SHA-verified official OASIS wheel."""
import base64
import csv
from email.parser import BytesParser
import hashlib
import io
from pathlib import Path
import urllib.request
import zipfile

URL = "https://files.pythonhosted.org/packages/77/d0/6d62173602433937d0228b7809e2b244e09c11cfb1be9c6754ae3b20d887/camel_oasis-0.2.5-py3-none-any.whl"
SHA256 = "9ebd6ba8e331495ee56b25cc63982188b94125dde499e5e9c00398a1d47e606d"
VERSION = "0.2.5+mirofish.1"
root = Path(__file__).resolve().parents[1]
original = root / "deploy/oasis-upstream.whl"
if not original.exists():
    original.write_bytes(urllib.request.urlopen(URL, timeout=60).read())
assert hashlib.sha256(original.read_bytes()).hexdigest() == SHA256

# Third-party imports in the OASIS runtime. Upstream also declared unused
# libraries and development tools as mandatory runtime dependencies.
requirements = [
    "camel-ai==0.2.90", "pandas>=2.2.3,<3", "igraph==0.11.6",
    "cairocffi==1.7.1", "neo4j>=5.23,<6", "sentence-transformers>=5.6,<7",
]
old_prefix = "camel_oasis-0.2.5.dist-info/"
new_prefix = f"camel_oasis-{VERSION}.dist-info/"
files = {}
with zipfile.ZipFile(original) as archive:
    original_python = {n: archive.read(n) for n in archive.namelist() if n.endswith(".py")}
    for name in archive.namelist():
        if name.endswith("/RECORD"):
            continue
        content = archive.read(name)
        target_name = name.replace(old_prefix, new_prefix, 1)
        if name == old_prefix + "METADATA":
            metadata = BytesParser().parsebytes(content)
            metadata.replace_header("Version", VERSION)
            del metadata["Requires-Dist"]
            for requirement in requirements:
                metadata["Requires-Dist"] = requirement
            content = metadata.as_bytes()
        files[target_name] = content
files[new_prefix + "MIROFISH-PATCH.txt"] = (
    "Local installation patch: runtime dependency metadata only.\n"
    f"Upstream URL: {URL}\nUpstream SHA256: {SHA256}\n"
    "Original Python source and license files preserved unchanged.\n"
    "Removed mandatory dev/unused dependencies: pytest, pytest-asyncio, "
    "pre-commit, pillow, unstructured, prance, openapi-spec-validator, "
    "slack_sdk, requests_oauthlib. Pillow is provided by CAMEL.\n"
    "CAMEL version follows the official OASIS main branch.\n"
).encode()
records = io.StringIO(newline="")
writer = csv.writer(records, lineterminator="\n")
for name, content in sorted(files.items()):
    digest = base64.urlsafe_b64encode(hashlib.sha256(content).digest()).decode().rstrip("=")
    writer.writerow([name, "sha256=" + digest, len(content)])
record_name = new_prefix + "RECORD"
writer.writerow([record_name, "", ""])
files[record_name] = records.getvalue().encode()
target = root / f"backend/vendor/camel_oasis-{VERSION}-py3-none-any.whl"
target.parent.mkdir(parents=True, exist_ok=True)
with zipfile.ZipFile(target, "w", compression=zipfile.ZIP_DEFLATED) as archive:
    for name, content in sorted(files.items()):
        entry = zipfile.ZipInfo(name, date_time=(1980, 1, 1, 0, 0, 0))
        entry.compress_type = zipfile.ZIP_DEFLATED
        entry.external_attr = 0o644 << 16
        archive.writestr(entry, content)
with zipfile.ZipFile(target) as archive:
    assert all(archive.read(name.replace(old_prefix, new_prefix, 1)) == content
               for name, content in original_python.items())
print(f"Patched wheel: {target.name}")
print(f"Unchanged Python source files: {len(original_python)}")
print(f"SHA256: {hashlib.sha256(target.read_bytes()).hexdigest()}")
