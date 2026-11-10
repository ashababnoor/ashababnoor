// Controls for the profile previewer. The preview itself is an iframe of our own
// server, so we can set GitHub's theme attribute on it, resize it and edit it freely.
(() => {
  const POLL_MS = 1000;
  const STORE_KEY = "profile-preview";
  const REMEMBERED = ["theme", "width", "readme", "barHidden"];
  const THEMES = [["auto", "Auto"], ["light", "Light"], ["dark", "Dark"]];
  const WIDTHS = [["desktop", "Desktop"], ["tablet", "Tablet"], ["phone", "Phone"]];
  const IMAGE_EXT = /\.(svg|png|jpe?g|gif|webp|ico)$/i;
  const VERSION_SUFFIX = /[-_.]?v\d+(?:\.\d+)*$/i;

  const $ = (selector) => document.querySelector(selector);
  const frame = $("#frame");
  const els = { user: $("#user"), theme: $("#theme"), width: $("#width"), versions: $("#versions"), versionsWrap: $("#versions-wrap"), readmes: $("#readmes"), readmesWrap: $("#readmes-wrap"), bar: $("#bar"), toggle: $("#bar-toggle"), status: $("#status") };

  const state = { user: document.documentElement.dataset.defaultUser || "", theme: "auto", width: "desktop", image: "", readme: "", barHidden: false };
  let images = [];
  let readmes = [];
  let fingerprint = null;
  let ui = null;
  let boot = null;
  let keepScroll = false;
  let scrollY = 0;

  // Remember theme and width between runs (a convenience; works without it).
  try {
    Object.assign(state, pick(JSON.parse(localStorage.getItem(STORE_KEY) || "{}"), REMEMBERED));
  } catch (_) { /* storage can be unavailable */ }

  function pick(source, keys) {
    return Object.fromEntries(keys.filter((key) => key in source).map((key) => [key, source[key]]));
  }

  function save() {
    try { localStorage.setItem(STORE_KEY, JSON.stringify(pick(state, REMEMBERED))); } catch (_) { /* ignore */ }
  }

  function setStatus(text, isError = false) {
    els.status.textContent = text;
    els.status.classList.toggle("error", isError);
  }

  // A row of buttons; the one matching state[key] is highlighted.
  function renderButtons(container, options, key, onPick) {
    container.replaceChildren(...options.map(([value, label]) => {
      const button = document.createElement("button");
      button.type = "button";
      button.textContent = label;
      button.setAttribute("aria-pressed", String(value === state[key]));
      button.addEventListener("click", () => {
        if (state[key] === value) return;
        state[key] = value;
        renderButtons(container, options, key, onPick);
        onPick(value);
      });
      return button;
    }));
  }

  function pageUrl(refresh) {
    const params = new URLSearchParams({ user: state.user });
    if (state.readme) params.set("readme", state.readme);
    if (state.image) params.set("img", state.image);
    if (refresh) params.set("refresh", "1");
    return `/page?${params}`;
  }

  function reload({ refresh = false, preserveScroll = false } = {}) {
    keepScroll = preserveScroll;
    if (preserveScroll) {
      try { scrollY = frame.contentWindow.scrollY; } catch (_) { scrollY = 0; }
    }
    setStatus("Loading…");
    frame.contentWindow.location.replace(pageUrl(refresh));
  }

  // GitHub's own CSS does all the coloring: we only say which theme to use.
  // color-scheme makes the browser show light/dark variants of SVG images too.
  function applyTheme() {
    let root;
    try { root = frame.contentDocument.documentElement; } catch (_) { return; }
    if (state.theme === "auto") {
      root.setAttribute("data-color-mode", "auto");
      root.style.removeProperty("color-scheme");
    } else {
      root.setAttribute("data-color-mode", state.theme);
      root.style.colorScheme = state.theme;
    }
  }

  function applyWidth() {
    frame.dataset.width = state.width;
  }

  // "assets/banner-v1.2.svg" and "http://host/repo/assets/banner-v1.0.svg" share the base "banner".
  function baseName(path) {
    const file = decodeURIComponent(path.split("?")[0].split("/").pop());
    return file.replace(IMAGE_EXT, "").replace(VERSION_SUFFIX, "").toLowerCase();
  }

  // Swap the README image inside the open preview without reloading it (no flicker).
  // Returns false when it can't, so the caller can fall back to a normal reload.
  function swapImageInPlace(path) {
    let doc;
    try { doc = frame.contentDocument; } catch (_) { return false; }
    const imgs = [...doc.querySelectorAll("article.markdown-body img")].filter((img) => img.dataset.previewOriginal || img.src.startsWith(location.origin + "/repo/"));
    if (!imgs.length) return false;
    const original = (img) => img.dataset.previewOriginal || img.src;

    if (path === "") { // back to the README as written
      for (const img of imgs) if (img.dataset.previewOriginal) img.src = img.dataset.previewOriginal;
      return true;
    }
    const target = imgs.find((img) => baseName(original(img)) === baseName(path)) || imgs[0];
    const url = `${location.origin}/repo/${encodeURI(path)}`;
    const probe = new Image();
    probe.onload = () => { // show the new picture only once it is ready
      target.dataset.previewOriginal = original(target);
      target.removeAttribute("srcset");
      target.src = url;
    };
    probe.onerror = () => reload({ preserveScroll: true });
    probe.src = url;
    return true;
  }

  // One button per README file in the repo (README.md, README-v2.md, ...). Hidden when there is just one.
  function renderReadmes() {
    if (!readmes.includes(state.readme)) state.readme = readmes[0] || "";
    els.readmesWrap.hidden = readmes.length < 2;
    renderButtons(els.readmes, readmes.map((name) => [name, name]), "readme", () => {
      state.image = "";
      save();
      fingerprint = null; // the next poll refreshes the image versions for this README without reloading
      reload();
      poll();
    });
  }

  // The little tab on the top bar hides it so the preview gets the full height.
  function applyBar() {
    els.bar.classList.toggle("collapsed", state.barHidden);
    els.toggle.setAttribute("aria-expanded", String(!state.barHidden));
    const label = state.barHidden ? "Show the top bar" : "Hide the top bar";
    els.toggle.title = label;
    els.toggle.setAttribute("aria-label", label);
  }

  function renderVersions() {
    if (!images.includes(state.image)) state.image = "";
    els.versionsWrap.hidden = images.length === 0;
    const options = [["", "README"], ...images.map((path) => [path, path.split("/").pop()])];
    renderButtons(els.versions, options, "image", (path) => {
      if (!swapImageInPlace(path)) reload({ preserveScroll: true });
    });
  }

  frame.addEventListener("load", () => {
    applyTheme();
    if (keepScroll) frame.contentWindow.scrollTo(0, scrollY);
    setStatus(`Showing ${state.user} · auto-reloads when you save`);
  });

  $("#user-form").addEventListener("submit", (event) => {
    event.preventDefault();
    state.user = els.user.value.trim();
    reload();
  });
  $("#refresh").addEventListener("click", () => reload({ refresh: true }));

  async function poll() {
    try {
      const response = await fetch(`/api/state?readme=${encodeURIComponent(state.readme)}`, { cache: "no-store" });
      const data = await response.json();
      // The tool itself changed (its UI files, or the server restarted): reload this page.
      if ((ui !== null && data.ui !== ui) || (boot !== null && data.boot !== boot)) {
        location.reload();
        return;
      }
      ui = data.ui;
      boot = data.boot;
      if (fingerprint === null || data.fingerprint !== fingerprint) {
        readmes = data.readmes;
        renderReadmes();
        images = data.images;
        renderVersions();
        if (fingerprint !== null) reload({ preserveScroll: true });
      }
      fingerprint = data.fingerprint;
    } catch (_) {
      setStatus("Lost connection to the preview server", true);
    }
  }

  els.toggle.addEventListener("click", () => { state.barHidden = !state.barHidden; save(); applyBar(); });
  els.user.value = state.user;
  applyBar();
  renderButtons(els.theme, THEMES, "theme", () => { save(); applyTheme(); });
  renderButtons(els.width, WIDTHS, "width", () => { save(); applyWidth(); });
  applyWidth();
  poll().then(() => reload());
  setInterval(poll, POLL_MS);
})();
