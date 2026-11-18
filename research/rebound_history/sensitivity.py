"""Exploratory next-session-open sensitivity for the unchanged frozen rebound signals.

This module never asserts point-in-time (PIT) validity or index tradability.
It measures how a price-index proxy changes when entry is delayed from the
signal day's closing index to the next recorded session's opening index.
"""
import argparse
from itertools import groupby
from pathlib import Path
from statistics import mean

from capture import STUDY
from series import assemble, frozen
from study import HORIZONS, describe, disjoint, match_effect, write_csv


def next_open_outcome(session_rows, index, horizon):
    """Return percentage change from t+1 open to t+h close, or None if censored."""
    if horizon < 1:
        raise ValueError('horizon must be at least 1')
    if index + horizon >= len(session_rows):
        return None
    entry = session_rows[index + 1]['open']
    exit_close = session_rows[index + horizon]['close']
    if not entry or entry <= 0 or not exit_close or exit_close <= 0:
        return None
    return 100 * (exit_close / entry - 1)


def evaluate_next_open(rows, rules):
    """Compute 15x7 descriptive sensitivities without altering frozen signals.

    Missing signals remain UNKNOWN and are never used as false controls.
    Outcomes stop at the end of an intact segment; the next index opening
    belongs to the first eligible session *after* the signal's close.
    """
    labels = rules['LABELS']
    records, signals = {}, {}
    values = {h: {} for h in HORIZONS}
    for segment, raw in groupby(rows, key=lambda item: item['segment']):
        enriched = rules['indicators'](list(raw))
        for index, row in enumerate(enriched):
            if row['date'] < STUDY.isoformat():
                continue
            key = (segment, index)
            records[key] = row
            outcome = dict(rules['signals'](enriched, index))
            # Same availability mask already used in study.evaluate.
            if index < 4:
                outcome['down4'] = None
            signals[key] = outcome
            for horizon in HORIZONS:
                value = next_open_outcome(enriched, index, horizon)
                if value is not None:
                    values[horizon][key] = (value, 0.0, 0.0)
    all_keys = list(records)
    result = []
    for name, label in labels.items():
        for horizon in HORIZONS:
            values_h = values[horizon]
            triggered = [k for k in all_keys if signals[k][name] is True]
            active = [k for k in triggered if k in values_h]
            controls = [k for k in values_h if signals[k][name] is False]
            simple = describe([values_h[k] for k in active])
            independent = disjoint(active, horizon)
            matched = match_effect(active, controls, records, values_h)
            result.append({
                'signal': name, 'horizon': horizon,
                'trigger_n': len(triggered), 'n': len(active),
                'censored_or_gap': len(triggered) - len(active),
                'next_open_mean_pct': simple['mean_pct'],
                'next_open_median_pct': simple['median_pct'],
                'next_open_win_pct': simple['win_pct'],
                'nonoverlap_n': len(independent),
                'nonoverlap_mean_pct': mean(values_h[k][0] for k in independent) if independent else None,
                'matched_n': matched['n'],
                'matched_delta_pp': matched['mean_delta_pp'],
                'pit_qualified_n': 0,
                'status': 'EXPLORATORY_INDEX_PROXY_NOT_PIT' if active else 'NO_MATURED_EVENTS',
            })
    return result


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('raw', type=Path)
    parser.add_argument('archive', type=Path)
    parser.add_argument('archive_sha256')
    parser.add_argument('out', type=Path)
    parser.add_argument('--exclude-margin-date', action='append', default=[])
    args = parser.parse_args()
    rules, _ = frozen(args.archive, args.archive_sha256)
    rows, _, _, _ = assemble(args.raw, set(args.exclude_margin_date))
    if not rows:
        parser.error('no validated official rows')
    args.out.parent.mkdir(parents=True, exist_ok=True)
    write_csv(args.out, evaluate_next_open(rows, rules))
    print('DESCRIPTIVE_ONLY: next-open index proxy; PIT remains BLOCKED, no executable-trade claim')


if __name__ == '__main__':
    main()
