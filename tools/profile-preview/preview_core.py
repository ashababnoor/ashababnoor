"""Pure logic for the profile previewer: no network, no HTTP server.

Everything here is deterministic and unit-tested (see tests/test_core.py).
"""
import hashlib
import html as html_lib
import os
import posixpath
import re
from pathlib import Path
from urllib.parse import quote, unquote

# The image files the previewer finds and serves, with their content types.
IMAGE_TYPES = {
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".ico": "image/x-icon",
}
IMAGE_EXTS = set(IMAGE_TYPES)
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


def is_image_name(name):
    return Path(name).suffix.lower() in IMAGE_EXTS


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
    if not is_image_name(candidate):
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
            if is_image_name(name):
                found.append((Path(dirpath) / name).relative_to(root).as_posix())
                if len(found) >= MAX_LISTED_IMAGES:
                    return sorted(found)
    return sorted(found)


BANNER_FOLDER = "assets/banners"
ICON_FOLDER = "assets/icons"
BANNER_ORDER = ["desktop", "tablet", "mobile"]  # slots are shown in this order, others after

_VERSION_SUFFIX_RE = re.compile(r"[-_.]?v\d+(?:\.\d+)*$", re.IGNORECASE)
# Image sources in README text: srcset="…", src="…" (not data-src) or markdown ![alt](…).
_README_SRC_RE = re.compile(
    r"""(?<![\w-])srcset\s*=\s*["']([^"']+)["']"""
    r"""|(?<![\w-])src\s*=\s*["']([^"']+)["']"""
    r"""|!\[[^\]]*\]\(\s*<?([^)\s>]+)""",
    re.IGNORECASE,
)
_HEADING_RE = re.compile(r"^\s{0,3}#{1,6}\s")
_TAG_RE = re.compile(r"<[^>]*>")
_ALT_RE = re.compile(r"""(?<![\w-])alt\s*=\s*["']([^"']*)["']""", re.IGNORECASE)


def _base_name(path):
    """File name without its extension and trailing version: banner-desktop-v1.2.svg -> banner-desktop."""
    name = Path(path).name
    if is_image_name(name):
        name = Path(name).stem
    return _VERSION_SUFFIX_RE.sub("", name).lower()


def resolve_src(src, base=""):
    """Repo-relative file path of an image source, read from the folder `base` the README is in.

    Escapes are decoded to the real file name (`a%20b.svg`, `a&amp;b.svg`). Returns None for
    remote, rooted or data sources, and for paths that leave the repo.
    `../assets/a.svg?v=1` in versions/ -> `assets/a.svg`.
    """
    src = html_lib.unescape((src or "").strip())
    if not src or src.startswith(_PASSTHROUGH_PREFIXES) or ":" in src.split("/")[0]:
        return None
    path = unquote(src.split("?")[0].split("#")[0])
    joined = posixpath.normpath(posixpath.join(base or ".", path))
    if joined in (".", "..") or joined.startswith("../"):
        return None
    return joined


def _heading_text(line):
    """The text of a markdown heading line without its #s and tags, or "" for other lines."""
    if not _HEADING_RE.match(line):
        return ""
    return _TAG_RE.sub("", _HEADING_RE.sub("", line, count=1)).strip(" #\t")


def _alt_text(line, position):
    """The alt="…" of the HTML tag around `position` in `line`, or ""."""
    start = line.rfind("<", 0, position)
    end = line.find(">", position)
    tag = line[start if start >= 0 else 0 : end if end >= 0 else len(line)]
    match = _ALT_RE.search(tag)
    return match.group(1).strip() if match else ""


def _readme_images(readme_text, base):
    """(repo path, label) for each local image in the README, in order. The label is the
    heading the image sits in, else its alt text, else its file name."""
    found = []
    for line in readme_text.splitlines():
        heading = _heading_text(line)
        for match in _README_SRC_RE.finditer(line):
            srcset, src, markdown_src = match.groups()
            if srcset:
                src = srcset.split(",")[0].split()[0]  # the first candidate's URL
            rel = resolve_src(src or markdown_src, base)
            if rel is not None:
                label = heading or _alt_text(line, match.start()) or Path(rel).stem
                found.append((rel, label))
    return found


def _images_under(root, folder):
    """Repo-relative paths of the images inside `folder` and its subfolders (hidden ones skipped)."""
    directory = Path(root) / folder
    if not directory.is_dir():
        return []
    found = []
    for path in directory.rglob("*"):
        inside = path.relative_to(directory).parts
        if path.is_file() and is_image_name(path) and not any(p.startswith(".") for p in inside):
            found.append(path.relative_to(root).as_posix())
    return sorted(found, key=_natural_key)


def _in_folder(rel, folder):
    return rel.startswith(folder + "/")


def _banner_kind(rel):
    """banner-desktop-slim-v1.0.svg -> "desktop-slim"."""
    stem = _base_name(rel)
    return stem[len("banner-"):] if stem.startswith("banner-") else stem


def _banner_rank(slot):
    """Sort key: desktop, tablet, mobile, then any other banner."""
    kind = _banner_kind(slot["id"])
    return BANNER_ORDER.index(kind) if kind in BANNER_ORDER else len(BANNER_ORDER)


