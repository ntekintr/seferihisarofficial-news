"""Read-only production-stage status, not an assertion that every fact is true."""
from .learning import profile
from .source_discovery import summary as discovery_summary


def summary(store, at):
    from .visual_policy import summary as visual_summary
    from .delivery_audit import summary as delivery_summary
    stages = {}
    for row in store.rows('SELECT status,COUNT(*) AS n FROM posts GROUP BY status'):
        stages[row['status']] = row['n']
    return {'version': 'autonomous-factory-v1', 'checked_at': at.isoformat(),
            'approval_mode': 'automatic_checks', 'post_stages': stages,
            'learning': profile(store, at), 'source_discovery': discovery_summary(store),
            'hashtag_target': 5, 'daily_news_feed_limit': 2,
            'visual_policy': visual_summary(store),
            'delivery_audit': delivery_summary(store, at),
            'verification_scope': 'source_provenance_dates_copy_visual_subject_and_asset_binding',
            'uncertainty_policy': 'withhold_without_republishing'}
