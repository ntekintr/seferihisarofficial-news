"""Reviewed weather spelling only; no guessed forecast, severity or timing."""
from __future__ import annotations

import re
import unicodedata
from datetime import date, datetime

VERSION = 'weather-copy-v1'


class WeatherTextError(ValueError):
    """A new weather card cannot display the complete source condition safely."""


def reviewed(forecast):
    return forecast.get('display_version') == VERSION


def display_condition(forecast):
    description = forecast['condition']
    if reviewed(forecast):
        description = unicodedata.normalize('NFC', description)
        if (any(unicodedata.category(c) in ('Cc', 'Cf', 'Cs') for c in description)
                or not any(c.isalpha() for c in description)
                or description.rstrip().endswith(('...', '…'))):
            raise WeatherTextError('Unreadable forecast text')
        # Exact reviewed typo, not fuzzy correction: "buzlu", "pus" and
        # unreviewed words/names must never acquire a different weather meaning.
        def spelling(match):
            word = match.group()
            return 'PUSLU' if word.isupper() else 'Puslu' if word[:1].isupper() else 'puslu'
        description = re.sub(r'\bpuzlu\b', spelling, description, flags=re.I)
        description = ' '.join(description.split())
    # Existing day-relative interpretation is also retained for legacy cards.
    if datetime.fromisoformat(forecast['period_start']).date() < date.fromisoformat(forecast['date']):
        description = re.sub(r'\byarın\b', 'bugün', description, flags=re.I)
    return description
