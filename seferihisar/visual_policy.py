"""A relevant picture is preferred; a source or category alone is not proof."""
VERSION = 'relevant-visual-first-v2'


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
    return {'version':VERSION, 'preference':['verified_source_image','reviewed_topic_scene','wait_for_valid_image'],
            'pending_covers':counts, 'unrelated_filler_allowed':False,
            'content_image_required':True, 'information_card_publishable':False,
            'scope':'Source image first, supported generic scene second, otherwise wait without a new social claim'}


def retired_scene(post, items):
    """A prepared cover still bound to a free-form article scene, now disabled.

    Only an unclassified news story (no reviewed subject) could receive such a
    scene, so its illustration binding proves it. The next research render
    drops the binding; until then the card must not go out with that picture.
    """
    from .illustrations import ARTICLE_SCENES_ENABLED
    if ARTICLE_SCENES_ENABLED or post.get('status') in ('published', 'publishing', 'uncertain'):
        return False
    item = (items or {}).get(post.get('item_id'))
    if not item or not post.get('illustration_keys', {}).get('0'):
        return False
    from .visual_subject import subject
    from .visual_topics import unclassified_news
    return subject(item) is None and unclassified_news(item)


def image_reason(post, items=None):
    if post.get('status') in ('published', 'publishing', 'uncertain'):
        return None
    if items is not None and retired_scene(post, items):
        return 'article_scene_retired'
    proof = post.get('visual_review', {})
    bound = post.get('source_photo_keys', {}).get('0') or post.get('illustration_keys', {}).get('0')
    if not bound or not proof.get('images', {}).get('0'):
        return 'awaiting_content_visual'
    return None
