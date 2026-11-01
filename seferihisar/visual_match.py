"""Local, bounded image/subject check; no inference API or arbitrary prompts.

CLIP compares a fixed English taxonomy. Similarity is a rejection heuristic,
not a factual verification or calibrated probability. Unsupported subjects
never enter it. Both actual wide crops must pass, not only the square source.
"""
from __future__ import annotations

import hashlib
import io
import os
from functools import lru_cache
from pathlib import Path

from PIL import Image, ImageOps

VERSION = 'subject-full-frame-v3'
MODEL = 'openai/clip-vit-base-patch32'
REVISION = '3d74acf9a28c67741b2f4f2ea7635f0aaf6f0268'
WEIGHT_SHA = 'a63082132ba4f97a80bea76823f544493bffa8082296d62d71581a4feff1576f'
FILES = {'config.json': 4186, 'merges.txt': 524657, 'preprocessor_config.json': 316,
         'pytorch_model.bin': 605247071, 'special_tokens_map.json': 389,
         'tokenizer_config.json': 592, 'vocab.json': 862328}
LABELS = {
    'theatre': 'a photograph of a theatre stage with curtains and stage lights',
    'concert': 'a photograph of musical instruments and a microphone on a concert stage',
    'cinema': 'a photograph of a cinema auditorium facing a large blank movie screen',
    'festival': 'a photograph of festive ribbons and hanging string lights over outdoor tables',
    'culture': 'a photograph of an art workspace with paintbrushes and a canvas',
    'family': 'a photograph of colourful building blocks and craft materials on a table',
    'sport': 'a photograph of a running track and sports equipment',
    'market': 'a photograph of wicker baskets of fresh produce at a market',
    'food': 'a photograph of dishes of food on a dining table',
    'education': 'a photograph of notebooks and pencils on a study desk',
    'yoga': 'a photograph of yoga mats and cork yoga blocks on the floor',
    'tile_art': 'a photograph of ceramic tiles, paintbrushes and bowls of paint on a worktable',
    'workshop': 'a photograph of paper, scissors and craft tools on a worktable',
    # Explicit distractors from observed failures. Never eligible outputs.
    'traffic': 'a photograph of a busy street full of cars and traffic',
    'empty_hall': 'a photograph of rows of empty auditorium seats without a stage or screen',
    'landscape': 'a photograph of a landscape, sky and buildings',
    'meeting': 'a photograph of people in a meeting around a table',
    'flood': 'a photograph of a flooded street covered in water',
    'blank': 'a blank solid colour image without objects',
    'citrus_harvest': 'a photograph of a person harvesting tangerines from a citrus tree in an orchard',
}

from .visual_topics import LABELS as NEWS_LABELS
LABELS.update(NEWS_LABELS)
LABELS.setdefault('roadworks', 'a news photograph of a street or sidewalk being renovated with bare ground and road maintenance equipment')
LABELS['event_calendar'] = 'a photograph of a desk calendar with blank pages and colourful blank admission tickets beside a pen'

# A real article photograph shows people and places, which the empty scenes
# above were never written to describe. Scored apart, so generated images and
# every threshold above stay exactly as they were.
OCCASION_LABELS = {
    'public_event': 'a news photograph of people at a public event, ceremony or festival',
    'community_event': 'a photograph of people at a local community event',
    'people_together': 'a press photograph of people standing together',
    'people_indoors': 'a photograph of people sitting in a room',
}
SCENE_LABELS = {
    'real_scene': 'a news photograph of a real scene',
    'real_place': 'a photograph of a real place or street',
}
NON_PHOTO_LABELS = {
    'graphic': 'a graphic design poster with large printed text and logos',
    'flyer': 'an advertisement flyer with colourful text and icons',
    'screenshot': 'a screenshot of a document or web page with text',
    'logo': 'a logo on a plain background',
    'illustration': 'a digital illustration or computer generated image',
    'blank': LABELS['blank'],
    'empty_hall': LABELS['empty_hall'],
}
PHOTO_LABELS = {**OCCASION_LABELS, **SCENE_LABELS, **NON_PHOTO_LABELS}
# Stories told through people need people in the picture: a street or an empty
# hall on a meeting story is the wrong photograph. Stories about a place or thing
# may show it without anyone. Incident subjects keep their own evidence: a crowd
# beside a road is not a photograph of that road's flood or repair.
SCENE_SUBJECTS = frozenset(('article_photo', 'bus', 'parking', 'landscape', 'land_planning', 'public_park',
                            'citrus_processing', 'animal_care'))