def _banner_slot(rel, banner_files):
    """A banner offers every banner whose name starts with its own, across all version
    folders: banner-desktop also offers banner-desktop-slim. Exact names come first
    within each folder."""
    stem = _base_name(rel)
    bases = {f: _base_name(f) for f in banner_files}
    options = [f for f, base in bases.items() if base == stem or base.startswith(stem + "-")]
    options.sort(key=lambda f: (_natural_key(posixpath.dirname(f)), bases[f] != stem, _natural_key(f)))
    label = _banner_kind(rel).replace("-", " ").capitalize()
    return {"id": rel, "group": "Banners", "label": label, "options": options}


def list_slots(root, readme_text, base=""):
    """The README images you can try alternatives for, each as a slot:
    {"id": path in the README, "group": "Banners" | "Icons", "label": ..., "options": [paths]}.

    - Banners: images the README uses from assets/banners/ (see _banner_slot), shown
      desktop, tablet, mobile first.
    - Icons: images the README uses from assets/icons/, named after their heading.
      Each offers every image in assets/icons/.
    An image used more than once is one slot, named after its first use.
    """
    banner_files = _images_under(root, BANNER_FOLDER)
    icon_files = _images_under(root, ICON_FOLDER)
    banners, icons, seen = [], [], set()
    for rel, label in _readme_images(readme_text, base):
        if rel in seen:
            continue
        seen.add(rel)
        if _in_folder(rel, BANNER_FOLDER):
            banners.append(_banner_slot(rel, banner_files))
        elif _in_folder(rel, ICON_FOLDER):
            icons.append({"id": rel, "group": "Icons", "label": label, "options": icon_files})
    banners.sort(key=_banner_rank)  # stable: other banners keep README order
    return banners + icons


def _local_src(rel, origin=""):
    """URL of a repo file on this server. The name is URL-encoded, so spaces survive in srcset."""
    return origin + "/repo/" + quote(rel.lstrip("/"))


def rewrite_relative_srcs(html, origin="", base="", swaps=None):
    """Point local <img src> and <source srcset> values at the local /repo/ route.

    - `origin` (e.g. http://127.0.0.1:8765) makes the URL absolute, which is needed
      when the page has a <base> tag pointing somewhere else.
    - `base` is the README's folder ("" for the repo root, "versions" for a saved
      version), so `../assets/a.svg` in versions/ is served as assets/a.svg.
    - `swaps` maps a path as written in the README to another image to show instead.
    - Each rewritten tag gets data-preview-src / data-preview-srcset with the path
      as written, so the page can swap it again without a reload.
    """
    swaps = swaps or {}

    def local(url):
        rel = resolve_src(url, base)
        if rel is None:
            return None, url
        query = url[len(url.split("?")[0]):] if "?" in url else ""
        shown = swaps.get(rel, rel)
        return rel, _local_src(shown, origin) + (query if shown == rel else "")

    def repl(match):
        prefix, quote, src = match.groups()
        rel, url = local(src)
        if rel is None:
            return match.group(0)
        return f'{prefix}{quote}{url}{quote} data-preview-src="{html_lib.escape(rel, quote=True)}"'

    def srcset_repl(match):
        prefix, quote, value = match.groups()
        candidates, first = [], None
        for candidate in value.split(","):
            url, _, descriptor = candidate.strip().partition(" ")
            rel, url = local(url) if url else (None, url)
            if rel is not None and first is None:
                first = rel
            candidates.append(f"{url} {descriptor}".strip())
        marker = f' data-preview-srcset="{html_lib.escape(first, quote=True)}"' if first else ""
        return f"{prefix}{quote}{', '.join(candidates)}{quote}{marker}"

    html = _SRCSET_RE.sub(srcset_repl, html)
    return _IMG_SRC_RE.sub(repl, html)


def build_page(profile_html, readme_html, origin="", base="", swaps=None):
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
    body = rewrite_relative_srcs(readme_html, origin, base, swaps)
    page, count = _README_RE.subn(lambda m: m.group(1) + body + m.group(3), page, count=1)
    if not count:
        raise NoReadmeContainer("this profile page has no README section to replace")
    return page


_README_NAME_RE = re.compile(r"^README(?:[-_. ][^/\\]*)?\.md$")


def _natural_key(name):
    return [int(part) if part.isdigit() else part.lower() for part in re.split(r"(\d+)", name)]


VERSIONS_FOLDER = "versions"


def list_readmes(root):
    """README variants in the repo root (README.md, README-v2.md, ...), the main one first,
    then the saved versions in versions/ (versions/v1.0.md, ...)."""
    root = Path(root)
    if not root.is_dir():
        return []
    names = [p.name for p in root.iterdir() if p.is_file() and _README_NAME_RE.match(p.name)]
    names.sort(key=lambda n: (n != "README.md", _natural_key(n)))
    saved = root / VERSIONS_FOLDER
    if saved.is_dir():
        names += [f"{VERSIONS_FOLDER}/{n}" for n in sorted((p.name for p in saved.iterdir() if p.is_file() and p.suffix == ".md"), key=_natural_key)]
    return names


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
