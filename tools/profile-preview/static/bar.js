// Controls for the profile previewer. The preview itself is an iframe of our own
// server, so we can set GitHub's theme attribute on it, resize it and edit it freely.
(() => {
  const POLL_MS = 1000;
  const STORE_KEY = "profile-preview";
  const REMEMBERED = ["theme", "width", "readme", "barHidden", "dock", "barSize", "slot", "swaps"];
  const THEMES = [["auto", "Auto", "contrast"], ["light", "Light", "sun"], ["dark", "Dark", "moon"]];
  const WIDTHS = [["desktop", "Desktop", "monitor"], ["tablet", "Tablet", "tablet"], ["phone", "Phone", "phone"]];
  const DOCKS = [["top", "Top", "panelTop"], ["left", "Left", "panelLeft"]];
  const SIZE_LIMITS = { top: [44, 0.7], left: [200, 0.6] }; // [min px, max share of the window]
  const DEFAULT_SIZE = { top: null, left: 300 };              // null = fit the content

  // Line icons (Lucide, ISC licence), drawn in the button's text colour.
  const ICONS = {
    search: '<circle cx="11" cy="11" r="8"/><path d="m21 21-4.3-4.3"/>',
    refresh: '<path d="M3 12a9 9 0 0 1 9-9 9.75 9.75 0 0 1 6.74 2.74L21 8"/><path d="M21 3v5h-5"/><path d="M21 12a9 9 0 0 1-9 9 9.75 9.75 0 0 1-6.74-2.74L3 16"/><path d="M8 16H3v5"/>',
    contrast: '<circle cx="12" cy="12" r="10"/><path d="M12 18a6 6 0 0 0 0-12v12z"/>',
    sun: '<circle cx="12" cy="12" r="4"/><path d="M12 2v2"/><path d="M12 20v2"/><path d="m4.93 4.93 1.41 1.41"/><path d="m17.66 17.66 1.41 1.41"/><path d="M2 12h2"/><path d="M20 12h2"/><path d="m6.34 17.66-1.41 1.41"/><path d="m19.07 4.93-1.41 1.41"/>',
    moon: '<path d="M12 3a6 6 0 0 0 9 9 9 9 0 1 1-9-9Z"/>',
    monitor: '<rect width="20" height="14" x="2" y="3" rx="2"/><path d="M8 21h8"/><path d="M12 17v4"/>',
    tablet: '<rect width="16" height="20" x="4" y="2" rx="2"/><path d="M12 18h.01"/>',
    phone: '<rect width="14" height="20" x="5" y="2" rx="2"/><path d="M12 18h.01"/>',
    panelTop: '<rect width="18" height="18" x="3" y="3" rx="2"/><path d="M3 9h18"/>',
    panelLeft: '<rect width="18" height="18" x="3" y="3" rx="2"/><path d="M9 3v18"/>',
  };

  function icon(name) {
    const template = document.createElement("template");
    template.innerHTML = `<svg class="icon" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true">${ICONS[name]}</svg>`;
    return template.content.firstChild;
  }

  const $ = (selector) => document.querySelector(selector);
  const frame = $("#frame");
  const els = {
    user: $("#user"), theme: $("#theme"), width: $("#width"), dock: $("#dock"),
    readme: $("#readme"), readmesWrap: $("#readmes-wrap"),
    slot: $("#slot"), options: $("#options"), slotsWrap: $("#slots-wrap"), resetSwaps: $("#reset-swaps"),
    bar: $("#bar"), toggle: $("#bar-toggle"), resize: $("#bar-resize"), status: $("#status"),
  };

  const state = {
    user: document.documentElement.dataset.defaultUser || "",
    theme: "auto",
    width: "desktop",
    readme: "",
    barHidden: false,
    dock: "top",
    barSize: { ...DEFAULT_SIZE },
    slot: "",   // which README image the Images row is showing alternatives for
    swaps: {},  // path as written in the README -> image to show instead
  };
  let slots = [];
  let readmes = [];
  let fingerprint = null;
  let ui = null;
  let boot = null;
  let keepScroll = false;
  let scrollY = 0;

  // Remember choices between runs (a convenience; works without it).
  try {
    Object.assign(state, pick(JSON.parse(localStorage.getItem(STORE_KEY) || "{}"), REMEMBERED));
  } catch (_) { /* storage can be unavailable */ }
  keepIfValid("theme", THEMES, "auto");
  keepIfValid("width", WIDTHS, "desktop");
  keepIfValid("dock", DOCKS, "top");
  if (typeof state.barSize !== "object" || state.barSize === null) state.barSize = { ...DEFAULT_SIZE };
  if (typeof state.swaps !== "object" || state.swaps === null) state.swaps = {};

  // A remembered value from an older version of the tool may no longer exist.
  function keepIfValid(key, options, fallback) {
    if (!options.some(([value]) => value === state[key])) state[key] = fallback;
  }

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

  function fileName(path) {
    return path.split("/").pop();
  }

  // A row of buttons. `isPressed(value)` says which one is highlighted.
  function renderButtons(container, options, isPressed, onPick, decorate) {
    container.replaceChildren(...options.map(([value, label, iconName]) => {
      const button = document.createElement("button");
      button.type = "button";
      if (iconName) button.append(icon(iconName));
      if (decorate) decorate(button, value);
      button.append(label);
      button.setAttribute("aria-pressed", String(isPressed(value)));
      button.addEventListener("click", () => { if (!isPressed(value)) onPick(value); });
      return button;
    }));
  }

  // Buttons bound to one key of `state`.
  function renderChoice(container, options, key, onPick) {
    renderButtons(container, options, (value) => state[key] === value, (value) => {
      state[key] = value;
      renderChoice(container, options, key, onPick);
      onPick(value);
    });
  }

  function pageUrl(refresh) {
    const params = new URLSearchParams({ user: state.user });
    if (state.readme) params.set("readme", state.readme);
    for (const [original, shown] of Object.entries(state.swaps)) params.append("swap", `${original}|${shown}`);
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


  // Fill a <select> with items sorted into <optgroup>s, in the order the groups first appear.
  function fillGroupedSelect(select, items, groupOf, optionFor) {
    const groups = new Map();
    for (const item of items) {
      const name = groupOf(item);
      if (!groups.has(name)) groups.set(name, []);
      groups.get(name).push(item);
    }
    select.replaceChildren(...[...groups].map(([name, members]) => {
      const group = document.createElement("optgroup");
      group.label = name;
      group.append(...members.map(optionFor));
      return group;
    }));
  }


  // ---- README picker -----------------------------------------------------

  // Repo-root READMEs first, then the saved versions. Hidden when there is just one.
  function renderReadmes() {
    if (!readmes.includes(state.readme)) state.readme = readmes[0] || "";
    els.readmesWrap.hidden = readmes.length < 2;
    fillGroupedSelect(
      els.readme,
      readmes,
      (name) => (name.includes("/") ? name.slice(0, name.lastIndexOf("/") + 1) : "Repo root"),
      (name) => new Option(fileName(name), name, false, name === state.readme),
    );
  }

  els.readme.addEventListener("change", () => {
    state.readme = els.readme.value;
    state.swaps = {}; // the new README has its own images
    save();
    fingerprint = null; // the next poll refreshes the image slots for this README
    reload();
    poll();
  });


  // ---- Images: try another banner or icon in place of the README's ---------

  function currentSlot() {
    return slots.find((slot) => slot.id === state.slot);
  }

  // Forget swaps for images this README no longer has, or files that are gone.
  function pruneSwaps() {
    const valid = Object.fromEntries(Object.entries(state.swaps).filter(([original, shown]) => {
      const slot = slots.find((s) => s.id === original);
      return slot && slot.options.includes(shown) && shown !== original;
    }));
    const changed = Object.keys(valid).length !== Object.keys(state.swaps).length;
    state.swaps = valid;
    return changed;
  }

  function renderSlots() {
    els.slotsWrap.hidden = slots.length === 0;
    if (!currentSlot()) state.slot = slots[0]?.id || "";

    fillGroupedSelect(els.slot, slots, (slot) => slot.group, (slot) => {
      const changed = slot.id in state.swaps ? " ●" : "";
      return new Option(slot.label + changed, slot.id, false, slot.id === state.slot);
    });
    els.resetSwaps.hidden = Object.keys(state.swaps).length === 0;
    renderOptions();
  }

  function renderOptions() {
    const slot = currentSlot();
    if (!slot) { els.options.replaceChildren(); return; }
    const shown = state.swaps[slot.id] || slot.id;
    const isIcon = slot.group === "Icons";
    const options = slot.options.map((path) => [path, isIcon ? fileName(path).replace(/\.[^.]+$/, "") : fileName(path)]);
    renderButtons(els.options, options, (path) => path === shown, (path) => choose(slot, path), (button, path) => {
      button.title = path + (path === slot.id ? " (as in the README)" : "");
      if (isIcon) {
        const preview = document.createElement("img");
        preview.src = `/repo/${encodeURI(path)}`;
        preview.alt = "";
        button.append(preview);
      }
    });
  }

  function choose(slot, path) {
    if (path === slot.id) delete state.swaps[slot.id];
    else state.swaps[slot.id] = path;
    save();
    renderSlots();
    if (!swapInPlace(slot.id, path)) reload({ preserveScroll: true });
  }

  els.slot.addEventListener("change", () => { state.slot = els.slot.value; save(); renderOptions(); });

  els.resetSwaps.addEventListener("click", () => {
    const originals = Object.keys(state.swaps);
    state.swaps = {};
    save();
    renderSlots();
    if (!originals.every((original) => swapInPlace(original, original))) reload({ preserveScroll: true });
  });

  // Show another image inside the open preview without reloading it (no flicker).
  // The server marks each README image with the path as written; we change every
  // <img> and <picture> <source> with that mark. Returns false when it can't.
  // The new picture is shown once it has loaded; if you pick again before that,
  // only the latest pick is shown.
  const latestPick = {};
  function swapInPlace(original, path) {
    let doc;
    try { doc = frame.contentDocument; } catch (_) { return false; }
    const mark = CSS.escape(original);
    const imgs = [...doc.querySelectorAll(`[data-preview-src="${mark}"]`)];
    const sources = [...doc.querySelectorAll(`[data-preview-srcset="${mark}"]`)];
    if (!imgs.length && !sources.length) return false;

    const url = `${location.origin}/repo/${encodeURI(path)}`;
    latestPick[original] = url;
    const probe = new Image();
    probe.onload = () => {
      if (latestPick[original] !== url) return;
      for (const img of imgs) img.src = url;
      for (const source of sources) source.srcset = url;
    };
    probe.onerror = () => reload({ preserveScroll: true });
    probe.src = url;
    return true;
  }


  // ---- Panel: dock top or left, drag its edge to resize, hide with the tab --

  function clampSize(size) {
    const [min, maxShare] = SIZE_LIMITS[state.dock];
    const max = (state.dock === "top" ? innerHeight : innerWidth) * maxShare;
    return Math.round(Math.min(Math.max(size, min), max));
  }

  function applyBar() {
    document.body.dataset.dock = state.dock;
    els.bar.classList.toggle("collapsed", state.barHidden);
    els.bar.style.width = "";
    els.bar.style.height = "";
    const size = state.barSize[state.dock];
    if (size != null) els.bar.style[state.dock === "top" ? "height" : "width"] = `${clampSize(size)}px`;

    const label = `${state.barHidden ? "Show" : "Hide"} the panel`;
    els.toggle.title = label;
    els.toggle.setAttribute("aria-label", label);
    els.toggle.setAttribute("aria-expanded", String(!state.barHidden));
    els.resize.setAttribute("aria-orientation", state.dock === "top" ? "horizontal" : "vertical");
  }

  els.resize.addEventListener("pointerdown", (event) => {
    event.preventDefault();
    els.resize.setPointerCapture(event.pointerId);
    document.body.classList.add("resizing");
    const box = els.bar.getBoundingClientRect();
    const start = state.dock === "top" ? event.clientY : event.clientX;
    const startSize = state.dock === "top" ? box.height : box.width;

    const drag = new AbortController(); // removes all three listeners when the drag ends
    els.resize.addEventListener("pointermove", (e) => {
      const delta = (state.dock === "top" ? e.clientY : e.clientX) - start;
      state.barSize = { ...state.barSize, [state.dock]: clampSize(startSize + delta) };
      applyBar();
    }, { signal: drag.signal });
    const end = () => {
      drag.abort();
      document.body.classList.remove("resizing");
      save();
    };
    els.resize.addEventListener("pointerup", end, { signal: drag.signal });
    els.resize.addEventListener("pointercancel", end, { signal: drag.signal });
  });

  // Double-click the edge: back to the default size.
  els.resize.addEventListener("dblclick", () => {
    state.barSize = { ...state.barSize, [state.dock]: DEFAULT_SIZE[state.dock] };
    save();
    applyBar();
  });

  els.toggle.addEventListener("click", () => { state.barHidden = !state.barHidden; save(); applyBar(); });
  addEventListener("resize", applyBar); // keep the panel within its limits when the window shrinks


  // ---- Loading and live reload -------------------------------------------

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
        slots = data.slots;
        if (pruneSwaps()) save();
        renderSlots();
        if (fingerprint !== null) reload({ preserveScroll: true });
      }
      fingerprint = data.fingerprint;
    } catch (_) {
      setStatus("Lost connection to the preview server", true);
    }
  }

  els.user.value = state.user;
  applyBar();
  renderChoice(els.theme, THEMES, "theme", () => { save(); applyTheme(); });
  renderChoice(els.width, WIDTHS, "width", () => { save(); applyWidth(); });
  renderChoice(els.dock, DOCKS, "dock", () => { save(); applyBar(); });
  for (const button of document.querySelectorAll("button[data-icon]")) button.prepend(icon(button.dataset.icon));
  applyWidth();
  poll().then(() => reload());
  setInterval(poll, POLL_MS);
})();
