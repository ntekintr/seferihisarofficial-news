"""Conservative OCR check for source posters; unreadable dates never become facts."""
import re
from datetime import date

from .domain import normalized,parse_date
from .image_safety import IllustrationCheckUnavailable,_scan_words


def check_words(scans,item,*,poster=False):
    from .collect import MONTHS
    start,end=parse_date(item['start']),parse_date(item['end'])
    matched_title = False
    requires_title = poster
    for words in scans:
        all_text=' '.join(w['text'] for w in words if w['confidence']>=0)
        years={int(y) for y in re.findall(r'\b(?:19|20)\d{2}\b',all_text)}
        if years-{start.year,end.year}:raise ValueError('Source image year mismatch')
        text=normalized(' '.join(w['text'] for w in words if w['confidence']>=50))
        raw=' '.join(w['text'] for w in words if w['confidence']>=50)
        dates=set()
        for day,month,year in re.findall(r'\b(\d{1,2})[./](\d{1,2})[./](20\d{2})\b',raw):
            dates.add(date(int(year),int(month),int(day)))
        months={normalized(k):v for k,v in MONTHS.items()}
        for day,month,year in re.findall(r'\b(\d{1,2})\s+('+'|'.join(months)+r')\s+(20\d{2})\b',text):
            dates.add(date(int(year),months[month],int(day)))
        for day,month in re.findall(r'\b(\d{1,2})\s+('+'|'.join(months)+r')(?![a-zçğıöşü]|\s+20\d{2})',text):
            if (int(day),months[month]) not in ((start.day,start.month),(end.day,end.month)):
                raise ValueError('Source image date mismatch')
        if dates-{start.date(),end.date()}:raise ValueError('Source image date mismatch')
        times={(int(h),int(m)) for h,m in re.findall(r'(?<![\d.])(\d{1,2})[:.](\d{2})(?![.\d])',raw)}
        if times and (not item.get('time_known') or times-{(start.hour,start.minute),(end.hour,end.minute)}):
            raise ValueError('Source image time mismatch')
        # Promotional artwork can be shared across several sessions and omit
        # the date. The exact source session supplies date/venue facts. Any
        # date/year/time actually printed above must still agree with it.
        if poster or years or dates or times or len(text.split()) >= 3:
            requires_title = True
            title={w for w in normalized(item['title']).split() if len(w)>2}-{'ile','bir','örnek'}
            if title and len(title & set(text.split()))/len(title)>=.6:
                matched_title = True
            elif len(text.split()) >= 3:
                raise ValueError('Source poster title mismatch')
    if requires_title and not matched_title:
        raise ValueError('Source poster title unreadable')
    return matched_title



def validate(data,item,*,poster=False):
    import shutil
    from .image_safety import ocr_available
    binary=shutil.which('tesseract')
    if not binary or not ocr_available():
        raise IllustrationCheckUnavailable('Event image text check unavailable')
    scans=[_scan_words(binary,data,mode) for mode in (11,6)]
    return check_words(scans,item,poster=poster)
