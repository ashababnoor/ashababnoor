"""Tests for the request handling of the previewer. The network is faked."""
import json
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import preview_app  # noqa: E402
import preview_core as core  # noqa: E402

PROFILE = (
    "<html><head><title>profile</title></head><body>"
    '<article class="markdown-body entry-content"><p>OLD</p></article></body></html>'
)


class FakeNetwork:
    def __init__(self):
        self.profile_calls = []
        self.render_calls = []
        self.render_error = None
        self.missing_users = set()

    def fetch_profile(self, user):
        self.profile_calls.append(user)
        if user in self.missing_users:
            raise preview_app.ProfileNotFound(user)
        return PROFILE.replace("profile", f"profile-of-{user}")

    def render_markdown(self, text, context):
        self.render_calls.append(text)
        if self.render_error:
            raise self.render_error
        return f"<h1>rendered:{text.strip()}</h1>"


class AppTestCase(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self._tmp.cleanup)
        self.root = Path(self._tmp.name).resolve()
        (self.root / "README.md").write_text("hello")
        (self.root / "assets").mkdir()
        (self.root / "assets" / "a.svg").write_text("<svg xmlns='http://www.w3.org/2000/svg'/>")
        self.net = FakeNetwork()
        self.app = preview_app.PreviewApp(
            root=self.root,
            cache_dir=self.root / "cache",
            default_user="someone",
            context="someone/someone",
            fetch_profile=self.net.fetch_profile,
            render_markdown=self.net.render_markdown,
            static_dir=Path(__file__).resolve().parent.parent / "static",
        )

    def get(self, path):
        status, ctype, body = self.app.handle(path)
        return status, ctype, body.decode("utf-8", "replace")


class PageRoute(AppTestCase):
    def test_shows_the_local_readme_inside_the_users_profile_page(self):
        status, ctype, body = self.get("/page?user=someone")
        self.assertEqual(status, 200)
        self.assertTrue(ctype.startswith("text/html"))
        self.assertIn("<h1>rendered:hello</h1>", body)
        self.assertIn("profile-of-someone", body)
        self.assertNotIn("OLD", body)

    def test_does_not_refetch_a_profile_it_already_has(self):
        self.get("/page?user=someone")
        self.get("/page?user=someone")
        self.assertEqual(self.net.profile_calls, ["someone"])

    def test_fetches_each_new_username_once(self):
        self.get("/page?user=someone")
        self.get("/page?user=other")
        self.get("/page?user=someone")
        self.get("/page?user=other")
        self.assertEqual(self.net.profile_calls, ["someone", "other"])

    def test_refresh_forces_a_new_fetch(self):
        self.get("/page?user=someone")
        self.get("/page?user=someone&refresh=1")
        self.assertEqual(self.net.profile_calls, ["someone", "someone"])

    def test_does_not_re_render_an_unchanged_readme_but_does_after_an_edit(self):
        self.get("/page?user=someone")
        self.get("/page?user=someone")
        self.assertEqual(len(self.net.render_calls), 1)
        (self.root / "README.md").write_text("changed")
        _status, _ctype, body = self.get("/page?user=someone")
        self.assertEqual(len(self.net.render_calls), 2)
        self.assertIn("rendered:changed", body)

    def test_keeps_only_the_latest_render_in_the_cache(self):
        for text in ("one", "two", "three"):
            (self.root / "README.md").write_text(text)
            self.get("/page?user=someone")
        renders = [p.name for p in (self.root / "cache").iterdir() if p.name.startswith("readme-")]
        self.assertEqual(len(renders), 1)

    def test_readme_images_point_at_this_server_not_at_the_github_base(self):
        # The profile page has <base href="https://github.com/">, so a bare
        # /repo/... path would resolve to github.com and the image would break.
        app = preview_app.PreviewApp(
            root=self.root, cache_dir=self.root / "cache2", default_user="someone",
            context="someone/someone", fetch_profile=self.net.fetch_profile,
            render_markdown=lambda text, context: '<img src="assets/a.svg">',
            static_dir=self.app.static_dir, origin="http://127.0.0.1:9",
        )
        _s, _c, raw = app.handle("/page?user=someone")
        body = raw.decode("utf-8")
        self.assertIn('src="http://127.0.0.1:9/repo/assets/a.svg"', body)

    def test_rejects_an_invalid_username(self):
        status, _ctype, _body = self.get("/page?user=../etc")
        self.assertEqual(status, 400)
        self.assertEqual(self.net.profile_calls, [])

    def test_reports_an_unknown_user(self):
        self.net.missing_users.add("ghost")
        status, _ctype, body = self.get("/page?user=ghost")
        self.assertEqual(status, 404)
        self.assertIn("ghost", body)

    def test_explains_a_missing_readme_file(self):
        (self.root / "README.md").unlink()
        status, _ctype, body = self.get("/page?user=someone")
        self.assertEqual(status, 400)
        self.assertIn("README.md", body)

    def test_explains_a_profile_without_a_readme_section(self):
        self.net.fetch_profile = lambda user: "<html><head></head><body>bare</body></html>"
        self.app.fetch_profile = self.net.fetch_profile
        status, _ctype, body = self.get("/page?user=norepo")
        self.assertEqual(status, 200)
        self.assertIn("no README section", body)

    def test_swaps_the_first_image_when_asked_and_ignores_unsafe_paths(self):
        self.net.render_markdown = lambda text, context: '<img src="assets/a.svg"><img src="assets/b.svg">'
        self.app.render_markdown = self.net.render_markdown
        _s, _c, body = self.get("/page?user=someone&img=assets/a.svg")
        self.assertIn('src="/repo/assets/a.svg"', body)
        _s, _c, body = self.get("/page?user=someone&img=../../etc/passwd.png")
        self.assertNotIn("passwd", body)

    def test_falls_back_to_the_last_good_render_when_rendering_fails(self):
        self.get("/page?user=someone")
        (self.root / "README.md").write_text("changed")
        self.net.render_error = preview_app.RenderError("rate limited", rate_limited=True)
        status, _ctype, body = self.get("/page?user=someone")
        self.assertEqual(status, 200)
        self.assertIn("rendered:hello", body)
        self.assertIn("preview-warning", body)

    def test_tells_you_about_the_token_when_rate_limited_with_nothing_cached(self):
        self.net.render_error = preview_app.RenderError("rate limited", rate_limited=True)
        status, _ctype, body = self.get("/page?user=someone")
        self.assertEqual(status, 502)
        self.assertIn("GITHUB_TOKEN", body)


