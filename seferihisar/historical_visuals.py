"""Bounded recovery of pre-protection visual cache loss from this repo's archive.

Never resets state, changes claims, replaces a new claim's image, or publishes.
Only listed byte-identical historical rows with unchanged owning claims qualify.
"""
import base64
import hashlib
import json
import sqlite3
import subprocess
from pathlib import Path

MANIFEST = {'state_commit': '8251e562a6419bc614a29619afbbf7116bc26116', 'snapshot_sha256': 'cc98e6653b8a6e9ef539e722603d867bbc07d792059fc229ded2397c88c861b5', 'rows': [{'key': '49ccf80a31139b0ec68839c2', 'original': '7b4a03eb00cf72a9f4ffa1f77ea1dc248af946c84205074d59f9014f5749063b', 'observed': None, 'owners': {'bedf0adcf894cd73bb953300': 'c3df786a9046fbde1881f27cf36d387ec118241f8076c85e2707e8e7c765194c', '596d2a369d905caebe8d4dc9': 'a5419fce2d1996ef8f64e7ae40f6545483e60bb91a70bacdcf3a1bf04591706c'}}, {'key': '570d290a6834837028e4c65d', 'original': 'ca739b5f58a16ca0911fa49f1ebf8589703aa9e9d256fcc245087e34941b0484', 'observed': None, 'owners': {'6758c340ef75ee2ac6bb660c': '17252c664d4d641ee2fbd7e06f02b0f9488a6a1e7c8d943a843806bd40c619a3', '8b5c1504bf617a4cd31bf9ad': 'b9555fe1a45eb8961ad64a19316e4109281b164886cd2d8bea39c2b0006a6d4d'}}, {'key': '5716fda498d69c7b1e240a03', 'original': '3418d569869bb95d16cb97ad5360beb72e4e66bda0c1b517f0885b35181b747c', 'observed': None, 'owners': {'bedf0adcf894cd73bb953300': 'c3df786a9046fbde1881f27cf36d387ec118241f8076c85e2707e8e7c765194c', '596d2a369d905caebe8d4dc9': 'a5419fce2d1996ef8f64e7ae40f6545483e60bb91a70bacdcf3a1bf04591706c'}}, {'key': '6f1e30774dff5a9bcc509af1', 'original': 'ae11ab8a9b2cb5a955009d372d93812ddc501b59d0bfe7e6aaba6a337db26ada', 'observed': '477836d0b9dc368df594405c5ef0eaadf570cc9bae86415421b028aa1cb9ca15', 'owners': {'bedf0adcf894cd73bb953300': 'c3df786a9046fbde1881f27cf36d387ec118241f8076c85e2707e8e7c765194c', '596d2a369d905caebe8d4dc9': 'a5419fce2d1996ef8f64e7ae40f6545483e60bb91a70bacdcf3a1bf04591706c', 'b050ea10f18efa39c7602b64': '5970362b65f04854b9732b265bb72b4e7dc3bf1f00d1312d99409162f061e0d0', '19ebf0e1a45240ae31e90732': '36414988f81ca1ee688d5ab5c1116c3f93f29f065967e3e1035c4cdd120f8665'}}, {'key': '78348daf5656b43043f3ce0c', 'original': '5b14e25c7dfe6591781b769a5c14101dd9eea4f9cd584ff5474e4c81a295da71', 'observed': None, 'owners': {'bedf0adcf894cd73bb953300': 'c3df786a9046fbde1881f27cf36d387ec118241f8076c85e2707e8e7c765194c', '596d2a369d905caebe8d4dc9': 'a5419fce2d1996ef8f64e7ae40f6545483e60bb91a70bacdcf3a1bf04591706c', '16269d4e5df54c1753039ad6': 'e67c7d6234576767c77e49a96d5096bc541792e7d371f24da79b49cddc5da7f3', '01a3e384a935248faa8a847e': 'b46b456eea95764f27b06159903dcdc5a17810565fb0bfcd8ffc478960686d65'}}, {'key': '7e8fbc08a75aa8d23c54f48e', 'original': 'c5a1e0b0c40901defe4bf260fb18eba5cf59d048275ac623747e6752bab5ff6d', 'observed': None, 'owners': {'d55bb96e7096aa0651b25717': 'b6f4e294e746c614cecffdfbd07c78c8d9967238f7fa871b621b5dc6dc78bd18', '8e5c7d4fd526dab5da87733c': 'bd0b1b6adfd3615b5a4333105b73f19df2c0b5ab938915e1c31421543b12fd9a'}}, {'key': 'b3292fc037037f6e6e558869', 'original': '9491ae801ba1d690f0ef8c79d8e83ed680defde36636145d739e026c0e53034f', 'observed': None, 'owners': {'eb9835717a10018e872d3b41': '4cc53f810a644f585c61d384eecde91dda76096b10b093fb9d924c162ac02c9e', '70dd3cae2cf7b767fa1cbd86': 'b951d5785edc02a16a759f65369137f9685627834bb4f14bf87b1361919dda7e'}}, {'key': 'cc23bcf2267e8b82757c4f48', 'original': '82f361fab198cef8fe7ef192c70eaf2a6c494e06a7988e028b95ccf94fa70f75', 'observed': None, 'owners': {'28e5c374611a36578e9b0b40': '94970957e970cc0013ef3609287c7113dce80f892509c03a58f8c2b1ecfca662', 'c5dad736c9997932805155ae': 'f5f0c58aaae66df2fef6cb11b86a26cefdaff32787aa9b1f026a916a1996201b'}}, {'key': 'd26a0339313aac1b3428ac21', 'original': '1aed52f82cf9897ea00840a9376f154e5ec0f565259dc9fbc2a139045ddd9a41', 'observed': None, 'owners': {'bedf0adcf894cd73bb953300': 'c3df786a9046fbde1881f27cf36d387ec118241f8076c85e2707e8e7c765194c', '596d2a369d905caebe8d4dc9': 'a5419fce2d1996ef8f64e7ae40f6545483e60bb91a70bacdcf3a1bf04591706c'}}, {'key': 'f5234beac45ae93baf324f98', 'original': '07e7669460a9c41c6ce4b15e202320ffcb2fce38d6bce92fb3c6117c55df2645', 'observed': None, 'owners': {'bedf0adcf894cd73bb953300': 'c3df786a9046fbde1881f27cf36d387ec118241f8076c85e2707e8e7c765194c', '596d2a369d905caebe8d4dc9': 'a5419fce2d1996ef8f64e7ae40f6545483e60bb91a70bacdcf3a1bf04591706c'}}]}


