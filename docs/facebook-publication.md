# Same content stream, optional Facebook destination

The crawler, editorial selection, captions and branded feed/story assets stay in
the existing research workflow. Facebook is a second publication destination in
`publish.yml`, not a second news bot. The Instagram account's Facebook Login
authentication does not itself implement a Facebook Page publication request.

## Current setup and activation

Facebook publication defaults to **disabled**. No permission, token or repository
flag is created by this change. Before activation, authorize the app for the
managed SeferihisarOfficial Page only, adding `pages_manage_posts` to the existing
`pages_show_list`, `pages_read_engagement`, `instagram_basic` and
`instagram_content_publish` permissions. Do not request messaging, ads, insights,
other pages or personal-post permissions.

In the existing `instagram-production` environment, store the Page credential as
`FACEBOOK_PAGE_ACCESS_TOKEN`. Set `FACEBOOK_PAGE_ID` to the Page's Graph API ID
(which can differ from the public profile ID). Validate the Page token's `me`
identity and linked `instagram_business_account` against `INSTAGRAM_USER_ID`.
Check permissions and review the prepared feed/story before setting
`FACEBOOK_TESTS_COMPLETED=true` and `FACEBOOK_PUBLISH_ENABLED=true`.

## Delivery and failure behavior

Only a feed already confirmed published on Instagram within the last hour of the
same Turkish day can be mirrored. Revalidate the current source, item revision,
news age and event end before sending. This never republishes Instagram content.
The existing caption and all feed slides (up to ten) become one Facebook photo
post. The matching first story card is eligible only after its Instagram story
and Facebook feed are confirmed published. Maximum two feeds and two stories
per Page per Turkish day, including uncertain attempts.

Media must already be deployed as public HTTPS JPEGs. All photos are uploaded
unpublished; feed uses `/{page-id}/feed` with `attached_media`, story uses
`/{page-id}/photo_stories` with `photo_id`. `facebook_deliveries` stores only safe
identifiers, timestamps and status. A claim is checkpointed remotely before any
Meta write. Crashes/timeouts leave `publishing` or `uncertain`; automatic runs do
not resend them. Manual inspection of Meta is required to resolve uncertainty.
Existing Instagram statuses remain independent.

Before enabling this destination, confirm the same API content is not also being
mirrored by another integration. Do not enable two Facebook delivery mechanisms.
Historical Instagram posts older than one hour are not replayed at activation.

## Official Meta references

- [Instagram content publishing](https://developers.facebook.com/documentation/instagram-platform/content-publishing)
- [Page Photos, permissions and multi-photo feed](https://developers.facebook.com/docs/graph-api/reference/page/photos/)
- [Page Photo Stories](https://developers.facebook.com/docs/graph-api/reference/page/photo_stories/)
- [Facebook Page posts](https://developers.facebook.com/documentation/pages-api/posts)
