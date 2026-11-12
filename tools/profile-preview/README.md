# Profile preview

See your local `README.md` inside your real GitHub profile page, before you push.

```bash
python3 tools/profile-preview/serve.py            # uses the owner of the `origin` remote
python3 tools/profile-preview/serve.py octocat    # or start on another username
```

Python 3 standard library only, nothing to install. Your browser opens on `http://127.0.0.1:8765/`.

## How it works

- Downloads the profile page of the chosen user, then swaps its README section for this repo's `README.md` (or another README you pick), rendered by GitHub's own markdown API the way GitHub renders a README file. Theme, fonts and layout are GitHub's.
- Images in the README (e.g. `assets/icons/user.svg`) are served from this repo, so unpushed images show up too.
- Saving a README or any image reloads the preview and keeps your scroll position. Editing the previewer itself works too: UI files (`static/`) reload the page, and Python files restart the server and then reload the page.

## The panel

| Control | What it does |
|---|---|
| Profile + Show | View any GitHub username with your README in it. Each username is downloaded once and cached. |
| Refresh profile | Download that profile page again. |
| Theme | Auto (system), Light or Dark. Sets GitHub's own theme, so SVGs that follow `prefers-color-scheme` switch too. |
| Display | Desktop, tablet or phone. |
| Panel | Dock the panel at the top or on the left. |
| README | Pick which file to preview: `README.md`, other READMEs in the repo root (`README-v2.md`, …) and the saved versions in `versions/`. Image paths are read from the file's own folder, as on GitHub, so `../assets/…` works in `versions/`. |
| Images | Try another image in place of one the README uses, without editing it. Pick a slot, then an image. A ● marks slots you changed; "Reset all" shows the README as written. |

**Image slots**

- **Banners:** every image the README uses from `assets/banners/`, including the `<picture>` sources, so desktop, tablet and mobile each get a slot. A slot offers every banner in `assets/banners/` (all version folders) whose name starts with its own, so `banner-desktop` also offers `banner-desktop-slim`.
- **Icons:** every image the README uses from `assets/icons/`, named after the heading it sits in. A slot offers every image in `assets/icons/`, subfolders included. To try a new icon, drop it in that folder; it doesn't need to be committed.

Drag the panel's inner edge to resize it; double-click the edge to reset. The tab on the edge hides the panel so the preview gets the full space. The tool remembers the panel's position, size and visibility, your theme, display and README, and the images you picked.

## Good to know

- Cached downloads live in `tools/profile-preview/.cache/` (gitignored).
- The markdown API allows 60 requests an hour without a token. Unchanged READMEs are cached, but if you hit the limit set `GITHUB_TOKEN` and restart. Meanwhile the last good render is shown with a warning.
- The server listens on `127.0.0.1` only.
- Options: `--port 9000`, `--no-open`.

## Tests

```bash
cd tools/profile-preview && python3 -m unittest discover -s tests
```