OCCASION_SUBJECTS = SCENE_SUBJECTS | frozenset(('festival', 'public_service', 'concert', 'theatre', 'cinema', 'culture',
                                                'education', 'health_workspace', 'market', 'food', 'meeting'))


class MatchUnavailable(ValueError):
    pass


class MatchRejected(ValueError):
    pass


def directory() -> Path:
    return Path(os.getenv('VISUAL_MODEL_DIR', 'work/visual-model'))


def download():
    """Explicit setup only. Fixed public files; no downloaded Python is run."""
    import requests
    root = directory()
    root.mkdir(parents=True, exist_ok=True)
    session = requests.Session()
    for name, size in FILES.items():
        path = root / name
        if path.is_file() and path.stat().st_size == size:
            if name != 'pytorch_model.bin' or hashlib.sha256(path.read_bytes()).hexdigest() == WEIGHT_SHA:
                continue
        temporary = path.with_suffix('.download')
        count, sha = 0, hashlib.sha256()
        with session.get(f'https://huggingface.co/{MODEL}/resolve/{REVISION}/{name}',
                         timeout=(10, 45), stream=True) as response:
            response.raise_for_status()
            with temporary.open('wb') as out:
                for chunk in response.iter_content(1024 * 1024):
                    count += len(chunk)
                    if count > size:
                        raise ValueError('Visual model file too large')
                    sha.update(chunk)
                    out.write(chunk)
        if count != size or (name == 'pytorch_model.bin' and sha.hexdigest() != WEIGHT_SHA):
            raise ValueError('Visual model integrity failed')
        temporary.replace(path)


@lru_cache(maxsize=1)
def runtime():
    try:
        import torch
        from transformers import CLIPModel, CLIPProcessor
        root = directory()
        if any(not (root / name).is_file() or (root / name).stat().st_size != size for name, size in FILES.items()):
            raise MatchUnavailable()
        if hashlib.sha256((root / 'pytorch_model.bin').read_bytes()).hexdigest() != WEIGHT_SHA:
            raise MatchUnavailable()
        torch.set_num_threads(2)
        processor = CLIPProcessor.from_pretrained(root, local_files_only=True, trust_remote_code=False, use_fast=False)
        model = CLIPModel.from_pretrained(root, local_files_only=True, trust_remote_code=False,
                                          use_safetensors=False, weights_only=True).eval()
        with torch.inference_mode():
            features = model.get_text_features(**processor(text=list(LABELS.values()),
                                                           padding=True, return_tensors='pt'))
            features = features / features.norm(dim=-1, keepdim=True)
        return torch, processor, model, features
    except Exception:
        # No provider/import/file exception text enters public diagnostics.
        raise MatchUnavailable('Visual match unavailable') from None


def scores(images: list[Image.Image]) -> list[dict[str, float]]:
    try:
        torch, processor, model, text = runtime()
        with torch.inference_mode():
            features = model.get_image_features(**processor(images=images, return_tensors='pt'))
            features = features / features.norm(dim=-1, keepdim=True)
            values = (features @ text.T).tolist()
        return [dict(zip(LABELS, row)) for row in values]
    except Exception:
        raise MatchUnavailable('Visual match unavailable') from None


