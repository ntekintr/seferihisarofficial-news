# SeferihisarOfficial fixed card identity

Feed cards are 1080×1350 JPEG; story cards are 1080×1920 JPEG. Both use the original approved logo asset and the same navy, mandarin-orange and turquoise header/category/footer strips. Turkish headlines use dotted capital İ correctly. Attribution has a reserved footer line; overly long titles/excerpts visibly end with an ellipsis, with full source information retained in the caption.

The illustration is a separate per-item input. `render_post(post, public_dir, illustrations={0: Path(...)})` assigns an illustration to exactly one slide and reuses it for that slide's feed/story formats. Source/detail slides do not inherit the image automatically. Each supplied illustration is labelled `Temsili çizim`. The renderer makes no network requests and includes no shared harbour or category-wide stock scene.

Without a matching illustration, the renderer produces a branded abstract/text card. This is a fallback, not the user's requested final AI-illustration automation.

## Remaining cloud generation work

The user chose a different representative illustration for each news item, with constant branding. The renderer interface and original logo are ready. An authenticated image-generation provider, spending authorization and durable per-item caching still need to be connected before claiming that GitHub Actions automatically creates those illustrations. No paid API requests or new credentials are created by this change. Existing publication gates and scheduled research remain unchanged.

Provider setup must preserve one generated image across feed/story renders, cache by factual revision, bound requests/cost, and avoid repeated charging after uncertain runs. Secret values must stay out of repository files, public state and logs. Generated scenes must not imply documentary evidence; sensitive-news publication still requires the existing review rules.
