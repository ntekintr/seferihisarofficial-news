"""Conservative OCR check for source posters; unreadable dates never become facts."""
import re
from datetime import date

from .domain import normalized,parse_date
from .image_safety import IllustrationCheckUnavailable,_scan_words


def check_words(scans,item,*,poster=False):
    from .collect import MONTHS
    start,end=parse_date(item['start']),parse_date(item['end'])
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
        if dates-{start.date(),end.date()}:raise ValueError('Source image date mismatch')
        times={(int(h),int(m)) for h,m in re.findall(r'(?<![\d.])(\d{1,2})[:.](\d{2})(?![.\d])',raw)}
        if times and (not item.get('time_known') or times-{(start.hour,start.minute),(end.hour,end.minute)}):
            raise ValueError('Source image time mismatch')
        # A text-heavy visual or portrait needs explicit matching title/date;
        # it cannot pass just because CLIP recognizes a generic concert poster.
        if poster or years or dates or times or len(text.split())>=3:
            title={w for w in normalized(item['title']).split() if len(w)>2}-{'ile','bir','örnek'}
            if (not title or len(title & set(text.split()))/len(title)<.6 or not dates
                    or item.get('time_known') and (start.hour,start.minute) not in times):
                raise ValueError('Source poster facts unreadable')


def validate(data,item,*,poster=False):
    import shutil
    from .image_safety import ocr_available
    binary=shutil.which('tesseract')
    if not binary or not ocr_available():
        raise IllustrationCheckUnavailable('Event image text check unavailable')
    scans=[_scan_words(binary,data,mode) for mode in (11,6)]
    check_words(scans,item,poster=poster)