def fingerprint(row):
    return hashlib.sha256(json.dumps([base64.b64encode(v).decode() if isinstance(v, bytes) else v
        for v in row], ensure_ascii=False, separators=(',', ':')).encode()).hexdigest()


def eligible(db, spec):
    owners = {}
    for row in db.execute("SELECT * FROM posts WHERE status IN ('published','publishing','uncertain')"):
        columns = [r[1] for r in db.execute('PRAGMA table_info(posts)')]
        post = dict(zip(columns, row))
        try:
            keys = json.loads(post['payload']).get('illustration_keys', {})
            if not isinstance(keys, dict): return False
            if spec['key'] in keys.values(): owners[post['id']] = fingerprint(row)
        except (TypeError, ValueError): return False
    if not owners or any(spec['owners'].get(k) != value for k, value in owners.items()):
        return False
    current = db.execute('SELECT * FROM illustrations WHERE id=?', (spec['key'],)).fetchone()
    observed = fingerprint(current) if current else None
    return observed != spec['original'] and observed == spec['observed']


def repair(db, archive_bytes, manifest=MANIFEST):
    if hashlib.sha256(archive_bytes).hexdigest() != manifest['snapshot_sha256']:
        raise ValueError('Historical snapshot checksum mismatch')
    archive = sqlite3.connect(':memory:')
    try:
        archive.deserialize(archive_bytes)
        if archive.execute('PRAGMA integrity_check').fetchone()[0] != 'ok':
            raise ValueError('Historical snapshot integrity mismatch')
        replacements = []
        for spec in manifest['rows']:
            if not eligible(db, spec): continue
            row = archive.execute('SELECT * FROM illustrations WHERE id=?', (spec['key'],)).fetchone()
            if not row or fingerprint(row) != spec['original']:
                raise ValueError('Historical row checksum mismatch')
            replacements.append(row)
        for row in replacements:
            db.execute('INSERT OR REPLACE INTO illustrations VALUES(?,?,?,?,?,?,?)', row)
        return len(replacements)
    finally:
        archive.close()


def recover(path: Path, git, manifest=MANIFEST):
    db = sqlite3.connect(path)
    try:
        if not any(eligible(db, spec) for spec in manifest['rows']): return 0
        revision = manifest['state_commit']
        try:
            snapshot = git('show', revision + ':platform.sqlite')
        except subprocess.CalledProcessError:
            git('fetch', '--no-tags', '--depth=1', 'origin', revision)
            snapshot = git('show', revision + ':platform.sqlite')
        with db:
            db.execute('BEGIN IMMEDIATE')
            return repair(db, snapshot, manifest)
    finally:
        db.close()
