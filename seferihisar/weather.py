"""MGM district forecast and one independent Instagram story per Turkish morning."""
from __future__ import annotations

import json
import re
from datetime import datetime, timedelta
from pathlib import Path

import requests

from .domain import TZ, now
from .weather_data import SITE, SOURCE, asset_id, fresh, validate_forecast


class ForecastError(ValueError):
    """Controlled diagnostics, without retaining source HTML or provider errors."""
    def __init__(self, code):
        self.code = code
        super().__init__(code)


def parse_forecast(html, at):
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html,'html.parser')
    values = {}
    for label,key in (('Başlangıç','period_start'),('Bitiş','period_end')):
        matches = soup.find_all(string=lambda t: t and t.strip() == label)
        stamps = []
        for match in matches:
            row = match.find_parent('tr')
            cells = row.find_all(['td','th'],recursive=False) if row else []
            if len(cells) >= 2:
                raw = cells[1].get_text(' ',strip=True)
                if m := re.fullmatch(r':?\s*(\d{2}\.\d{2}\.\d{4}-\d{2}:\d{2})',raw):
                    stamps.append(datetime.strptime(m[1],'%d.%m.%Y-%H:%M').replace(tzinfo=TZ))
        if len(stamps) != 1:
            raise ForecastError('forecast_period_missing')
        values[key] = stamps[0].isoformat()
    rows = []
    for row in soup.select('tr'):
        cells = row.find_all(['th','td'],recursive=False)
        if len(cells) == 4 and cells[0].get_text(' ',strip=True) == 'Seferihisar':
            rows.append([c.get_text(' ',strip=True) for c in cells])
    if len(rows) != 1:
        raise ForecastError('forecast_district_missing')
    _,condition,low,high = rows[0]
    # MGM's daytime bulletin leaves the overnight minimum cell empty. Retain
    # that absence explicitly; never borrow yesterday's or another district's.
    temperatures = []
    for raw in (low, high):
        if not raw:
            temperatures.append(None)
        elif re.fullmatch(r'-?\d{1,2}', raw):
            temperatures.append(int(raw))
        else:
            raise ForecastError('forecast_temperature_missing')
    if temperatures == [None, None]:
        raise ForecastError('forecast_temperature_missing')
    result = {'date':at.astimezone(TZ).date().isoformat(),'place':'Seferihisar','condition':condition,
              'low':temperatures[0],'high':temperatures[1],**values,'fetched_at':at.isoformat(),'source_url':SOURCE}
    validate_forecast(result)
    from .security import assert_no_secrets
    assert_no_secrets(result)
    return result


def refresh_weather(store, at, fetcher=None):
    at = at.astimezone(TZ)
    if not 6 <= at.hour < 9:
        return
    day = at.date().isoformat()
    old = store.rows('SELECT * FROM weather_stories WHERE day=?',(day,))
    if old and old[0]['status'] in ('publishing','published','uncertain'):
        return  # A publication claim is immutable, even if the forecast changes.
    if old and old[0]['status'] == 'prepared' and datetime.fromisoformat(old[0]['checked_at']) > at-timedelta(minutes=15):
        return
    try:
        if fetcher is None:
            from .collect import Fetcher
            fetcher = Fetcher([{'url':SOURCE,'enabled':True}])
        html,_ = fetcher.get(SOURCE)
        # Freshness is measured after fetching, not from the earlier research start.
        forecast = parse_forecast(html,now())
        if forecast['date'] != day:
            raise ValueError('Research crossed a local day boundary')
        payload = json.dumps(forecast,ensure_ascii=False)
        status,result = 'prepared','prepared'
    except (requests.RequestException,ValueError,TypeError,KeyError) as exc:
        payload = old[0]['forecast'] if old else None
        status, result = 'blocked', weather_error_code(exc)
    with store.db:
        store.db.execute('INSERT INTO weather_stories(day,forecast,status,checked_at,last_result) VALUES(?,?,?,?,?) '
                         'ON CONFLICT(day) DO UPDATE SET forecast=excluded.forecast,status=excluded.status,checked_at=excluded.checked_at,last_result=excluded.last_result '
                         "WHERE weather_stories.status IN ('prepared','blocked')",(day,payload,status,now().isoformat(),result))


def weather_error_code(exc):
    if isinstance(exc, ForecastError):
        return exc.code
    if isinstance(exc, requests.exceptions.SSLError):
        return 'source_tls_failed'
    if isinstance(exc, requests.Timeout):
        return 'source_timeout'
    if isinstance(exc, requests.HTTPError):
        return 'source_http_error'
    if isinstance(exc, requests.ConnectionError):
        return 'source_connection_failed'
    if isinstance(exc, ValueError) and str(exc) == 'robots.txt disallows this path':
        return 'source_robots_denied'
    return 'forecast_invalid'


