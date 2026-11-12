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


class ResolveSrc(unittest.TestCase):
    def test_resolves_a_source_from_the_readmes_own_folder(self):
        self.assertEqual(core.resolve_src("assets/a.svg", ""), "assets/a.svg")
        self.assertEqual(core.resolve_src("./assets/a.svg", ""), "assets/a.svg")
        self.assertEqual(core.resolve_src("../assets/a.svg", "versions"), "assets/a.svg")
        self.assertEqual(core.resolve_src("../github-metrics.svg?v=1", "versions"), "github-metrics.svg")

    def test_decodes_url_escapes_and_html_entities_to_the_real_file_name(self):
        self.assertEqual(core.resolve_src("assets/a%20b.svg", ""), "assets/a b.svg")
        self.assertEqual(core.resolve_src("assets/a&amp;b.svg", ""), "assets/a&b.svg")

    def test_returns_none_outside_the_repo_and_for_remote_or_rooted_sources(self):
        for src, base in (("../a.svg", ""), ("../../a.svg", "versions"), ("https://x.com/a.png", ""),
                          ("//x.com/a.png", ""), ("/rooted.png", ""), ("data:image/png;base64,AA", "")):
            self.assertIsNone(core.resolve_src(src, base), src)


class ListSlots(unittest.TestCase):
    FILES = (
        "assets/banners/v1/banner-desktop-v1.0.svg", "assets/banners/v1/banner-desktop-slim-v1.0.svg",
        "assets/banners/v1/banner-tablet-v1.0.svg", "assets/banners/v1/banner-mobile-v1.0.svg",
        "assets/banners/v2/banner-desktop-v2.0.svg", "assets/banners/v2/notes.txt",
        "assets/icons/user.svg", "assets/icons/link.svg", "assets/icons/try/mail.svg",
        "assets/banner-desktop-v0.svg", "github-metrics.svg",
    )
    README = (
        "<picture>\n"
        '  <source media="(max-width: 600px)" srcset="{p}assets/banners/v1/banner-mobile-v1.0.svg">\n'
        '  <source media="(min-width: 601px)" srcset="{p}assets/banners/v1/banner-tablet-v1.0.svg">\n'
        '  <img src="{p}assets/banners/v1/banner-desktop-v1.0.svg" width="100%">\n'
        "</picture>\n\n"
        '### <img src="{p}assets/icons/user.svg" width="18" alt=""> About Me\n\n'
        '<img src="{p}github-metrics.svg">\n\n'
        '### <img src="{p}assets/icons/link.svg" width="18" alt=""> Connect With Me\n'
    )

    def setUp(self):
        tmp = tempfile.TemporaryDirectory()
        self.addCleanup(tmp.cleanup)
        self.root = Path(tmp.name)
        for rel in self.FILES:
            (self.root / rel).parent.mkdir(parents=True, exist_ok=True)
            (self.root / rel).write_bytes(b"x")

    def slots(self, text=None, base=""):
        return core.list_slots(self.root, self.README.format(p="") if text is None else text, base)

    def test_banner_slots_come_in_display_order(self):
        banners = [(s["label"], s["id"]) for s in self.slots() if s["group"] == "Banners"]
        self.assertEqual(banners, [
            ("Desktop", "assets/banners/v1/banner-desktop-v1.0.svg"),
            ("Tablet", "assets/banners/v1/banner-tablet-v1.0.svg"),
            ("Mobile", "assets/banners/v1/banner-mobile-v1.0.svg"),
        ])

    def test_a_banner_slot_offers_every_banner_whose_name_starts_with_its_own(self):
        desktop = self.slots()[0]
        self.assertEqual(desktop["options"], [
            "assets/banners/v1/banner-desktop-v1.0.svg",
            "assets/banners/v1/banner-desktop-slim-v1.0.svg",
            "assets/banners/v2/banner-desktop-v2.0.svg",
        ])
        self.assertEqual(self.slots()[2]["options"], ["assets/banners/v1/banner-mobile-v1.0.svg"])

    def test_icon_slots_are_named_by_their_heading_and_offer_every_icon(self):
        icons = [s for s in self.slots() if s["group"] == "Icons"]
        self.assertEqual([(s["label"], s["id"]) for s in icons],
                         [("About Me", "assets/icons/user.svg"), ("Connect With Me", "assets/icons/link.svg")])
        self.assertEqual(icons[0]["options"],
                         ["assets/icons/link.svg", "assets/icons/try/mail.svg", "assets/icons/user.svg"])

    def test_an_icon_outside_a_heading_is_named_by_its_alt_text_or_file_name(self):
        labels = [s["label"] for s in self.slots('<img src="assets/icons/user.svg" alt="Me"> <img src="assets/icons/link.svg">')]
        self.assertEqual(labels, ["Me", "link"])

    def test_alt_text_is_found_wherever_it_sits_in_the_tag(self):
        labels = [s["label"] for s in self.slots('<img alt="Me" width="18" src="assets/icons/user.svg">')]
        self.assertEqual(labels, ["Me"])

    def test_data_src_attributes_are_not_image_sources(self):
        self.assertEqual(self.slots('<img data-src="assets/icons/user.svg" src="https://x.com/y.png">'), [])

    def test_images_outside_banners_and_icons_get_no_slot(self):
        ids = [s["id"] for s in self.slots()]
        self.assertNotIn("github-metrics.svg", ids)
        self.assertEqual(self.slots('<img src="assets/banner-desktop-v0.svg">'), [])

    def test_a_readme_in_versions_resolves_its_paths_from_that_folder(self):
        self.assertEqual(self.slots(self.README.format(p="../"), "versions"), self.slots())

    def test_lists_nothing_when_the_readme_has_no_local_images(self):
        self.assertEqual(self.slots("# hi\n![x](https://example.com/other.png)"), [])


