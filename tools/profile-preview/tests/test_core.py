"""Unit tests for the pure logic of the profile previewer (no network)."""
import os
import sys
import tempfile
import time
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import preview_core as core  # noqa: E402


class OwnerFromRemote(unittest.TestCase):
    def test_parses_https_remote(self):
        self.assertEqual(core.owner_from_remote("https://github.com/ashababnoor/ashababnoor.git"), "ashababnoor")


    def test_parses_scp_style_ssh_remote(self):
        self.assertEqual(core.owner_from_remote("git@github.com:ashababnoor/ashababnoor.git"), "ashababnoor")


    def test_returns_none_for_non_github_or_junk(self):
        self.assertIsNone(core.owner_from_remote("https://gitlab.com/someone/repo.git"))
        self.assertIsNone(core.owner_from_remote(""))
        self.assertIsNone(core.owner_from_remote("not a remote"))


class ValidUsername(unittest.TestCase):
    def test_accepts_normal_usernames(self):
        for name in ("ashababnoor", "a", "some-one", "User123"):
            self.assertTrue(core.valid_username(name), name)

    def test_rejects_path_tricks_and_bad_characters(self):
        for name in ("", "../etc", "a/b", "-start", "end-" * 20, "has space", "x" * 40, "a.b"):
            self.assertFalse(core.valid_username(name), name)


class SafeImagePath(unittest.TestCase):
    def setUp(self):
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name).resolve()
        (self.root / "assets").mkdir()
        (self.root / "assets" / "banner.svg").write_text("<svg/>")
        (self.root / "README.md").write_text("# hi")
        (self.root / ".git").mkdir()
        (self.root / ".git" / "x.png").write_bytes(b"png")
        (self.root / "secret.svg").write_text("<svg/>")
        self.addCleanup(self._tmp.cleanup)

    def test_allows_an_image_inside_the_repo(self):
        self.assertEqual(core.safe_image_path(self.root, "assets/banner.svg"), self.root / "assets" / "banner.svg")

    def test_blocks_parent_directory_traversal(self):
        outside = self.root.parent / "outside.svg"
        outside.write_text("<svg/>")
        self.addCleanup(outside.unlink)
        self.assertIsNone(core.safe_image_path(self.root, "../outside.svg"))
        self.assertIsNone(core.safe_image_path(self.root, "assets/../../outside.svg"))

    def test_blocks_absolute_paths(self):
        self.assertIsNone(core.safe_image_path(self.root, str(self.root / "assets" / "banner.svg")))

    def test_blocks_hidden_directories(self):
        self.assertIsNone(core.safe_image_path(self.root, ".git/x.png"))

    def test_blocks_non_image_files(self):
        self.assertIsNone(core.safe_image_path(self.root, "README.md"))


    def test_blocks_a_symlink_that_points_outside_the_repo(self):
        outside = self.root.parent / "linked-target.svg"
        outside.write_text("<svg/>")
        self.addCleanup(outside.unlink)
        link = self.root / "assets" / "link.svg"
        os.symlink(outside, link)
        self.assertIsNone(core.safe_image_path(self.root, "assets/link.svg"))


class ListVersions(unittest.TestCase):
    def make(self, readme):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        for rel in ("assets/banner-v1.0.svg", "assets/banner-v1.1.svg", "assets/banner-v2.png",
                    "assets/other.png", "_assets/banner-v1.0.svg", "docs/banner-v9.svg"):
            (root / rel).parent.mkdir(parents=True, exist_ok=True)
            (root / rel).write_bytes(b"x")
        (root / "assets" / "notes.txt").write_text("x")
        (root / "README.md").write_text(readme)
        return root

    def test_lists_every_version_of_a_readme_image_from_assets_only(self):
        root = self.make('<img src="assets/banner-v1.0.svg" width="100%">')
        self.assertEqual(
            core.list_versions(root, root.joinpath("README.md").read_text()),
            ["assets/banner-v1.0.svg", "assets/banner-v1.1.svg", "assets/banner-v2.png"],
        )

    def test_finds_markdown_images_and_ignores_remote_ones(self):
        root = self.make("![b](./assets/banner-v1.1.svg)\n![x](https://example.com/other.png)")
        self.assertEqual(
            core.list_versions(root, root.joinpath("README.md").read_text()),
            ["assets/banner-v1.0.svg", "assets/banner-v1.1.svg", "assets/banner-v2.png"],
        )

    def test_lists_nothing_when_the_readme_has_no_local_images(self):
        root = self.make("# hi\n![x](https://example.com/other.png)")
        self.assertEqual(core.list_versions(root, root.joinpath("README.md").read_text()), [])


