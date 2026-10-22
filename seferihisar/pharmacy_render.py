"""Deterministic readable type over a once-generated 3D brand background."""
from datetime import date
import hashlib
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageOps

from .brand import logo_path
from .render import font, wrap
from .text_quality import ensure_glyphs
from .pharmacy_data import asset_id, background_path, background_hash, profile, validate_bulletin

SCALE=2
TOP=760
BOTTOM=1660


def layouts(value):
    """No dropped address/phone/note: move the full entry to the next page."""
    validate_bulletin(value)
    draw=ImageDraw.Draw(Image.new('RGB',(1,1)))
    result=[]; page=[]; used=0
    for entry in value['entries']:
        name=entry['name']
        names=wrap(draw,name,font(40*SCALE,True),820*SCALE)
        address=wrap(draw,entry['address'],font(30*SCALE),820*SCALE)
        notes=wrap(draw,entry['note'],font(26*SCALE),820*SCALE) if entry['note'] else []
        for text,size,bold in [(name,40,True),(entry['address'],30,False),(entry['note'],26,False),(entry['region'],23,True)]:
            ensure_glyphs(text,font(size*SCALE,bold))
        height=42+len(names)*49+len(address)*38+(52 if entry['phone'] else 0)+len(notes)*32+32
        if height > BOTTOM-TOP:
            raise ValueError('Pharmacy details exceed readable story budget')
        if page and (len(page)>=3 or used+height+18>BOTTOM-TOP):
            result.append(page);page=[];used=0
        page.append((entry,names,address,notes,height));used+=height+18
    if page:result.append(page)
    if len(result)>4:
        raise ValueError('Too many pharmacy story pages')
    return result


def render(value,public_dir,*,preview=False):
    validate_bulletin(value)
    if value['background_sha256']!=background_hash():
        raise ValueError('Versioned pharmacy background changed')
    p=profile();pages=layouts(value);assets=[];hashes={}
    accent='#35d6de' if p['city']=='seferihisar' else '#a42b66'
    ink='#102d43' if p['city']=='seferihisar' else '#20324a'
    heading='white' if p['city']=='seferihisar' else ink
    for index,entries in enumerate(pages,1):
        with Image.open(background_path()) as bg:
            canvas=ImageOps.fit(bg.convert('RGB'),(1080*SCALE,1920*SCALE),method=Image.Resampling.LANCZOS).convert('RGBA')
        draw=ImageDraw.Draw(canvas)
        def text(x,y,value,size=30,color=None,bold=False):
            typeface=font(size*SCALE,bold)
            ensure_glyphs(value,typeface)
            draw.text((x*SCALE,y*SCALE),value,font=typeface,fill=color or heading,anchor='lt')
        with Image.open(logo_path()) as src:
            size=140 if p['city']=='seferihisar' else 230
            logo=ImageOps.fit(src.convert('RGB'),(size*SCALE,size*SCALE),method=Image.Resampling.LANCZOS)
        mask=Image.new('L',logo.size,0);md=ImageDraw.Draw(mask)
        md.rounded_rectangle((0,0,logo.width-1,logo.height-1),radius=32*SCALE,fill=255)
        canvas.paste(logo,(72*SCALE,170*SCALE),mask)
        if p['city']=='seferihisar':
            text(230,208,'SEFERİHİSAR',25,bold=True)
            text(230,247,'OFFICIAL',22,accent)
        text(72,445,'Nöbetçi',66,bold=True)
        text(72,519,'Eczaneler',66,bold=True)
        text(74,609,p['label'],31,accent,bold=True)
        day=date.fromisoformat(value['date'])
        weekday=('Pazartesi','Salı','Çarşamba','Perşembe','Cuma','Cumartesi','Pazar')[day.weekday()]
        label=day.strftime('%d.%m.%Y')+' · '+weekday
        text(74,676,label,31,bold=True)
        if len(pages)>1:text(927,676,f'{index}/{len(pages)}',27,accent)
        y=TOP
        for entry,names,address,notes,height in entries:
            bounds=(66*SCALE,y*SCALE,1014*SCALE,(y+height)*SCALE)
            shadow=Image.new('RGBA',canvas.size,(0,0,0,0));sd=ImageDraw.Draw(shadow)
            sd.rounded_rectangle((bounds[0],bounds[1]+12*SCALE,bounds[2],bounds[3]+12*SCALE),radius=26*SCALE,fill=(0,0,0,85))
            canvas=Image.alpha_composite(canvas,shadow.filter(ImageFilter.GaussianBlur(10*SCALE)))
            overlay=Image.new('RGBA',canvas.size,(0,0,0,0));od=ImageDraw.Draw(overlay)
            od.rounded_rectangle(bounds,radius=26*SCALE,fill=(250,252,255,245),outline=(255,255,255,220),width=2*SCALE)
            od.rounded_rectangle((79*SCALE,(y+25)*SCALE,85*SCALE,(y+height-25)*SCALE),radius=3*SCALE,fill=accent)
            canvas=Image.alpha_composite(canvas,overlay);draw=ImageDraw.Draw(canvas)
            pos=y+22;text(105,pos,entry['region'],23,'#387480' if p['city']=='seferihisar' else '#92325e',True);pos+=33
            for line in names:text(105,pos,line,40,ink,True);pos+=49
            for line in address:text(105,pos,line,30,'#3c4c5d');pos+=38
            if entry['phone']:
                raw=entry['phone'];display=f'{raw[:4]} {raw[4:7]} {raw[7:9]} {raw[9:]}'
                text(105,pos+7,display,35,ink,True);pos+=52
            for line in notes:text(105,pos+4,line,26,'#75420e');pos+=32
            y+=height+18
        text(73,1731,'Gitmeden önce telefonla teyit edin.',27,'#e4edf3' if p['city']=='seferihisar' else '#47596a')
        text(73,1780,'@'+p['username'],27,accent,True)
        if preview:text(73,1832,'ÖRNEK TASARIM · PAYLAŞILMADI',22,'#f4d5a9' if p['city']=='seferihisar' else '#6e5b30')
        relative=f'media/{asset_id(value)}/story-{index}.jpg';target=Path(public_dir)/relative
        target.parent.mkdir(parents=True,exist_ok=True)
        canvas.convert('RGB').resize((1080,1920),Image.Resampling.LANCZOS).save(target,'JPEG',quality=95,subsampling=0)
        assets.append(relative);hashes[relative]=hashlib.sha256(target.read_bytes()).hexdigest()
    return {'assets':assets,'sha256':hashes}