@lru_cache(maxsize=1)
def photo_text():
    torch, processor, model, _ = runtime()
    with torch.inference_mode():
        features = model.get_text_features(**processor(text=list(PHOTO_LABELS.values()),
                                                       padding=True, return_tensors='pt'))
        return features / features.norm(dim=-1, keepdim=True)


def photo_scores(images: list[Image.Image]) -> list[dict[str, float]]:
    try:
        torch, processor, model, _ = runtime()
        text = photo_text()
        with torch.inference_mode():
            features = model.get_image_features(**processor(images=images, return_tensors='pt'))
            features = features / features.norm(dim=-1, keepdim=True)
            values = (features @ text.T).tolist()
        return [dict(zip(PHOTO_LABELS, row)) for row in values]
    except Exception:
        raise MatchUnavailable('Visual match unavailable') from None


def accepted(result: dict[str, float], expected: str) -> bool:
    import math
    if expected not in LABELS or set(result) != set(LABELS) or not all(
            type(value) in (int, float) and math.isfinite(value) for value in result.values()):
        return False
    positive = result[expected]
    # Conservative abstention: explicit subject evidence AND a margin over
    # every alternative. These are cosine thresholds, never confidence %.
    return positive >= 0.24 and positive - max(v for k, v in result.items() if k != expected) >= 0.015


def occasion_accepted(result: dict[str, float], expected: str = '') -> bool:
    import math
    if set(result) != set(PHOTO_LABELS) or not all(
            type(value) in (int, float) and math.isfinite(value) for value in result.values()):
        return False
    labels = {**OCCASION_LABELS, **SCENE_LABELS} if expected in SCENE_SUBJECTS else OCCASION_LABELS
    positive = max(result[label] for label in labels)
    # Calibrated 1 Nov on 42 real article images: every headline banner fell
    # below .19 or inside the margin. Also a rejection heuristic, never a fact check.
    return positive >= 0.19 and positive - max(result[label] for label in NON_PHOTO_LABELS) >= 0.015


def validate_match(data: bytes, expected: str) -> dict:
    if expected not in LABELS or expected in ('empty_hall', 'landscape', 'meeting', 'flood', 'blank', 'citrus_harvest'):
        raise MatchRejected('Unsupported visual subject')
    return _validate_crops(data,expected)


def validate_news_photo(data: bytes, expected: str) -> dict:
    # These remain forbidden generated scenes. Only a separately verified,
    # article-bound source photograph may reach this narrow news taxonomy.
    from .source_photo_data import ARTICLE_PHOTO, SUBJECTS
    if expected == ARTICLE_PHOTO:
        return _validate_occasion(data,expected)
    if expected not in SUBJECTS:
        raise MatchRejected('Unsupported news photograph')
    try:
        return _validate_crops(data,expected,source_photo=True)
    except MatchRejected:
        if expected not in OCCASION_SUBJECTS:
            raise
        return _validate_occasion(data,expected)


