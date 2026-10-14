"""Project reviewed coverage entries onto recent, real reader health."""
from __future__ import annotations

from datetime import timedelta

from .domain import parse_date
from .security import contains_secret, public_url


def public_catalog(entries, sources, health, at):
    readers = {s['id']: s for s in sources}
    checks = {h['source_id']: h for h in health}
    result = []
    for entry in entries:
        if not public_url(entry.get('url', '')) or contains_secret(entry):
            continue
        row = {key: entry.get(key) for key in ('id', 'name', 'url', 'group', 'status', 'note')}
        reader_id = entry.get('reader_id', entry['id'])
        reader, check = readers.get(reader_id), checks.get(reader_id)
        # An undated event page or an unconnected site is a separate coverage
        # limitation. A working alternative must not erase that limitation.
        if reader and entry['status'] != 'date_missing':
            stamp = parse_date(check.get('checked_at')) if check else None
            if not reader.get('enabled'):
                row.update(status='reader_pending', note='Bu kaynağın okuyucusu etkin değil.')
            elif not stamp or not at - timedelta(hours=1) <= stamp <= at + timedelta(minutes=5):
                row.update(status='check_pending', note='Güncel canlı kontrol bekleniyor.')
            elif check['status'] in ('ok', 'empty'):
                row.update(status='connected', note=(f"Son kontrolde {check['parsed']} kayıt okundu, "
                            f"{check['accepted']} kayıt doğrulandı. "
                            'Güncel haber ve etkinlik uygunluğu ayrıca denetlenir.'))
            elif check['status'] == 'partial':
                row.update(status='partial', note=(f"Son kontrolde kısmen okundu; {check['error_count']} hata. "
                            'Ayrıntılar sistem durumu bölümündedir. ' + (entry.get('note') or '')))
            else:
                row.update(status='access_failed', note='Son kontrolde okunamadı. Ayrıntılar sistem durumu bölümündedir. '
                           + (entry.get('note') or ''))
        if row['status'] != 'connected':
            for sid in entry.get('fallback_reader_ids', []):
                fallback, check = readers.get(sid), checks.get(sid)
                stamp = parse_date(check.get('checked_at')) if check else None
                if (fallback and fallback.get('enabled') and stamp
                        and at - timedelta(hours=1) <= stamp <= at + timedelta(minutes=5)
                        and check['status'] in ('ok', 'empty')):
                    row['note'] = (row.get('note') or '') + f" Tamamlayıcı kaynak {fallback['name']} son kontrolde okunabildi."
        result.append(row)
    return result
