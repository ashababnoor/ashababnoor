"""Pure logic for the profile previewer: no network, no HTTP server.

Everything here is deterministic and unit-tested (see tests/test_core.py).
"""
import hashlib
import html as html_lib
import os
import re
from pathlib import Path

IMAGE_EXTS = {".svg", ".png", ".jpg", ".jpeg", ".gif", ".webp", ".ico"}
MAX_LISTED_IMAGES = 500
BASE_TAG = '<base href="https://github.com/">'

# GitHub usernames: 1-39 chars, alphanumeric or hyphen, no leading/trailing hyphen.
_USERNAME_RE = re.compile(r"^[A-Za-z0-9](?:[A-Za-z0-9-]{0,37}[A-Za-z0-9])?$")
_REMOTE_URL_RE = re.compile(r"^(?:https?|ssh|git)://(?:[^@/]+@)?github\.com/([^/]+)/[^/]+?(?:\.git)?/?$")
_REMOTE_SCP_RE = re.compile(r"^(?:[^@\s]+@)?github\.com:([^/]+)/[^/]+?(?:\.git)?/?$")
_IMG_SRC_RE = re.compile(r"""(<img\b[^>]*?\bsrc\s*=\s*)(["'])(.*?)\2""", re.IGNORECASE | re.DOTALL)
_SRCSET_RE = re.compile(r"""(<(?:source|img)\b[^>]*?\bsrcset\s*=\s*)(["'])(.*?)\2""", re.IGNORECASE | re.DOTALL)
_SCRIPT_RE = re.compile(r"<script\b.*?</script>", re.IGNORECASE | re.DOTALL)
_HEAD_RE = re.compile(r"(<head\b[^>]*>)", re.IGNORECASE)
_README_RE = re.compile(
    r"""(<article\b[^>]*\bclass="[^"]*\bmarkdown-body\b[^"]*"[^>]*>)(.*?)(</article>)""",
    re.IGNORECASE | re.DOTALL,
)
_CACHE_KEY_RE = re.compile(r"^[A-Za-z0-9._-]+$")
_PASSTHROUGH_PREFIXES = ("http://", "https://", "//", "data:", "/")


class NoReadmeContainer(Exception):
    """The fetched profile page has no README section to replace."""


def valid_username(name):
    return bool(_USERNAME_RE.match(name or ""))


def owner_from_remote(url):
    """Return the GitHub owner from a git remote URL, or None."""
    url = (url or "").strip()
    match = _REMOTE_URL_RE.match(url) or _REMOTE_SCP_RE.match(url)
    if not match:
        return None
    owner = match.group(1)
    return owner if valid_username(owner) else None


def safe_image_path(root, rel):
    """Resolve `rel` inside `root` if it is an existing image, else None.

    Blocks traversal, absolute paths, hidden directories, non-image files and
    symlinks that point outside the repo.
    """
    if not rel or rel.startswith(("/", "\\")) or Path(rel).is_absolute():
        return None
    if any(part == ".." or part.startswith(".") for part in Path(rel).parts):
        return None
    candidate = Path(root) / rel
    if candidate.suffix.lower() not in IMAGE_EXTS:
        return None
    try:
        resolved = candidate.resolve(strict=True)
        resolved.relative_to(Path(root).resolve())
    except (OSError, ValueError):
        return None
    return resolved if resolved.is_file() else None


def list_images(root):
    """Repo-relative paths of all image files (used to notice changes), skipping hidden dirs and node_modules."""
    found = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames[:] = sorted(d for d in dirnames if not d.startswith(".") and d != "node_modules")
        for name in sorted(filenames):
            if Path(name).suffix.lower() in IMAGE_EXTS:
                found.append((Path(dirpath) / name).relative_to(root).as_posix())
                if len(found) >= MAX_LISTED_IMAGES:
                    return sorted(found)
    return sorted(found)


_VERSION_SUFFIX_RE = re.compile(r"[-_.]?v\d+(?:\.\d+)*$", re.IGNORECASE)
_README_SRC_RE = re.compile(r"""(?:\bsrc\s*=\s*["']([^"']+)["']|!\[[^\]]*\]\(\s*<?([^)\s>]+))""", re.IGNORECASE)


def _base_name(path):
    """File name without its extension and trailing version: banner-v1.2.svg -> banner."""
    name = Path(path).name
    if Path(name).suffix.lower() in IMAGE_EXTS:
        name = name[: -len(Path(name).suffix)]
    return _VERSION_SUFFIX_RE.sub("", name).lower()


def _local_readme_images(readme_text):
    found = []
    for match in _README_SRC_RE.finditer(readme_text):
        src = match.group(1) or match.group(2)
        if src and not src.startswith(_PASSTHROUGH_PREFIXES):
            found.append(src)
    return found


def list_versions(root, readme_text):
    """Versions of each image the README uses (v-suffix ignored), looked up in that image's own folder.

    Only folders inside assets/ are searched, e.g. assets/ or assets/banners/v1/.
    """
    wanted = {}  # folder (repo-relative) -> base names used by the README there
    for src in _local_readme_images(readme_text):
        folder = Path(src.split("?")[0].split("#")[0]).parent
        if folder.parts[:1] == (".",):
            folder = Path(*folder.parts[1:])
        if folder.parts[:1] != ("assets",) or ".." in folder.parts:
            continue
        wanted.setdefault(folder.as_posix(), set()).add(_base_name(src))

    found = []
    for folder, bases in wanted.items():
        directory = Path(root) / folder
        if not directory.is_dir():
            continue
        found += [
            f"{folder}/{p.name}"
            for p in directory.iterdir()
            if p.is_file() and p.suffix.lower() in IMAGE_EXTS and _base_name(p.name) in bases
        ]
    return sorted(found)[:MAX_LISTED_IMAGES]


