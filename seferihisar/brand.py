"""Versioned logo identity, including immutable pre-rollout publications."""
from pathlib import Path

VERSION = 'snail-s-v1'
LEGACY = 'stone-s-v1'
PUBLIC_ASSET = 'logo-snail-s-v1.png'
LOGOS = {VERSION: 'logo.png', LEGACY: 'logo-legacy.png'}


def logo_path(version=VERSION):
    if not isinstance(version, str) or version not in LOGOS:
        raise ValueError('Unknown brand version')
    return Path(__file__).with_name('assets') / LOGOS[version]


def prepare(post):
    if post.get('status', 'prepared') in ('prepared', 'blocked_source'):
        post['brand_version'] = VERSION


def version_for(post):
    # Claims without a marker predate this rollout; they must retain old bytes.
    return post.get('brand_version', VERSION if post.get('status', 'prepared')
                    in ('prepared', 'blocked_source') else LEGACY)