def export_weather(store,public_dir,at):
    rows = store.rows('SELECT * FROM weather_stories WHERE day=?',(at.astimezone(TZ).date().isoformat(),))
    if not rows:
        return None
    row = rows[0]
    result = {'day':row['day'],'status':row['status'],'last_result':row['last_result'],
              'checked_at':row['checked_at'],'published_at':row['published_at'],'target_time':'08:00','timezone':'Europe/Istanbul'}
    if row['forecast']:
        forecast = json.loads(row['forecast'])
        from .weather_render import render_weather
        result.update(forecast=forecast,asset_id=asset_id(forecast),asset=render_weather(forecast,public_dir))
    return result


def publish_weather(store,at,site_url,adapter=None,checkpoint=None):
    at = at.astimezone(TZ)
    # No late catch-up, old-day replay, feed, or news-slot consumption.
    if at.hour != 8:
        return {'status':'outside_window'}
    from .instagram import Instagram
    api = adapter or Instagram()
    if not api.enabled():
        return {'status':'disabled'}
    day = at.date().isoformat()
    rows = store.rows('SELECT * FROM weather_stories WHERE day=?',(day,))
    if not rows:
        return {'status':'not_ready'}
    row = rows[0]
    if row['status'] == 'published':
        return {'status':'already_published'}
    if row['status'] in ('publishing','uncertain'):
        return {'status':'awaiting_resolution'}
    if row['status'] != 'prepared' or not row['forecast']:
        return {'status': row['last_result'] if row['status'] == 'blocked' and row['last_result'] not in ('outside_window','prepared') else 'source_unavailable'}
    forecast = json.loads(row['forecast'])
    if not fresh(forecast,at):
        return {'status':'forecast_stale'}
    if site_url.rstrip('/') != SITE:
        raise ValueError('Unexpected weather media site')
    try:
        response = api.session.get(SITE+'/data.json',timeout=(8,20),allow_redirects=False)
        response.raise_for_status()
        if not 200 <= response.status_code < 300 or len(response.content) > 2_000_000:
            return {'status':'media_not_deployed'}
        snapshot = response.json()
        deployed = snapshot.get('weather_story') or {}
        expected = f'media/{asset_id(forecast)}/story-1.jpg'
        if snapshot.get('demo') is not False or deployed.get('forecast') != forecast or deployed.get('asset') != expected or deployed.get('asset_id') != asset_id(forecast):
            return {'status':'media_not_deployed'}
        url = SITE+'/'+expected
        head = api.session.head(url,timeout=15,allow_redirects=False)
        if head.status_code != 200 or not head.headers.get('Content-Type','').startswith('image/jpeg'):
            return {'status':'media_not_deployed'}
    except (requests.RequestException,ValueError,KeyError,TypeError):
        return {'status':'media_not_deployed'}
    with store.db:
        changed = store.db.execute("UPDATE weather_stories SET status='publishing',published_at=?,last_result='awaiting_resolution' WHERE day=? AND status='prepared' AND forecast=?",(at.isoformat(),day,row['forecast']))
    if changed.rowcount != 1:
        return {'status':'awaiting_resolution'}
    if checkpoint:
        checkpoint()  # Durable claim before any Meta mutation.
    try:
        container = api.container([url],'',True)
        with store.db:
            store.db.execute('UPDATE weather_stories SET container_id=? WHERE day=?',(container,day))
        if checkpoint:
            checkpoint()
        api.wait(container)
        media = api.call(f'{api.account}/media_publish',creation_id=container)['id']
        if not isinstance(media,str) or not re.fullmatch(r'\d{1,32}',media):
            raise ValueError('Invalid media identity')
        with store.db:
            store.db.execute("UPDATE weather_stories SET status='published',media_id=?,last_result='published' WHERE day=?",(media,day))
        if checkpoint:
            checkpoint()
        return {'status':'published'}
    except (requests.RequestException,RuntimeError,KeyError,ValueError):
        with store.db:
            store.db.execute("UPDATE weather_stories SET status='uncertain',last_result='uncertain' WHERE day=?",(day,))
        if checkpoint:
            checkpoint()
        return {'status':'uncertain'}


def record_result(store, day, result):
    # A delayed scheduled run must not erase the actual morning failure.
    if result['status'] == 'outside_window':
        return
    with store.db:
        store.db.execute("UPDATE weather_stories SET last_result=? WHERE day=? AND status IN ('prepared','blocked')",(result['status'],day))


def main():
    import os
    from .store import Store
    from .state_git import persist
    store = Store('state/platform.sqlite')
    try:
        result = publish_weather(store,now(),os.getenv('SITE_URL',''),
                                 checkpoint=(lambda:persist(store.path)) if os.getenv('STATE_GIT_CHECKPOINT') == 'true' else None)
        # Retain only the controlled result, even when no claim was made.
        day = now().date().isoformat()
        record_result(store,day,result)
        if target := os.getenv('GITHUB_STEP_SUMMARY'):
            with Path(target).open('a',encoding='utf-8') as out:
                out.write('### Günlük hava durumu story\n\n'+json.dumps(result)+'\n\n08:00 Türkiye saati hedeflenir. Gecikme yedeği yalnız 08:00–08:59; günde bir story.\n')
        print(json.dumps(result))
        if result['status'] not in ('published','already_published','outside_window'):
            raise SystemExit(1)
    finally:
        store.close()


if __name__ == '__main__':
    main()
