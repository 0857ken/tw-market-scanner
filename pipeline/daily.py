"""Internal acquisition into a NEW disposable candidate. Baseline is read-only.

Use python -m pipeline.daily_release for the supported candidate entry point.
Only six licensed current endpoints; no date parameters, T86, historical or paid API.
"""
import argparse
import copy
import json
import shutil
import tempfile
from datetime import datetime
from pathlib import Path
from . import parsers
from .common import ROOT, TPE, read_json, write_json, calendar_rows, expected_session
from .run import collect, build
from .research import integrate, member_on, suspended_on
from .schema import validate, valid_number
from .current_csv import fetch_twse_csv
from .candidate_io import candidate_destination, exclusive_lock, publish_directory, atomic_json
from .daily_policy import load as load_policy

MODULES = ('calendar', 'companies', 'quotes', 'tpexCompanies', 'tpexQuotes', 'tpexInstitutional')
PARSERS = {'calendar': lambda raw: (max(r['date'] for r in calendar_rows(raw)), calendar_rows(raw)),
           'companies': parsers.companies, 'quotes': parsers.quotes,
           'tpexCompanies': parsers.tpex_companies, 'tpexQuotes': parsers.tpex_quotes,
           'tpexInstitutional': parsers.tpex_institutional}


def quality(payload):
    """Disjoint price categories. Unknown reasons are not labelled suspension/no trade."""
    result = {}
    for market, module in [('TWSE', 'quotes'), ('TPEx', 'tpexQuotes')]:
        day = payload['sources'].get(module, {}).get('asOf')
        stocks = [s for s in payload['stocks'] if s['market'] == market and day and member_on(s, day)]
        counts = dict(valid=0, missingRow=0, missingPriceUnknownReason=0, confirmedSuspended=0)
        up = down = flat = change_unknown = 0
        for s in stocks:
            row = next((r for r in s['history'] if r['date'] == day), None)
            if suspended_on(s, day): counts['confirmedSuspended'] += 1
            elif not row or row.get('status') == 'missing': counts['missingRow'] += 1
            elif not valid_number(row.get('rawClose')) or row['rawClose'] <= 0: counts['missingPriceUnknownReason'] += 1
            else:
                counts['valid'] += 1
                change = row.get('changeAmount')
                if not valid_number(change) or row['rawClose'] - change <= 0: change_unknown += 1
                elif change > 0: up += 1
                elif change < 0: down += 1
                else: flat += 1
        source = payload['sources'].get(module, {})
        result[market] = {'asOf': day, 'total': len(stocks), **counts, 'missing': len(stocks)-counts['valid'],
                         'coveragePct': counts['valid']/len(stocks)*100 if stocks else None,
                         'unknownReason': counts['missingRow']+counts['missingPriceUnknownReason'],
                         'up': up, 'down': down, 'flat': flat, 'changeEligible': up+down+flat,
                         'changeUnknownAmongValidPrices': change_unknown,
                         'observedSessions': len(payload['research']['markets'][market]['sessions']),
                         'fetchedAt': source.get('fetchedAt'), 'lastAttemptAt': source.get('lastAttemptAt'),
                         'sourceVersion': source.get('sha256'), 'status': source.get('status')}
    same = result['TWSE']['asOf'] == result['TPEx']['asOf'] and result['TWSE']['asOf'] is not None
    result['ALL'] = {'sameDate': same, 'asOf': result['TWSE']['asOf'] if same else None,
                     'reason': None if same else 'Market dates differ; no combined daily breadth',
                     **{k: sum(result[m][k] for m in ('TWSE', 'TPEx')) if same else None
                        for k in ('total','valid','missing','unknownReason','up','down','flat','changeEligible')}}
    return result


def run_daily(data_dir, now=None, twse_current_csv=False, stop_on_failure=False, *, output_dir=None):
    load_policy()
    if output_dir is None:
        raise ValueError('Read-only baseline: output_dir is required; use pipeline.daily_release')
    data_dir = Path(data_dir).resolve()
    output = candidate_destination(data_dir, output_dir)
    now = now or datetime.now(TPE)
    original = read_json(data_dir/'market.json')
    if not original: raise ValueError('A validated baseline data copy is required')
    validate(original)
    attempt = {'attemptedAt': now.astimezone(TPE).isoformat(timespec='seconds'), 'modules': list(MODULES),
               'historicalRequests': 0, 'scheduleEnabled': False}
    # All multi-file writes stay in an unpublished generation. No rollback writes
    # to the input are necessary, even when a write is interrupted mid-file.
    with exclusive_lock(output.parent / ('.' + output.name + '.lock')), tempfile.TemporaryDirectory(prefix='.daily-', dir=output.parent) as tmp:
        candidate_destination(data_dir, output)  # Recheck after acquiring the lock, before HTTP.
        stage = Path(tmp)/'data'
        shutil.copytree(data_dir, stage)
        sources = copy.deepcopy(read_json(stage/'source-state.json', {}).get('sources', {}))
        sources.pop('pipeline', None)
        try:
            attempt['attemptedModules'] = []
            for module in MODULES:
                attempt['attemptedModules'].append(module)
                collect(stage, sources, module, PARSERS[module], now,
                        fetcher=fetch_twse_csv if module == 'quotes' and twse_current_csv else None)
                if stop_on_failure and sources.get(module, {}).get('fetchStatus') != 'ok':
                    break
            attempt['sources'] = {m:sources.get(m) for m in MODULES}
            errors = [m for m in MODULES if sources.get(m, {}).get('fetchStatus') != 'ok']
            if errors: raise ValueError('Update aborted; failed sources: '+', '.join(errors))
            calendar = read_json(sorted((stage/'raw').glob('calendar_*.json'))[-1])['rows']
            payload = integrate(build(stage, sources, calendar, original['creditHistory'], now), stage)
            validate(payload)
            report = {'generatedAt': payload['generatedAt'], 'asOf': payload['asOf'], 'mode': payload['mode'],
                      'stockCount': len(payload['stocks']), 'quoteDays': len(payload['quoteSessions']),
                      'sources': payload['sources'], 'coverage': quality(payload), 'freshCritical': False,
                      'warnings': ['TPEx完整交易日曆未獨立核准，更新成功不代表日期已驗證', '信用策略凍結；TWSE T86停用', '還原價格及完整歷史未驗證']}
            expected, known = expected_session(now, calendar)
            attempt.update(status='validated', expectedTWSE=expected if known else None, coverage=report['coverage'])
            write_json(stage/'source-state.json', {'sources': payload['sources']})
            write_json(stage/'quality.json', report)
            write_json(stage/'market.json', payload)
            write_json(stage/'daily-attempt.json', attempt)
            publish_directory(stage, output)
        except Exception as exc:
            attempt['sources'] = {m:sources.get(m) for m in MODULES}
            attempt.update(status='failed-last-valid-retained', error=str(exc), coverage=quality(original))
            atomic_json(output.with_name(output.name + '.attempt.json'), attempt)
            return 2
    return 0


if __name__ == '__main__':
    raise SystemExit('Internal acquisition only. Use python -m pipeline.daily_release --help; no request made.')
