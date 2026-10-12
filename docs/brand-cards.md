# SeferihisarOfficial fixed card identity

Feed cards are 1080×1350 JPEG; story cards are 1080×1920 JPEG. Both use the original approved logo asset and the same navy, mandarin-orange and turquoise header/category/footer strips. Turkish headlines use dotted capital İ correctly. Attribution has a reserved footer line; overly long titles/excerpts visibly end with an ellipsis, with full source information retained in the caption.

The illustration is a separate per-item input. `render_post(post, public_dir, illustrations={0: Path(...)})` assigns an illustration to exactly one slide and reuses it for that slide's feed/story formats. Source/detail slides do not inherit the image automatically. Each supplied illustration is labelled `Temsili çizim`. The renderer makes no network requests and includes no shared harbour or category-wide stock scene.

Without a matching illustration, the renderer produces a branded abstract/text card. This is a fallback, not the user's requested final AI-illustration automation.

## Free cloud illustrations

The research workflow uses Cloudflare Workers AI `@cf/black-forest-labs/flux-1-schnell` with four steps. The user-approved account is on Workers Free; its shared allowance is 10,000 Neurons per UTC day, and quota exhaustion fails instead of automatically upgrading. This repository does not create a paid plan or enable Instagram publication.

The bot reads `CLOUDFLARE_API_TOKEN` from GitHub Actions Secrets and `CLOUDFLARE_ACCOUNT_ID` from Actions Variables. They are passed only to the content preparation step. `ILLUSTRATIONS_ENABLED=true` enables generation; demos ignore it and make no image-provider calls. Missing credentials or a rejected request produces the branded text-card fallback.

Each verified item/revision has its own illustration, shared across feed, story, announcement, reminders and matching calendar slides. Calendar covers and source/detail appendices remain text cards. A changed factual revision receives a new cache key. Provider imagery is symbolic, visibly labelled `Temsili çizim`, and never substitutes for source verification.

The cache travels inside the existing public-safe SQLite database on `automation-state`, so a fresh runner reuses previous images. Only re-encoded baseline JPEG pixels are retained; prompts, provider responses, EXIF, comments and credentials are not persisted. The state validator checks image framing and metadata without requiring Pillow in the isolated writer job. Cache bounds: 80 images and 12 MiB; individual images are at most 768×768 and 512 KiB. Revoked/unverified items' cached images are removed from active state.

Generation is limited to two attempts per run and twenty per UTC day, claimed in SQLite before the request. Handled errors/timeouts are retained through the normal state writer and wait until the next UTC day, with a maximum of two attempts per item/revision. An abrupt runner termination before that writer can lose new claims or generated images; Cloudflare's Free-plan quota still prevents paid overage. A provider error stops further requests in that run. Public `data.json` exposes only generation/reuse/failure/deferred counts for troubleshooting. Source/date verification and all publication gates remain in force.

The manually dispatched `Test free cloud illustration (no publication)` workflow checks one generated illustration in a fresh GitHub runner and uploads only labelled feed/story example JPEGs as a two-day artifact. It does not restore or modify production state, deploy Pages, access Instagram credentials or publish a social post. Its sample is explicitly a design test, not a real event.

Official references: https://developers.cloudflare.com/workers-ai/platform/pricing/ and https://developers.cloudflare.com/workers-ai/models/flux-1-schnell/.
