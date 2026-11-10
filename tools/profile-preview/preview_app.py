"""Request handling for the profile previewer.

`PreviewApp.handle(path)` maps a request path to `(status, content_type, body)`.
The network (fetching a profile, rendering markdown) is injected, so this module
can be tested without touching GitHub. See serve.py for the real wiring.
"""
import hashlib
import html
import json
import mimetypes
import secrets
from pathlib import Path
from urllib.parse import parse_qs, unquote, urlsplit

import preview_core as core

HTML = "text/html; charset=utf-8"
IMAGE_TYPES = {
    ".svg": "image/svg+xml",
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".gif": "image/gif",
    ".webp": "image/webp",
    ".ico": "image/x-icon",
}
STATIC_TYPES = {".js": "text/javascript; charset=utf-8", ".css": "text/css; charset=utf-8"}
LAST_RENDER_KEY = "last-render"
LAST_RENDER_KEY_NAME = "last-render-key"  # which readme-<hash> file is the current one


class ProfileNotFound(Exception):
    """GitHub has no profile page for that username."""


class RenderError(Exception):
    """GitHub's markdown renderer could not render the README."""

    def __init__(self, message, rate_limited=False):
        super().__init__(message)
        self.rate_limited = rate_limited


def _message_page(status, title, message):
    body = (
        '<!doctype html><meta charset="utf-8"><meta name="color-scheme" content="light dark">'
        '<style>body{font:16px/1.5 system-ui,sans-serif;max-width:40rem;margin:4rem auto;padding:0 1rem}</style>'
        f"<h2>{html.escape(title)}</h2><p>{html.escape(message)}</p>"
    )
    return status, HTML, body.encode("utf-8")


class PreviewApp:
    def __init__(self, root, cache_dir, default_user, context, fetch_profile, render_markdown, static_dir, origin=""):
        self.root = Path(root).resolve()
        self.cache = core.DiskCache(cache_dir)
        self.default_user = default_user
        self.context = context
        self.fetch_profile = fetch_profile
        self.render_markdown = render_markdown
        self.static_dir = Path(static_dir).resolve()
        self.boot = secrets.token_hex(4)  # changes when the server restarts
        self.origin = origin  # e.g. http://127.0.0.1:8765, for image URLs

    # -- routing ---------------------------------------------------------
    def handle(self, raw_path):
        parts = urlsplit(raw_path)
        path, query = parts.path, parse_qs(parts.query)
        if path == "/":
            return self._shell()
        if path == "/page":
            return self._page(query)
        if path == "/api/state":
            return self._state()
        if path.startswith("/repo/"):
            return self._repo_file(unquote(path[len("/repo/"):]))
        if path.startswith("/static/"):
            return self._static_file(unquote(path[len("/static/"):]))
        return _message_page(404, "Not found", "There is nothing at this address.")

    # -- routes ----------------------------------------------------------
    def _shell(self):
        template = (self.static_dir / "shell.html").read_text(encoding="utf-8")
        page = template.replace("{{DEFAULT_USER}}", html.escape(self.default_user or "", quote=True))
        return 200, HTML, page.encode("utf-8")

    def _state(self):
        readme = self.root / "README.md"
        text = readme.read_text(encoding="utf-8") if readme.is_file() else ""
        payload = {"fingerprint": core.fingerprint(self.root), "images": core.list_versions(self.root, text),
                   "ui": core.static_fingerprint(self.static_dir), "boot": self.boot}
        return 200, "application/json", json.dumps(payload).encode("utf-8")

    def _repo_file(self, rel):
        path = core.safe_image_path(self.root, rel)
        if path is None:
            return _message_page(404, "Not found", "That file is not an image inside this repo.")
        ctype = IMAGE_TYPES.get(path.suffix.lower()) or mimetypes.guess_type(path.name)[0] or "application/octet-stream"
        return 200, ctype, path.read_bytes()

    def _static_file(self, rel):
        path = (self.static_dir / rel).resolve()
        if path.parent != self.static_dir or path.suffix not in STATIC_TYPES or not path.is_file():
            return _message_page(404, "Not found", "No such file.")
        return 200, STATIC_TYPES[path.suffix], path.read_bytes()

    def _page(self, query):
        user = (query.get("user") or [self.default_user or ""])[0]
        if not core.valid_username(user):
            return _message_page(400, "Invalid username", f"“{user}” is not a valid GitHub username.")
        readme_path = self.root / "README.md"
        if not readme_path.is_file():
            return _message_page(400, "README.md not found", f"There is no README.md in {self.root}.")

        profile_key = f"profile-{user.lower()}"
        if query.get("refresh"):
            self.cache.drop(profile_key)
        profile = self.cache.get(profile_key)
        if profile is None:
            try:
                profile = self.fetch_profile(user)
            except ProfileNotFound:
                return _message_page(404, "Profile not found", f"GitHub has no profile page for “{user}”.")
            except OSError as error:
                return _message_page(502, "Could not reach GitHub", str(error))
            self.cache.put(profile_key, profile)

        rendered, warning = self._rendered_readme(readme_path.read_text(encoding="utf-8"))
        if rendered is None:
            return _message_page(502, "Could not render the README", warning)
        image = (query.get("img") or [""])[0]
        if image and core.safe_image_path(self.root, image):
            rendered = core.swap_image(core.rewrite_relative_srcs(rendered, self.origin), image, self.origin)
        if warning:
            rendered = f'<div class="preview-warning" style="padding:8px 12px;margin-bottom:16px;background:Mark;color:MarkText">⚠ {html.escape(warning)}</div>' + rendered
        try:
            page = core.build_page(profile, rendered, self.origin)
        except core.NoReadmeContainer as error:
            return _message_page(200, "Nothing to replace", f"{error}. Create the profile repo (a public repo named exactly like the username) on GitHub first.")
        return 200, HTML, page.encode("utf-8")

    def _rendered_readme(self, text):
        """Return (html, warning). html is None when nothing could be rendered."""
        key = "readme-" + hashlib.sha256(f"{self.context}\n{text}".encode("utf-8")).hexdigest()[:16]
        cached = self.cache.get(key)
        if cached is not None:
            return cached, None
        try:
            rendered = self.render_markdown(text, self.context)
        except RenderError as error:
            hint = " Set a GITHUB_TOKEN environment variable to raise GitHub's rate limit." if error.rate_limited else ""
            last = self.cache.get(LAST_RENDER_KEY)
            if last is not None:
                return last, f"Showing the last successful render. {error}.{hint}"
            return None, f"{error}.{hint}"
        previous = self.cache.get(LAST_RENDER_KEY_NAME)
        if previous and previous != key:
            self.cache.drop(previous)
        self.cache.put(key, rendered)
        self.cache.put(LAST_RENDER_KEY_NAME, key)
        self.cache.put(LAST_RENDER_KEY, rendered)
        return rendered, None