class ReadmeChoice(AppTestCase):
    def setUp(self):
        super().setUp()
        (self.root / "README-v2.md").write_text('v2 text <img src="assets/a.svg">')

    def test_state_lists_the_readme_variants(self):
        state = json.loads(self.app.handle("/api/state")[2])
        self.assertEqual(state["readmes"], ["README.md", "README-v2.md"])

    def test_page_shows_the_chosen_readme_and_defaults_to_readme_md(self):
        _s, _c, body = self.get("/page?user=someone&readme=README-v2.md")
        self.assertIn("rendered:v2 text", body)
        _s, _c, body = self.get("/page?user=someone")
        self.assertIn("rendered:hello", body)

    def test_page_rejects_a_readme_that_is_not_in_the_list(self):
        for bad in ("../README.md", "notes.md", "README-v9.md"):
            status, _c, _body = self.get("/page?user=someone&readme=" + bad)
            self.assertEqual(status, 400, bad)

    def test_state_image_versions_come_from_the_chosen_readme(self):
        default = json.loads(self.app.handle("/api/state")[2])["images"]
        chosen = json.loads(self.app.handle("/api/state?readme=README-v2.md")[2])["images"]
        self.assertEqual(default, [])
        self.assertEqual(chosen, ["assets/a.svg"])

    def test_state_changes_when_another_readme_is_edited(self):
        first = json.loads(self.app.handle("/api/state")[2])["fingerprint"]
        (self.root / "README-v2.md").write_text("edited, now longer")
        self.assertNotEqual(first, json.loads(self.app.handle("/api/state")[2])["fingerprint"])


class RepoRoute(AppTestCase):
    def test_serves_an_image_with_the_right_content_type(self):
        status, ctype, body = self.get("/repo/assets/a.svg")
        self.assertEqual(status, 200)
        self.assertEqual(ctype, "image/svg+xml")
        self.assertIn("<svg", body)

    def test_blocks_traversal_and_non_images(self):
        self.assertEqual(self.get("/repo/../README.md")[0], 404)
        self.assertEqual(self.get("/repo/README.md")[0], 404)
        self.assertEqual(self.get("/repo/%2e%2e/README.md")[0], 404)


class ShellAndState(AppTestCase):
    def test_the_shell_page_frames_the_preview_for_the_default_user(self):
        status, ctype, body = self.get("/")
        self.assertEqual(status, 200)
        self.assertTrue(ctype.startswith("text/html"))
        self.assertIn('data-default-user="someone"', body)
        self.assertIn('id="frame"', body)

    def test_state_lets_the_page_notice_ui_edits_and_server_restarts(self):
        static = self.root / "static"
        static.mkdir()
        (static / "bar.js").write_text("one")
        app = preview_app.PreviewApp(
            root=self.root, cache_dir=self.root / "c3", default_user="someone", context="x/x",
            fetch_profile=self.net.fetch_profile, render_markdown=self.net.render_markdown, static_dir=static,
        )
        first = json.loads(app.handle("/api/state")[2])
        (static / "bar.js").write_text("two!")
        second = json.loads(app.handle("/api/state")[2])
        self.assertNotEqual(first["ui"], second["ui"])
        self.assertEqual(first["boot"], second["boot"])
        other = preview_app.PreviewApp(
            root=self.root, cache_dir=self.root / "c4", default_user="someone", context="x/x",
            fetch_profile=self.net.fetch_profile, render_markdown=self.net.render_markdown, static_dir=static,
        )
        self.assertNotEqual(first["boot"], json.loads(other.handle("/api/state")[2])["boot"])

    def test_state_reports_a_fingerprint_that_changes_with_the_readme(self):
        (self.root / "README.md").write_text('<img src="assets/a.svg">')
        _s, _c, first = self.get("/api/state")
        (self.root / "README.md").write_text("different and longer")
        _s, _c, second = self.get("/api/state")
        self.assertNotEqual(json.loads(first)["fingerprint"], json.loads(second)["fingerprint"])
        self.assertIn("assets/a.svg", json.loads(first)["images"])


    def test_static_files_are_served_but_cannot_escape_the_static_folder(self):
        self.assertEqual(self.get("/static/bar.js")[0], 200)
        self.assertEqual(self.get("/static/../preview_core.py")[0], 404)


if __name__ == "__main__":
    unittest.main()
