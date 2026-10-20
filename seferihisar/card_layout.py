"""Versioned card policy; standard library only for durable-state validation."""

LEGACY='caption-note-v1'
VERSION='editorial-cream-v1'
SUPPORTED=(LEGACY,VERSION)
CAPTION_NOTE='Detaylar açıklamada.'


def prepare(post):
    if post.get('status','prepared') in ('prepared','blocked_source'):
        post['card_layout']=VERSION


def inline_note(post):
    # Unclaimed direct previews use the new policy. A retained claim needs its
    # explicit policy marker; old claims preserve their exact earlier layout.
    return (post.get('card_layout') in SUPPORTED
            or post.get('status','prepared') in ('prepared','blocked_source'))


def editorial(post):
    # Explicit legacy claims retain their old bytes. New claims retain their
    # selected layout after publication, independent of later defaults.
    return (post.get('card_layout')==VERSION
            or post.get('status','prepared') in ('prepared','blocked_source'))
