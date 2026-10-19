# Brand asset

logo.png is the snail/S logo approved by the user on 19 October 2026, created with the built-in image generation tool. It combines the ivory stone S, mandarin-orange spiral shell, friendly three-dimensional snail and turquoise wave. The renderer composites this exact source file into new feed, story and weather headers; individual illustrations never redraw the logo.

logo-legacy.png retains the earlier S/mandarin logo. Claims made before this rollout have no brand_version marker and continue to render with that exact original asset. New posts and weather forecasts carry brand_version: snail-s-v1, binding the logo change to new media editions and preserving it after publication. The web panel and favicon use the versioned public copy logo-snail-s-v1.png. See docs/brand-cards.md for the rollout boundary.

There is no shared landscape/news backdrop. Per-item images are explicitly assigned and checked before the renderer adds branding. If no suitable image is available, the renderer uses a branded information card. Source attribution stays in the caption. Operational generation settings and quotas are documented separately in docs/brand-cards.md; this asset note does not enable any service or publication.
