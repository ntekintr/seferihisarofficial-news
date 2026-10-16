"""Public daily forecast contract. Standard library only for durable-state validation."""
from __future__ import annotations

import json
import re
from datetime import date, datetime, time, timedelta

from .domain import TZ, digest

SOURCE = 'https://www.mgm.gov.tr/tahmin/gunluk-tahmin.aspx?b=3'
SITE = 'https://ntekintr.github.io/seferihisarofficial-news'
FIELDS = {'date', 'place', 'condition', 'low', 'high', 'period_start', 'period_end', 'fetched_at', 'source_url'}
RESULTS = {'prepared', 'published', 'already_published', 'outside_window', 'disabled', 'source_unavailable',
           'forecast_invalid', 'forecast_stale', 'not_ready', 'media_not_deployed', 'awaiting_resolution', 'uncertain',
           'forecast_temperature_missing', 'forecast_district_missing', 'forecast_period_missing',
           'source_timeout', 'source_tls_failed', 'source_http_error', 'source_connection_failed', 'source_robots_denied'}
STATES = {'prepared', 'blocked', 'publishing', 'published', 'uncertain'}


def validate_forecast(value):
    if not isinstance(value, dict) or set(value) != FIELDS:
        raise ValueError('Invalid forecast fields')
    day = date.fromisoformat(value['date'])
    if day.isoformat() != value['date'] or value['place'] != 'Seferihisar' or value['source_url'] != SOURCE:
        raise ValueError('Invalid forecast identity')
    if not isinstance(value['condition'], str) or not 2 <= len(value['condition']) <= 240 or not re.fullmatch(r'[\w\s,;:.()°/–%-]+', value['condition']):
        raise ValueError('Invalid forecast description')
    temperatures = [value[k] for k in ('low', 'high') if value[k] is not None]
    if (not temperatures or any(type(v) is not int or not -40 <= v <= 60 for v in temperatures)
            or (len(temperatures) == 2 and value['low'] > value['high'])):
        raise ValueError('Invalid forecast temperature')
    stamps = [datetime.fromisoformat(value[k]) for k in ('period_start', 'period_end', 'fetched_at')]
    if any(s.tzinfo is None for s in stamps):
        raise ValueError('Forecast timezone missing')
    start, end, fetched = [s.astimezone(TZ) for s in stamps]
    morning = datetime.combine(day, time(8), TZ)
    if not start <= morning < end or not timedelta(hours=12) <= end-start <= timedelta(hours=30):
        raise ValueError('Forecast does not cover this morning')
    if not start-timedelta(hours=6) <= fetched < end:
        raise ValueError('Forecast retrieval outside validity')
    return value


def asset_id(forecast):
    validate_forecast(forecast)
    # A changed prediction or renderer receives a new URL; checking again alone does not.
    values = {k: v for k, v in forecast.items() if k != 'fetched_at'}
    return digest('daily-weather-snail-3d-v2:' + json.dumps(values, ensure_ascii=False, sort_keys=True))


def fresh(forecast, at):
    validate_forecast(forecast)
    at = at.astimezone(TZ)
    fetched = datetime.fromisoformat(forecast['fetched_at']).astimezone(TZ)
    return (forecast['date'] == at.date().isoformat() and
            datetime.fromisoformat(forecast['period_start']) <= at < datetime.fromisoformat(forecast['period_end']) and
            at-timedelta(minutes=90) <= fetched <= at+timedelta(minutes=5))
