"""Minimal forecast typography with a small original 3D snail scene near the bottom."""
from __future__ import annotations

import re
from datetime import date, datetime
from pathlib import Path

from PIL import Image, ImageDraw, ImageOps

from .render import ASSETS, NAVY, ORANGE, TURQUOISE, font, readable_date_line, wrap
from .weather_data import asset_id, validate_forecast


def scene_for(condition):
    value = condition.casefold().replace('yağışsız','')
    if 'gök gürült' in value or 'dolu' in value:
        return 'storm'
    if re.search(r'\bkar(?:lı|la| yağ| yağış| sağanak)|\bsulu kar',value):
        return 'snow'
    if any(w in value for w in ('sağanak','yağmur','yağış')):
        return 'rain'
    if any(w in value for w in ('fırtına','rüzgarlı','rüzgârlı','kuvvetli rüzgar','kuvvetli rüzgâr')):
        return 'wind'
    if any(w in value for w in ('sis','pus')):
        return 'fog'
    if 'parçalı' in value or 'az bulut' in value:
        return 'partly-cloudy'
    if 'bulut' in value or 'kapalı' in value:
        return 'cloudy'
    return 'sunny' if 'güneş' in value or 'açık' in value else 'cloudy'


def display_condition(forecast):
    description = forecast['condition']
    if datetime.fromisoformat(forecast['period_start']).date() < date.fromisoformat(forecast['date']):
        description = re.sub(r'\byarın\b','bugün',description,flags=re.I)
    return description


def render_weather(forecast, public_dir: Path):
    validate_forecast(forecast)
    scale = 2
    image = Image.new('RGB', (1080*scale, 1920*scale), '#fbf6eb')
    draw = ImageDraw.Draw(image)
    def text(xy, value, size, color=NAVY, bold=False, anchor='mm'):
        draw.text(tuple(int(v*scale) for v in xy), value, font=font(size*scale, bold), fill=color, anchor=anchor)
    def line(points, color, width=3):
        draw.line([(int(x*scale),int(y*scale)) for x,y in points], fill=color, width=width*scale)

    with Image.open(ASSETS/'logo.png') as original:
        logo = ImageOps.fit(original.convert('RGB'), (96*scale,96*scale), method=Image.Resampling.LANCZOS)
    mask = Image.new('L',logo.size,0)
    ImageDraw.Draw(mask).ellipse((0,0,logo.width-1,logo.height-1),fill=255)
    image.paste(logo,(900*scale,230*scale),mask)
    text((84,258),'SEFERİHİSAR',29,bold=True,anchor='lm')
    text((84,300),'OFFICIAL',23,TURQUOISE,anchor='lm')
    line([(84,367),(996,367)],ORANGE,2)
    text((540,480),'Günaydın, Seferihisar!',55,bold=True)
    day = date.fromisoformat(forecast['date'])
    weekday = ('Pazartesi','Salı','Çarşamba','Perşembe','Cuma','Cumartesi','Pazar')[day.weekday()]
    text((540,552),readable_date_line(day.strftime('%d.%m.%Y'))+' · '+weekday,29,'#60717d')

    available = [(key, label) for key, label in (('high','En yüksek'),('low','En düşük'))
                 if forecast[key] is not None]
    for index, (key, label) in enumerate(available):
        x = 540 if len(available) == 1 else (370,717)[index]
        text((x,758),f"{forecast[key]}°",132 if index == 0 else 94,
             NAVY if index == 0 else '#71838c',bold=index == 0)
        text((x,873),label,27,'#60717d')
    description = display_condition(forecast)
    for size in (40,36,32,28,24):
        lines = wrap(draw,description,font(size*scale,True),870*scale)
        if len(lines) <= 3: break
    for i,value in enumerate(lines):
        text((540,1000+i*(size+12)),value,size,bold=True)
    end = datetime.fromisoformat(forecast['period_end'])
    end_label = end.strftime('%H:%M') if end.date() == day else readable_date_line(end.strftime('%d.%m.%Y'))+' '+end.strftime('%H:%M')
    text((540,1210),'Tahmin geçerliliği: '+end_label,24,'#71838c')

    # Small original landscape confined to the lower fifth of the story.
    scene = scene_for(forecast['condition'])
    with Image.open(ASSETS/f'weather-snail-{scene}.jpg') as original:
        landscape = ImageOps.fit(original.convert('RGB'),(1080*scale,400*scale),
                                 method=Image.Resampling.LANCZOS,centering=(0.5,1.0))
    image.paste(landscape,(0,1325*scale))
    fade = Image.new('L',(1080*scale,80*scale),0)
    fade_draw = ImageDraw.Draw(fade)
    for y in range(80*scale):
        fade_draw.line((0,y,1080*scale,y),fill=round(255*(1-y/(80*scale-1))))
    image.paste('#fbf6eb',(0,1325*scale,1080*scale,1405*scale),fade)
    line([(84,1775),(996,1775)],TURQUOISE,3)
    text((540,1820),'@seferihisarofficial',25,bold=True)
    image = image.resize((1080,1920),Image.Resampling.LANCZOS)
    relative = f'media/{asset_id(forecast)}/story-1.jpg'
    target = public_dir/relative
    target.parent.mkdir(parents=True,exist_ok=True)
    image.save(target,'JPEG',quality=95,subsampling=0)
    return relative
