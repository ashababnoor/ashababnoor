# Profile preview

See your local `README.md` inside your real GitHub profile page, before you push.

```bash
python3 tools/profile-preview/serve.py            # uses the owner of the `origin` remote
python3 tools/profile-preview/serve.py octocat    # or start on another username
```

Python 3 standard library only, nothing to install. Your browser opens on `http://127.0.0.1:8765/`.

## How it works

- Downloads the profile page of the chosen user, then swaps its README section for this repo's `README.md`, rendered by GitHub's own markdown API. Theme, fonts and layout are GitHub's.
- Images in the README (e.g. `assets/banner.svg`) are served from this repo, so unpushed images show up too.
- Saving `README.md` or any image reloads the preview and keeps your scroll position. Editing the previewer itself works too: UI files (`static/`) reload the page, and Python files restart the server and then reload the page.

## The top bar

| Control | What it does |
|---|---|
| Profile + Show | View any GitHub username with your README in it. Each username is downloaded once and cached. |
| Refresh profile | Download that profile page again. |
| Theme | Auto (system), Light or Dark buttons. Sets GitHub's own theme, so SVGs that follow `prefers-color-scheme` switch too. |
| Display | Desktop, tablet or phone. |
| Image version | One button per version of an image your README uses (`banner-v1.0.svg`, `banner-v1.1.svg`, …; the `-vX.Y` part is ignored, only `assets/` is searched). Click one to preview it in place of the README's image, without editing. "README" shows it as written. |

## Good to know

- Cached downloads live in `tools/profile-preview/.cache/` (gitignored).
- The markdown API allows 60 requests an hour without a token. Unchanged READMEs are cached, but if you hit the limit set `GITHUB_TOKEN` and restart. Meanwhile the last good render is shown with a warning.
- The server listens on `127.0.0.1` only.
- Options: `--port 9000`, `--no-open`.

## Tests

```bash
cd tools/profile-preview && python3 -m unittest discover -s tests
```