class RewriteRelativeSrcs(unittest.TestCase):
    def test_rewrites_relative_image_sources_to_the_local_route(self):
        html = '<img src="assets/banner.svg" width="100%">'
        self.assertEqual(core.rewrite_relative_srcs(html), '<img src="/repo/assets/banner.svg" width="100%">')

    def test_handles_dot_slash_and_single_quotes(self):
        self.assertEqual(core.rewrite_relative_srcs("<img src='./a/b.png'>"), "<img src='/repo/a/b.png'>")

    def test_rewrites_srcset_on_picture_sources_too(self):
        html = '<picture><source media="(max-width: 600px)" srcset="assets/m.svg"><img src="assets/d.svg"></picture>'
        out = core.rewrite_relative_srcs(html, "http://h:1")
        self.assertIn('srcset="http://h:1/repo/assets/m.svg"', out)
        self.assertIn('src="http://h:1/repo/assets/d.svg"', out)

    def test_rewrites_each_candidate_in_a_srcset_list(self):
        out = core.rewrite_relative_srcs('<source srcset="a.png 1x, https://x.com/b.png 2x">')
        self.assertEqual(out, '<source srcset="/repo/a.png 1x, https://x.com/b.png 2x">')

    def test_leaves_absolute_protocol_relative_data_and_rooted_sources_alone(self):
        for src in ("https://x.com/a.png", "http://x.com/a.png", "//x.com/a.png", "data:image/png;base64,AAAA", "/already/rooted.png"):
            html = f'<img src="{src}">'
            self.assertEqual(core.rewrite_relative_srcs(html), html, src)


class SwapImage(unittest.TestCase):
    def test_replaces_the_image_that_is_another_version_of_the_chosen_one(self):
        html = '<img src="/repo/assets/logo.png" alt="1"><img src="/repo/assets/banner-v1.0.svg" alt="2">'
        out = core.swap_image(html, "assets/banner-v1.2.svg")
        self.assertEqual(out, '<img src="/repo/assets/logo.png" alt="1"><img src="/repo/assets/banner-v1.2.svg" alt="2">')

    def test_falls_back_to_the_first_image_when_none_matches(self):
        html = '<img src="/repo/a.svg" alt="1"><img src="/repo/b.svg" alt="2">'
        out = core.swap_image(html, "assets/new.svg")
        self.assertEqual(out, '<img src="/repo/assets/new.svg" alt="1"><img src="/repo/b.svg" alt="2">')


class BuildPage(unittest.TestCase):
    PROFILE = (
        "<html><head><title>x</title><script>evil()</script></head><body>"
        '<script src="https://github.githubassets.com/a.js"></script>'
        '<article class="markdown-body entry-content" itemprop="text"><p>OLD README</p></article>'
        "<footer>kept</footer></body></html>"
    )

    def test_replaces_the_readme_container_contents(self):
        out = core.build_page(self.PROFILE, "<h1>NEW</h1>")
        self.assertIn("<h1>NEW</h1>", out)
        self.assertNotIn("OLD README", out)
        self.assertIn("<footer>kept</footer>", out)

    def test_keeps_the_container_tag_so_github_styles_still_apply(self):
        out = core.build_page(self.PROFILE, "<h1>NEW</h1>")
        self.assertIn('<article class="markdown-body entry-content" itemprop="text"><h1>NEW</h1></article>', out)

    def test_strips_scripts_and_adds_a_base_href(self):
        out = core.build_page(self.PROFILE, "<h1>NEW</h1>")
        self.assertNotIn("<script", out)
        self.assertIn('<base href="https://github.com/">', out)

    def test_rewrites_relative_images_inside_the_readme(self):
        out = core.build_page(self.PROFILE, '<img src="assets/x.svg">')
        self.assertIn('<img src="/repo/assets/x.svg">', out)

    def test_raises_when_the_profile_has_no_readme_container(self):
        with self.assertRaises(core.NoReadmeContainer):
            core.build_page("<html><head></head><body>none</body></html>", "<h1>NEW</h1>")

    def test_does_not_treat_backslashes_in_the_readme_as_regex_escapes(self):
        out = core.build_page(self.PROFILE, r"<p>C:\new\1 and \g<0></p>")
        self.assertIn(r"<p>C:\new\1 and \g<0></p>", out)


