"""Versioned card policy; standard library only for durable-state validation."""

LEGACY='caption-note-v1'
FITTED='editorial-cream-v1'
ONE_SCALE='editorial-cream-v2'
VERSION='editorial-cream-v3'
SUPPORTED=(LEGACY,FITTED,ONE_SCALE,VERSION)
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
    return (post.get('card_layout') in (FITTED,ONE_SCALE,VERSION)
            or post.get('status','prepared') in ('prepared','blocked_source'))


def filled_hero(post):
    # Short text once left an empty band; the picture now takes that space.
    # Claimed earlier layouts keep the bytes they were published with.
    return (post.get('card_layout')==VERSION
            or (not post.get('card_layout') and post.get('status','prepared') in ('prepared','blocked_source')))


def fixed_scale(post):
    # A claimed v1 card keeps the sizes it was published with.
    return post.get('card_layout')!=FITTED