def validate_headline_photo(data: bytes, expected: str, title: str) -> dict:
    """Check an editorial graphic's actual photo above a matching text banner.

    This is model input only: the source file and published full frame are
    unchanged. A matching headline never replaces the photo subject check.
    """
    import re
    import shutil
    from .domain import normalized
    from .image_safety import _scan_words
    binary = shutil.which('tesseract')
    if not binary:
        raise MatchRejected('No verified headline region')
    title_words = {w for w in normalized(title).split() if len(w)>2}
    if len(title_words)<3:
        raise MatchRejected('Insufficient headline identity')
    with Image.open(io.BytesIO(data)) as raw:
        image=raw.convert('RGB');width,height=image.size
    for mode in (11,6):
        try:
            words=_scan_words(binary,data,mode)
        except ValueError:
            continue
        hits=[w for w in words if w['confidence']>=65
              and title_words.intersection(normalized(w['text']).split())
              and w['box']['height']>=height*.045]
        seen={v for w in hits for v in normalized(w['text']).split()} & title_words
        if len(seen)/len(title_words)<.6:
            continue
        top=min(w['box']['top'] for w in hits)
        if not height*.35<=top<=height*.75:
            continue
        # A broad, bounded upper photograph must independently pass the same
        # fixed taxonomy, absolute similarity and alternative-class margin.
        region=image.crop((0,0,width,max(1,int(top-height*.02))))
        buffer=io.BytesIO();region.save(buffer,format='JPEG',quality=90)
        if expected == 'traffic':
            import math
            values=scores([ImageOps.pad(region,(224,224),color='#777777')])
            result=values[0] if len(values)==1 else {}
            # Parking and traffic share cars/road geometry. Only for an exact
            # source/title-bound banner may that sibling have a narrow margin;
            # traffic must still be the highest score and beat every unrelated
            # subject by the unchanged margin. Flood/dry-road are never grouped.
            if (set(result)==set(LABELS) and all(type(v) in (int,float) and math.isfinite(v) for v in result.values()) and result['traffic']>=.24
                    and result['traffic']>=result['parking']
                    and result['traffic']-max(v for k,v in result.items() if k not in ('traffic','parking'))>=.015):
                return {'subject':expected,'version':VERSION,'image_sha256':hashlib.sha256(data).hexdigest()}
            raise MatchRejected('Source transport context mismatch')
        return _validate_crops(buffer.getvalue(),expected,source_photo=True)
    raise MatchRejected('No verified headline region')


def validate_event_photo(data: bytes, expected: str) -> dict:
    from .source_photo_data import EVENT_SUBJECTS
    if expected not in EVENT_SUBJECTS:
        raise MatchRejected('Unsupported event photograph')
    return _validate_crops(data,expected,source_photo=True)


def _validate_occasion(data: bytes, expected: str) -> dict:
    """The publisher bound this file to the exact article; it must be a photograph."""
    from .image_safety import IllustrationCheckUnavailable, IllustrationTextRejected, validate_photo_not_text_graphic
    try:
        validate_photo_not_text_graphic(data)
    except IllustrationTextRejected:
        raise MatchRejected('Headline graphic') from None
    except IllustrationCheckUnavailable:
        raise
    except ValueError:
        raise MatchRejected('Unsupported photograph') from None
    try:
        with Image.open(io.BytesIO(data)) as image:
            image.load()
            crops = [ImageOps.pad(image.convert('RGB'),size,Image.Resampling.LANCZOS,color='#06244a')
                     for size in ((1080, 436), (1080, 506), (1080, 586))]
        results = photo_scores(crops)
        if len(results) != 3 or not all(occasion_accepted(result, expected) for result in results):
            raise MatchRejected('Visual subject mismatch')
        return {'subject': expected, 'version': VERSION,
                'image_sha256': hashlib.sha256(data).hexdigest()}
    except (MatchRejected, MatchUnavailable):
        raise
    except Exception:
        raise MatchUnavailable('Visual match unavailable') from None


def _validate_crops(data: bytes, expected: str, *, source_photo=False) -> dict:
    try:
        with Image.open(io.BytesIO(data)) as image:
            image.load()
            center = (0.5, 1.0) if expected == 'yoga' else (0.5, 0.5)
            crops = [ImageOps.pad(image.convert('RGB'),size,Image.Resampling.LANCZOS,color='#06244a') if source_photo
                     else ImageOps.fit(image.convert('RGB'), size, Image.Resampling.LANCZOS, centering=center)
                     for size in ((1080, 436), (1080, 506), (1080, 586))]
        results = scores(crops)
        if len(results) != 3 or not all(accepted(result, expected) for result in results):
            raise MatchRejected('Visual subject mismatch')
        return {'subject': expected, 'version': VERSION,
                'image_sha256': hashlib.sha256(data).hexdigest()}
    except (MatchRejected, MatchUnavailable):
        raise
    except Exception:
        raise MatchUnavailable('Visual match unavailable') from None


if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--download', action='store_true', required=True)
    parser.parse_args()
    download()
    runtime()
    print('Pinned local visual model ready')
