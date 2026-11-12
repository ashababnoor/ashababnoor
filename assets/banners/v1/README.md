# Banner design guide

The design system behind the profile banners: variants, typography, spacing, margins, alignment and colour. A visual version with previews, measurement overlays and colour swatches is in [`banner-design-guide.html`](banner-design-guide.html); open it in a browser.

All dimensions are in CSS pixels. Positions and gaps are measured from the visible outline of the letters (the **ink**), not from the font's line box, as rendered by Chrome on macOS.

## Variants

| Variant | File | Size | Shown when |
|---|---|---|---|
| Desktop | `banner-desktop-v1.0.svg` | 846 × 139 | screens wider than 1100px; also the fallback image |
| Slim | `banner-desktop-slim-v1.0.svg` | 846 × 102 | not currently used; a compact alternative to desktop |
| Tablet | `banner-tablet-v1.0.svg` | 600 × 168 | screens 601–1100px wide |
| Mobile | `banner-mobile-v1.0.svg` | 397 × 165 | screens up to 600px wide |

The profile README chooses a variant with a `<picture>` element and displays it at full width. Each SVG contains both a light and a dark palette and follows the viewer's system setting (`prefers-color-scheme`).

## Content

```
~/shabab $ _                              ← prompt (monospace; accent path, grey $, blinking cursor)
Ahmed Shabab Noor                         ← name
Software & Data Engineer                  ← role
Backend systems · Data pipelines · AI/ML  ← tagline (monospace)
```

On the slim variant, the tagline moves up to the role's baseline and is set flush right.

## Typography

### Typefaces

| Use | Font stack |
|---|---|
| Name, role | `-apple-system, BlinkMacSystemFont, 'Segoe UI', 'Inter', 'Helvetica Neue', Arial, sans-serif` |
| Prompt, tagline | `'Fira Code', 'SF Mono', Menlo, Consolas, 'Liberation Mono', monospace` |

No fonts are embedded. The banners use the viewer's system fonts, so rendering varies slightly between operating systems.

### Type scale

| | Prompt | Name | Role | Tagline | Name ÷ role | Role ÷ tagline |
|---|---|---|---|---|---|---|
| Desktop, slim | 13 | 28 | 16 | 13 | 1.75× | 1.23× |
| Tablet | 15 | 34 | 18 | 15 | 1.89× | 1.20× |
| Mobile | 14 | 32 | 18 | 14 | 1.78× | 1.29× |

| Line | Weight | Tracking (letter-spacing) |
|---|---|---|
| Prompt | 400, with a 0.35px stroke in light mode | 1 |
| Name | 700 | −0.3 at 28px; −1 at 32 and 34px |
| Role | 500 | 0.2 |
| Tagline | 400 | 0 |

### Principles

- **A matched monospace pair.** The prompt and the tagline are always the same size.
- **Name to role: 1.75–1.9×.** A clear lead for the name without dominating the frame.
- **Role to tagline: 1.2–1.3×.** The tagline is supporting detail, so it's set a step smaller than the role to draw less attention.
- **Tighter tracking on the name.** Large bold type looks loose at default spacing, so the name is tightened slightly: −0.3 at 28px, −1 at 32–34px.
- **Stroke compensation in light mode.** Dark text on a light background looks thinner than light text on a dark one (the irradiation effect). So in light mode, the prompt gets a 0.35px stroke in its own colour, and the `$` one in its grey. A heavier font weight wouldn't help, because Menlo, the macOS fallback when Fira Code and SF Mono aren't installed, has only regular and bold.

## Vertical spacing

The four lines form three groups by proximity: the prompt, the name and role, and the tagline. The name and role are separated by a small **inner gap**. The prompt and the tagline each sit one larger **group gap** away, equal above and below. The difference between the two gaps is what makes the grouping read.

```
top margin
~/shabab $ _
        group gap
Ahmed Shabab Noor
        inner gap
Software & Data Engineer
        group gap   (equal to the one above)
Backend systems · Data pipelines · AI/ML
bottom margin  (equal to the top)
```

| Gap | Desktop | Slim | Tablet | Mobile |
|---|---|---|---|---|
| Prompt → name (group) | 13.3 | 14.3 | 21.0 | 21.8 |
| Name → role (inner) | 9.0 | 9.0 | 12.3 | 12.0 |
| Role → tagline (group) | 13.5 | same line | 21.0 | 21.8 |
| Group ÷ inner | 1.49× | 1.58× | 1.71× | 1.81× |

Gaps are measured from the bottom of one line's ink to the top of the next, and rounded to 0.1px. The group gap is 1.5–1.8 times the inner gap.

## Margins

The text is treated as a single block placed in the frame. The space around it forms the margins.

| | Desktop | Slim | Tablet | Mobile |
|---|---|---|---|---|
| Frame | 846 × 139 | 846 × 102 | 600 × 168 | 397 × 165 |
| Text block height | 97.3 | 71.8 | 126.0 | 124.0 |
| Top / bottom | 21.0 / 20.8 | 15.3 / 15.0 | 21.0 / 21.0 | 20.5 / 20.5 |
| Top as share of height | **15%** | **15%** | **12.5%** | **12.5%** |
| Left | 41.8 | 30.3 | 31.5 | 30.8 |
| Left ÷ top | **2×** | **2×** | **1.5×** | **1.5×** |
| Right | open | 30.3 | open | 30.8 |

