"""The font files the artwork is drawn with, downloaded from npm once and checked against pinned hashes."""

import hashlib
import io
import tarfile
import urllib.request
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class FontSource:
    package: str
    version: str
    sha256: str  # of the font file itself, not of the npm tarball


FONT_SOURCES = {
    "mona-sans-latin-wdth-normal.woff2": FontSource(
        "@fontsource-variable/mona-sans",
        "5.3.0",
        "5ea3740633e5ac7af56c13d7e8ec32bcae12e7723e53d34284469a8947ccb2f3",
    ),
    "monaspace-neon-latin-400-normal.woff2": FontSource(
        "@fontsource/monaspace-neon",
        "5.3.0",
        "d90b15f2bab28d1ee0b11a3e45ab2b3b5f1d0ca898ae047ab40172d25730343c",
    ),
}


class FontUnavailable(Exception):
    """npm did not serve the pinned font file."""


def download(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=30) as r:
        data: bytes = r.read()
        return data


def pinned(data: bytes, src: FontSource) -> bool:
    return hashlib.sha256(data).hexdigest() == src.sha256


def load(
    name: str,
    cache_dir: Path,
    fetch: Callable[[str], bytes] = download,
    *,
    sources: Mapping[str, FontSource] = FONT_SOURCES,
) -> bytes:
    """The bytes of the font file `name`, from cache_dir, or from npm when they are not cached yet."""
    src = sources[name]
    path = cache_dir / name
    if path.exists() and pinned(cached := path.read_bytes(), src):
        return cached
    url = f"https://registry.npmjs.org/{src.package}/-/{src.package.split('/')[-1]}-{src.version}.tgz"
    print(f"  fetching {src.package}@{src.version}")
    with tarfile.open(fileobj=io.BytesIO(fetch(url))) as tar:
        member = tar.extractfile(f"package/files/{name}")
        if member is None:
            raise FontUnavailable(f"{name} is not in {src.package}@{src.version}")
        data = member.read()
    if not pinned(data, src):
        raise FontUnavailable(f"{name} from {src.package}@{src.version} does not match its pinned sha256")
    cache_dir.mkdir(exist_ok=True)
    part = path.with_name(name + ".part")
    part.write_bytes(data)
    part.replace(path)  # an interrupted write never leaves half a font under the real name
    return data
