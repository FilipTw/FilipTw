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

    def __str__(self) -> str:
        return f"{self.package}@{self.version}"

    @property
    def tarball(self) -> str:
        return f"https://registry.npmjs.org/{self.package}/-/{self.package.split('/')[-1]}-{self.version}.tgz"

    def matches(self, data: bytes) -> bool:
        return hashlib.sha256(data).hexdigest() == self.sha256


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
    """The downloaded package does not hold the pinned font file."""


def download(url: str) -> bytes:
    with urllib.request.urlopen(url, timeout=30) as response:
        data: bytes = response.read()
        return data


def load(
    name: str,
    cache_dir: Path,
    fetch: Callable[[str], bytes] = download,
    *,
    sources: Mapping[str, FontSource] = FONT_SOURCES,
) -> bytes:
    """The bytes of the font file `name`, which must be in sources. A copy in cache_dir that matches its
    pin is used as is; otherwise the npm package is fetched and the file replaces the copy.
    Raises FontUnavailable when the package lacks the file or it does not match its pin, and lets the
    fetch's own errors (no network, HTTP errors, timeout) through."""
    src = sources[name]
    path = cache_dir / name
    if path.exists() and src.matches(cached := path.read_bytes()):
        return cached
    print(f"  fetching {src}")
    with tarfile.open(fileobj=io.BytesIO(fetch(src.tarball))) as tar:
        try:
            member = tar.extractfile(f"package/files/{name}")
        except KeyError:
            member = None
        if member is None:
            raise FontUnavailable(f"{name} is not in {src}")
        data = member.read()
    if not src.matches(data):
        raise FontUnavailable(f"{name} from {src} does not match its pinned sha256")
    cache_dir.mkdir(exist_ok=True)
    part = path.with_name(name + ".part")
    part.write_bytes(data)
    part.replace(path)  # an interrupted write never leaves half a font under the real name
    return data