def _local_src(rel, origin=""):
    return origin + "/repo/" + rel.lstrip("/")


def rewrite_relative_srcs(html, origin=""):
    """Point relative <img src> values at the local /repo/ route.

    `origin` (e.g. http://127.0.0.1:8765) makes the URL absolute, which is needed
    when the page has a <base> tag pointing somewhere else."""

    def repl(match):
        prefix, quote, src = match.groups()
        if src.startswith(_PASSTHROUGH_PREFIXES):
            return match.group(0)
        rel = src[2:] if src.startswith("./") else src
        return f"{prefix}{quote}{_local_src(rel, origin)}{quote}"

    def srcset_repl(match):
        prefix, quote, value = match.groups()
        candidates = []
        for candidate in value.split(","):
            url, _, descriptor = candidate.strip().partition(" ")
            if url and not url.startswith(_PASSTHROUGH_PREFIXES):
                url = _local_src(url[2:] if url.startswith("./") else url, origin)
            candidates.append(f"{url} {descriptor}".strip())
        return f"{prefix}{quote}{', '.join(candidates)}{quote}"

    html = _SRCSET_RE.sub(srcset_repl, html)
    return _IMG_SRC_RE.sub(repl, html)


def swap_image(html, rel, origin=""):
    """Replace the <img> that is another version of `rel` (else the first <img>) with `rel`."""
    new_src = html_lib.escape(_local_src(rel, origin), quote=True)
    target = _base_name(rel)
    matches = list(_IMG_SRC_RE.finditer(html))
    chosen = next((m for m in matches if _base_name(m.group(3).split("?")[0]) == target), matches[0] if matches else None)
    if chosen is None:
        return html
    prefix, quote, _old = chosen.groups()
    return html[: chosen.start()] + f"{prefix}{quote}{new_src}{quote}" + html[chosen.end():]


def build_page(profile_html, readme_html, origin=""):
    """Return the profile page with its README replaced by `readme_html`.

    GitHub's scripts are removed (the page is a static preview), a <base> tag
    keeps GitHub's relative links and assets working, and the README container
    tag is kept so GitHub's own CSS styles the new content.
    """
    page = _SCRIPT_RE.sub("", profile_html)
    if BASE_TAG not in page:
        page, count = _HEAD_RE.subn(lambda m: m.group(1) + BASE_TAG, page, count=1)
        if not count:
            page = BASE_TAG + page
    body = rewrite_relative_srcs(readme_html, origin)
    page, count = _README_RE.subn(lambda m: m.group(1) + body + m.group(3), page, count=1)
    if not count:
        raise NoReadmeContainer("this profile page has no README section to replace")
    return page


_README_NAME_RE = re.compile(r"^README(?:[-_. ][^/\\]*)?\.md$")


def _natural_key(name):
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", name)]


def list_readmes(root):
    """README variants in the repo root (README.md, README-v2.md, ...), the main one first."""
    root = Path(root)
    if not root.is_dir():
        return []
    names = [p.name for p in root.iterdir() if p.is_file() and _README_NAME_RE.match(p.name)]
    return sorted(names, key=lambda n: (n != "README.md", _natural_key(n)))


def readme_path(root, name):
    """The path of a listed README variant, or None for anything else (no traversal)."""
    if name in list_readmes(root):
        return Path(root) / name
    return None


def fingerprint(root):
    """A short hash that changes whenever a README variant or any image changes."""
    root = Path(root)
    digest = hashlib.sha1()
    for rel in [*list_readmes(root), *list_images(root)]:
        path = root / rel
        try:
            stat = path.stat()
        except OSError:
            continue
        digest.update(f"{rel}:{stat.st_mtime_ns}:{stat.st_size}\n".encode())
    return digest.hexdigest()


def static_fingerprint(folder):
    """A short hash that changes whenever a file in the previewer's own UI folder changes."""
    digest = hashlib.sha1()
    for path in sorted(Path(folder).glob("*")):
        if path.is_file():
            info = path.stat()
            digest.update(f"{path.name}\0{info.st_mtime_ns}\0{info.st_size}\n".encode("utf-8"))
    return digest.hexdigest()


class DiskCache:
    """A tiny text cache in one folder. Keys cannot escape that folder."""

    def __init__(self, directory):
        self.directory = Path(directory)

    def _path(self, key):
        if not _CACHE_KEY_RE.match(key) or key.startswith("."):
            raise ValueError(f"invalid cache key: {key!r}")
        return self.directory / key

    def get(self, key):
        try:
            return self._path(key).read_text(encoding="utf-8")
        except FileNotFoundError:
            return None

    def put(self, key, text):
        path = self._path(key)
        self.directory.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding="utf-8")

    def drop(self, key):
        try:
            self._path(key).unlink()
        except FileNotFoundError:
            pass
