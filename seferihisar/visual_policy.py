"""A relevant picture is preferred; a source or category alone is not proof."""
VERSION = 'relevant-visual-first-v1'


def summary(store):
    from .visual_gate import valid_review
    counts = {'source_photo':0, 'topic_visual':0, 'information_card':0}
    for post in store.posts():
        if post['status']!='prepared' or post.get('publish_format'):
            continue
        images = post.get('visual_review',{}).get('images',{}) if valid_review(post) else {}
        # Count the visible cover, not a photograph on a later calendar slide.
        kind = ('source_photo' if '0' in images and post.get('source_photo_keys',{}).get('0') else
                'topic_visual' if '0' in images and post.get('illustration_keys',{}).get('0') else
                'information_card')
        counts[kind] += 1
    return {'version':VERSION, 'preference':['verified_source_image','reviewed_event_scene','information_card'],
            'pending_covers':counts, 'unrelated_filler_allowed':False,
            'scope':'Supported source subjects and same-origin structured event images; no universal image guarantee'}
