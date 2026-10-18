# Optional source photos from Instagram

The existing caption reader and public manifest remain unchanged. A separate,
optional step uses the same existing read credential and Business Discovery GET
endpoint, adding `media_type` and `media_url`. It does not request new permission,
generate a token, scrape login pages, read pagination, or publish anything. If
those fields are unavailable, caption research continues with information cards.

At most two recent, verified caption items per run are selected, restricted to
the existing meeting, flood and traffic news subjects. Accounts whose caption
read failed receive no extra query. Each selected account is read at most once
in this optional step. The returned caption, permalink and timestamp must still
produce the exact item from the caption manifest. Only `IMAGE` is eligible;
carousels, reels, videos, archival/illustrative labels and warnings stay cards.

The API-returned CDN address is used once in memory, never persisted or logged.
Only approved Instagram/Facebook CDN host patterns over public HTTPS/DNS are
allowed. The image session carries no Graph authorization or cookies; redirects
and retries are disabled. MIME, 2 MB input, 4 megapixel, landscape and 640x300
minimum bounds apply. Metadata is stripped, pixels are reduced to at most 768px,
and the strict metadata-free JPEG validator runs before artifact export.

The one-day artifact adds `photos.json` and at most two cleaned JPEGs beside
`public.json`. The index contains the public source permalink, Graph media ID,
source title/time, check time, subject and SHA-256. It contains no signed CDN URL
or API response. Research has no Meta credential. It independently verifies the
caption-run timestamp, configured source, item equality, one-hour freshness,
fixed hash-derived filename, metadata schema, byte hash and strict JPEG shape.
An invalid or missing photo artifact does not invalidate captions.

Research then runs the existing pinned local CLIP subject check over all three
actual hero layouts. CLIP only rejects subject mismatches; it does not establish
people's identity, photo authenticity or exact event location. The source link
is supplied by the same Graph media row, not inferred by CLIP. Reused pixels or
media IDs cannot represent another item. Approved photos enter the same bounded
`source_photos` cache and immutable source/revision binding as web source photos.
Publication rechecks that binding, age, deployed manifest and JPEG hashes before
any claim or Meta mutation. It never fetches source media. Frozen records and
legacy photo keys keep their exact previous validation and hash behavior.

Photos retain their full frame; the existing logo, stripes and caption-only
credit rules apply. Unsupported, unavailable or rejected images use information
cards. Production `source_photos.instagram` diagnostics distinguish artifact
availability and optional API/download outcomes from approved photo assignments.
An `available` artifact is not a model approval or a social delivery. A successful
workflow is not proof of a new photo publication. Daily publication limits and
the separate weather story remain unchanged.

Primary API field reference: Meta's official generated
[IGMedia SDK](https://github.com/facebook/facebook-python-business-sdk/blob/main/facebook_business/adobjects/igmedia.py).
Field existence does not establish Business Discovery permission for a given
account; the normal cloud run determines availability using the current credential.
