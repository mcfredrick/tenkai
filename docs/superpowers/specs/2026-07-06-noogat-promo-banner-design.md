# Noogat Promo Banner — Design Spec

## Summary

Add a thin promotional banner below the site header on all pages of the Tenkai website, advertising the noogat.app note-taking app.

## Placement

Inserted in `baseof.html` between `{{ partial "header.html" . }}` and `<main class="content">`, as a new partial `partials/promo-banner.html`.

## Content

- **Logo**: `<img>` sourced from `https://noogat.app/assets/logo-transparent.png`, 20px tall
- **Headline**: "Voice Notes that Organize Themselves." — linked to `https://noogat.app`
- **Dismiss button**: `×` on the right side

## Styling

All values use CSS variables to respect both dark and light themes:

- `background: var(--surface)`
- `border-bottom: 1px solid var(--border)`
- Text: `var(--muted)` default, `var(--accent)` on hover (with `var(--glow)`)
- Flexbox row, space-between, vertically centered
- Padding matches existing site rhythm (e.g. `0.5rem 1.5rem`)

## Dismiss Behavior

- Clicking `×` hides the banner and sets `sessionStorage.setItem('promo-dismissed', '1')`
- On page load, if key is present, banner is hidden immediately (no flash)
- Reappears in a new browser session

## Files Changed

| File | Change |
|------|--------|
| `themes/tenkai/layouts/partials/promo-banner.html` | New partial — banner markup + inline dismiss script |
| `themes/tenkai/layouts/_default/baseof.html` | Insert `{{ partial "promo-banner.html" . }}` between header and main |
| `themes/tenkai/static/style.css` | Add `.promo-banner` styles |