### Principles

- **Hierarchy first, then equal space above and below.** The type sizes and gaps were set first, to get the hierarchy right. The frame was then sized to give the text equal space above and below, each a fixed share of the height: 15% on desktop and slim, 12.5% on tablet and mobile. On desktop the text fills the remaining 70% of the height: 97.3 ÷ 0.70 ≈ 139px.
- **Margin proportions:**
  - **Desktop and slim: top margin 15% of the height, left margin 2 × top.** They're shown at actual size on wide screens, so they get more room above, below and to the left.
  - **Tablet and mobile: top margin 12.5% of the height, left margin 1.5 × top.** The tablet banner is displayed scaled up (about 1–1.6×), so its margins are already generous on screen. On mobile, a wider left margin would push the tagline into the right edge.
- **Horizontal placement:**
  - **Desktop and tablet: left-aligned, right side open.** Keeping the text together on the left reads more easily than spreading it across the frame. The open space also holds the background glow.
  - **Slim and mobile: centred.** The side margins are equal, so the text as a whole is centred horizontally. On slim, the flush-right tagline ends one left margin from the right edge. The mobile frame is exactly the text block plus the left margin on each side (397px).

## Optical alignment

Every line starts on the same visible left edge. Each glyph carries a left side bearing, the built-in space before its outline, which varies by letter, weight and size. The bold "A" of the name has the most. So each line's `x` is adjusted by a fraction of a pixel until the visible letters line up.

| | Prompt `x → ink` | Name | Role | Tagline |
|---|---|---|---|---|
| Desktop | 41.87 → 41.75 | 41.62 → 41.75 | 41.12 → 41.75 | 41.12 → 42.00 |
| Slim | 30.38 → 30.25 | 30.13 → 30.25 | 29.63 → 30.25 | flush right, ends at 815.75 |
| Tablet | 31.50 → 31.50 | 31.25 → 31.50 | 30.75 → 31.50 | 30.50 → 31.50 |
| Mobile | 30.75 → 30.75 | 30.50 → 30.75 | 30.00 → 30.75 | 29.75 → 30.75 |

Each cell shows the line's `x` position → where its ink starts. Ink was measured on a 0.25px grid; differences under half a pixel aren't visible.

## Colour

Two palettes, switched by `prefers-color-scheme` inside each SVG. Contrast ratios are WCAG 2 ratios against the plain background.

| Role | Used for | CSS class | Light | Contrast | Dark | Contrast |
|---|---|---|---|---|---|---|
| Background | frame | `.bg` | `#F6F8FB` | | `#121212` | |
| Primary | name; slim tagline | `.name` `.tagw` | `#0B1220` | 17.6:1 | `#E0E0E0` | 14.2:1 |
| Secondary | role, tagline, `$` | `.role` `.tag` `.tagr` | `#4B5568` | 7.1:1 | `#B8B8B8` | 9.4:1 |
| Accent | prompt path and cursor | `.path` | `#15803D` | 4.7:1 | `#4ADE80` | 10.8:1 |

- **Three text colours.** Primary, secondary and accent, with nothing in between.
- **Colour sets the hierarchy; size and typeface refine it.** The primary colour marks the name, and the secondary colour marks the lines that support it. Within the secondary lines, size and typeface add a further step: the role is larger and set in the sans-serif, so it leads the smaller, monospace tagline.
- **Contrast is checked over the glow, not only on the plain background.** All text meets WCAG 2 AA (4.5:1) in both themes, including where it crosses the glow. On tablet and mobile the tagline runs into the glow, and the quietest grey that keeps 4.5:1 there is almost identical to the secondary colour, so the tagline uses it. The worst case, at the brightest point of the glow on mobile, is 4.9:1 in light and 4.6:1 in dark.
- **Slim's tagline uses the primary colour.** It sits fully on the glow, where the secondary colour drops to 4.2:1. The primary colour keeps 10.5:1 in light and 6.5:1 in dark at the brightest point.

### Background glow

Three ellipses on the right of the frame, blurred into one soft field of colour.

| Glow | Colour | Position | Opacity, light | Opacity, dark |
|---|---|---|---|---|
| Teal | `#00D4AA` | top | 55% | 45% |
| Indigo | `#6366F1` | bottom right | 40% | 50% |
| Sky | `#38BDF8` | bottom centre | 45% | 35% |

- **Blur:** a Gaussian blur that scales with the frame's height, so every variant has the same softness.
- **Tagline halo (tablet and mobile):** a faint, blurred copy of the tagline in the background colour sits behind it to separate it from the glow.

## Motion and accessibility

- The cursor blinks every 1.1s, and stops when the viewer has reduced motion turned on (`prefers-reduced-motion`).
- Each SVG has a `<title>` with the full text, and the README image has alt text.