class RewriteRelativeSrcs(unittest.TestCase):
    def test_rewrites_relative_image_sources_to_the_local_route(self):
        html = '<img src="assets/banner.svg" width="100%">'
        self.assertEqual(core.rewrite_relative_srcs(html),
                         '<img src="/repo/assets/banner.svg" data-preview-src="assets/banner.svg" width="100%">')

    def test_handles_dot_slash_and_single_quotes(self):
        self.assertEqual(core.rewrite_relative_srcs("<img src='./a/b.png'>"),
                         "<img src='/repo/a/b.png' data-preview-src=\"a/b.png\">")

    def test_rewrites_srcset_on_picture_sources_too(self):
        html = '<picture><source media="(max-width: 600px)" srcset="assets/m.svg"><img src="assets/d.svg"></picture>'
        out = core.rewrite_relative_srcs(html, "http://h:1")
        self.assertIn('srcset="http://h:1/repo/assets/m.svg"', out)
        self.assertIn('src="http://h:1/repo/assets/d.svg"', out)

    def test_rewrites_each_candidate_in_a_srcset_list(self):
        out = core.rewrite_relative_srcs('<source srcset="a.png 1x, https://x.com/b.png 2x">')
        self.assertEqual(out, '<source srcset="/repo/a.png 1x, https://x.com/b.png 2x" data-preview-srcset="a.png">')

    def test_leaves_absolute_protocol_relative_data_and_rooted_sources_alone(self):
        for src in ("https://x.com/a.png", "http://x.com/a.png", "//x.com/a.png", "data:image/png;base64,AAAA", "/already/rooted.png"):
            html = f'<img src="{src}">'
            self.assertEqual(core.rewrite_relative_srcs(html), html, src)


class RewriteWithBaseAndSwaps(unittest.TestCase):
    def test_resolves_sources_from_the_readmes_folder(self):
        out = core.rewrite_relative_srcs('<img src="../assets/a.svg?v=1">', base="versions")
        self.assertEqual(out, '<img src="/repo/assets/a.svg?v=1" data-preview-src="assets/a.svg">')

    def test_encodes_file_names_so_spaces_survive_in_src_and_srcset(self):
        html = '<source srcset="assets/m.svg"><img src="assets/a%20b.svg">'
        out = core.rewrite_relative_srcs(html, swaps={"assets/m.svg": "assets/m 2.svg"})
        self.assertEqual(out, (
            '<source srcset="/repo/assets/m%202.svg" data-preview-srcset="assets/m.svg">'
            '<img src="/repo/assets/a%20b.svg" data-preview-src="assets/a b.svg">'
        ))

    def test_leaves_sources_that_would_leave_the_repo_alone(self):
        self.assertEqual(core.rewrite_relative_srcs('<img src="../x.svg">'), '<img src="../x.svg">')

    def test_swaps_img_and_picture_sources_by_their_original_path(self):
        html = '<picture><source srcset="assets/m.svg"><img src="assets/d.svg"></picture><img src="assets/d.svg">'
        out = core.rewrite_relative_srcs(html, swaps={"assets/d.svg": "assets/d2.svg", "assets/m.svg": "assets/m2.svg"})
        self.assertEqual(out, (
            '<picture><source srcset="/repo/assets/m2.svg" data-preview-srcset="assets/m.svg">'
            '<img src="/repo/assets/d2.svg" data-preview-src="assets/d.svg"></picture>'
            '<img src="/repo/assets/d2.svg" data-preview-src="assets/d.svg">'
        ))


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
        self.assertIn('<img src="/repo/assets/x.svg" data-preview-src="assets/x.svg">', out)

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
        self.assertEqual(core.list_readmes(root),
                         ["README.md", "README-v2.md", "README-v3.md", "README-v10.md", "versions/v1.0.md"])

    def test_lists_saved_versions_after_the_root_readmes(self):
        root = self.make(["README.md", "README-v2.md", "versions/v10.0.md", "versions/v2.0.md", "versions/notes.txt"])
        self.assertEqual(core.list_readmes(root), ["README.md", "README-v2.md", "versions/v2.0.md", "versions/v10.0.md"])
        self.assertEqual(core.readme_path(root, "versions/v2.0.md"), root / "versions" / "v2.0.md")
        self.assertIsNone(core.readme_path(root, "versions/../README.md"))

    def test_lists_nothing_when_there_is_no_readme_at_all(self):
        self.assertEqual(core.list_readmes(self.make(["notes.md"])), [])

    def test_resolves_only_listed_readme_names(self):
        root = self.make(["README.md", "README-v2.md", "secret.md", "docs/README.md"])
        self.assertEqual(core.readme_path(root, "README-v2.md"), (root / "README-v2.md"))
        for bad in ("secret.md", "../README.md", "docs/README.md", "/etc/passwd", "README-v9.md", ""):
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
