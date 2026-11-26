"""fontstore.load serves pinned font files; a fake npm answers with a tarball built here."""

import hashlib
import io
import tarfile

import pytest

from fontstore import FontSource, FontUnavailable, load

NAME = "face.woff2"
FONT = b"wOF2 the real font"
SOURCE = FontSource("@scope/face", "1.0.0", hashlib.sha256(FONT).hexdigest())
TARBALL = "https://registry.npmjs.org/@scope/face/-/face-1.0.0.tgz"


def npm(font=FONT):
    """A fetch that serves the package tarball with `font` inside, and the list of URLs it was asked for."""
    buf = io.BytesIO()
    with tarfile.open(fileobj=buf, mode="w:gz") as tar:
        member = tarfile.TarInfo(f"package/files/{NAME}")
        member.size = len(font)
        tar.addfile(member, io.BytesIO(font))

    urls = []

    def fetch(url):
        urls.append(url)
        assert url == TARBALL
        return buf.getvalue()

    return fetch, urls


def test_the_first_run_downloads_the_font_and_keeps_it(tmp_path):
    fetch, urls = npm()
    assert load(NAME, tmp_path, fetch, sources={NAME: SOURCE}) == FONT
    assert (tmp_path / NAME).read_bytes() == FONT
    assert urls == [TARBALL]


def test_a_cached_font_is_used_without_the_network(tmp_path):
    (tmp_path / NAME).write_bytes(FONT)
    fetch, urls = npm()
    assert load(NAME, tmp_path, fetch, sources={NAME: SOURCE}) == FONT
    assert urls == []


def test_a_cached_font_that_does_not_match_its_pin_is_downloaded_again(tmp_path):
    (tmp_path / NAME).write_bytes(b"wOF2 an older version")
    fetch, urls = npm()
    assert load(NAME, tmp_path, fetch, sources={NAME: SOURCE}) == FONT
    assert (tmp_path / NAME).read_bytes() == FONT
    assert urls == [TARBALL]


def test_a_package_without_the_font_is_refused(tmp_path):
    with pytest.raises(FontUnavailable, match=r"other\.woff2 is not in @scope/face@1\.0\.0"):
        load("other.woff2", tmp_path, npm()[0], sources={"other.woff2": SOURCE})
    assert list(tmp_path.iterdir()) == []


def test_a_download_that_does_not_match_its_pin_is_refused_and_not_kept(tmp_path):
    with pytest.raises(FontUnavailable, match=r"face\.woff2.*@scope/face@1\.0\.0"):
        load(NAME, tmp_path, npm(b"wOF2 tampered")[0], sources={NAME: SOURCE})
    assert list(tmp_path.iterdir()) == []
