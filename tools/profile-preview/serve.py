#!/usr/bin/env python3
"""Preview your local README.md inside a real GitHub profile page.

    python3 tools/profile-preview/serve.py [username] [--port 8765] [--no-open]

Standard library only. See README.md in this folder.
"""
import argparse
import json
import os
import subprocess
import sys
import threading
import time
import urllib.error
import urllib.request
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))

import preview_app  # noqa: E402
import preview_core as core  # noqa: E402

USER_AGENT = "profile-preview (local README previewer)"
TIMEOUT = 20


def git(*args, cwd):
    try:
        out = subprocess.run(["git", *args], cwd=cwd, capture_output=True, text=True, check=True)
        return out.stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        return ""


def fetch_profile(user):
    request = urllib.request.Request(f"https://github.com/{user}", headers={"User-Agent": USER_AGENT})
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            return response.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as error:
        if error.code == 404:
            raise preview_app.ProfileNotFound(user) from error
        raise OSError(f"GitHub answered HTTP {error.code}") from error
    except urllib.error.URLError as error:
        raise OSError(str(error.reason)) from error


def render_markdown(text, context):
    headers = {"User-Agent": USER_AGENT, "Content-Type": "application/json", "Accept": "application/vnd.github+json"}
    token = os.environ.get("GITHUB_TOKEN")
    if token:
        headers["Authorization"] = f"Bearer {token}"
    body = json.dumps({"text": text, "mode": "gfm", "context": context}).encode("utf-8")
    request = urllib.request.Request("https://api.github.com/markdown", data=body, headers=headers, method="POST")
    try:
        with urllib.request.urlopen(request, timeout=TIMEOUT) as response:
            return response.read().decode("utf-8")
    except urllib.error.HTTPError as error:
        limited = error.code in (403, 429)
        raise preview_app.RenderError(f"GitHub's markdown renderer answered HTTP {error.code}", rate_limited=limited) from error
    except urllib.error.URLError as error:
        raise preview_app.RenderError(f"Could not reach GitHub's markdown renderer ({error.reason})") from error


def watch_own_code(poll_seconds=1.0):
    """Restart this process when its own Python files change (the page then reloads itself)."""
    files = sorted(HERE.glob("*.py"))
    stamp = lambda: [f.stat().st_mtime_ns for f in files]  # noqa: E731
    seen = stamp()

    def loop():
        nonlocal seen
        while True:
            time.sleep(poll_seconds)
            try:
                now = stamp()
            except OSError:
                continue
            if now != seen:
                argv = [sys.executable, *sys.argv] + ([] if "--no-open" in sys.argv else ["--no-open"])
                os.execv(sys.executable, argv)

    threading.Thread(target=loop, daemon=True).start()


def make_handler(app):
    class Handler(BaseHTTPRequestHandler):
        def do_GET(self):
            status, ctype, body = app.handle(self.path)
            self.send_response(status)
            self.send_header("Content-Type", ctype)
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)

        def log_message(self, *_args):
            pass

    return Handler


def main(argv=None):
    parser = argparse.ArgumentParser(description="Preview this repo's README.md inside a real GitHub profile page.")
    parser.add_argument("user", nargs="?", help="GitHub username to show (default: owner of the 'origin' remote)")
    parser.add_argument("--port", type=int, default=8765)
    parser.add_argument("--no-open", action="store_true", help="do not open the browser")
    args = parser.parse_args(argv)

    root = Path(git("rev-parse", "--show-toplevel", cwd=HERE) or Path.cwd())
    user = args.user or core.owner_from_remote(git("remote", "get-url", "origin", cwd=root))
    if not user or not core.valid_username(user):
        parser.error("could not work out a GitHub username; pass one, e.g. serve.py octocat")

    app = preview_app.PreviewApp(
        root=root,
        cache_dir=HERE / ".cache",
        default_user=user,
        context=f"{user}/{user}",
        fetch_profile=fetch_profile,
        render_markdown=render_markdown,
        static_dir=HERE / "static",
        origin=f"http://127.0.0.1:{args.port}",
    )
    server = ThreadingHTTPServer(("127.0.0.1", args.port), make_handler(app))
    url = f"http://127.0.0.1:{args.port}/"
    print(f"Previewing {root / 'README.md'} as {user}\n  {url}\nCtrl+C to stop.")
    if not args.no_open:
        threading.Timer(0.3, webbrowser.open, args=(url,)).start()
    watch_own_code()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print()
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
