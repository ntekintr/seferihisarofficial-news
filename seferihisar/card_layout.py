"""Versioned card policy; standard library only for durable-state validation."""

VERSION='caption-note-v1'
CAPTION_NOTE='Detaylar açıklamada.'


def prepare(post):
    if post.get('status','prepared') in ('prepared','blocked_source'):
        post['card_layout']=VERSION


def inline_note(post):
    # Unclaimed direct previews use the new policy. A retained claim needs its
    # explicit policy marker; old claims preserve their exact earlier layout.
    return (post.get('card_layout')==VERSION
            or post.get('status','prepared') in ('prepared','blocked_source'))