class Fingerprint(unittest.TestCase):
    def test_changes_when_a_file_is_edited_or_added(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            readme = root / "README.md"
            readme.write_text("one")
            before = core.fingerprint(root)
            self.assertEqual(before, core.fingerprint(root))
            time.sleep(0.01)
            readme.write_text("two!")
            after_edit = core.fingerprint(root)
            self.assertNotEqual(before, after_edit)
            (root / "pic.svg").write_text("<svg/>")
            self.assertNotEqual(after_edit, core.fingerprint(root))


class ReadmeVersions(unittest.TestCase):
    def make(self, names):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        root = Path(tmp.name)
        for name in names:
            (root / name).parent.mkdir(parents=True, exist_ok=True)
            (root / name).write_text("x")
        return root

    def test_lists_readme_variants_in_the_repo_root_with_the_main_one_first(self):
        root = self.make(["README-v2.md", "README.md", "README-v10.md", "README-v3.md", "notes.md", "README.txt",
                          "versions/v1.0.md", "docs/README.md", ".README-hidden.md"])
        self.assertEqual(core.list_readmes(root), ["README.md", "README-v2.md", "README-v3.md", "README-v10.md"])

    def test_lists_nothing_when_there_is_no_readme_at_all(self):
        self.assertEqual(core.list_readmes(self.make(["notes.md"])), [])

    def test_resolves_only_listed_readme_names(self):
        root = self.make(["README.md", "README-v2.md", "secret.md", "versions/v1.0.md"])
        self.assertEqual(core.readme_path(root, "README-v2.md"), (root / "README-v2.md"))
        for bad in ("secret.md", "../README.md", "versions/v1.0.md", "/etc/passwd", "README-v9.md", ""):
            self.assertIsNone(core.readme_path(root, bad), bad)

    def test_fingerprint_notices_edits_to_any_readme_variant(self):
        root = self.make(["README.md", "README-v2.md"])
        before = core.fingerprint(root)
        (root / "README-v2.md").write_text("longer text")
        edited = core.fingerprint(root)
        self.assertNotEqual(before, edited)
        (root / "README-v3.md").write_text("new")
        self.assertNotEqual(edited, core.fingerprint(root))


class StaticFingerprint(unittest.TestCase):
    def test_changes_when_a_ui_file_is_edited_or_added(self):
        with tempfile.TemporaryDirectory() as tmp:
            folder = Path(tmp)
            (folder / "bar.js").write_text("a")
            before = core.static_fingerprint(folder)
            self.assertEqual(before, core.static_fingerprint(folder))
            (folder / "bar.js").write_text("bb")
            edited = core.static_fingerprint(folder)
            self.assertNotEqual(before, edited)
            (folder / "bar.css").write_text("x")
            self.assertNotEqual(edited, core.static_fingerprint(folder))


class DiskCache(unittest.TestCase):
    def test_round_trips_text_and_misses_cleanly(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = core.DiskCache(Path(tmp) / ".cache")
            self.assertIsNone(cache.get("profile-someone"))
            cache.put("profile-someone", "<html/>")
            self.assertEqual(cache.get("profile-someone"), "<html/>")


    def test_rejects_keys_that_could_escape_the_cache_folder(self):
        with tempfile.TemporaryDirectory() as tmp:
            cache = core.DiskCache(Path(tmp) / ".cache")
            with self.assertRaises(ValueError):
                cache.put("../evil", "x")


if __name__ == "__main__":
    unittest.main()
