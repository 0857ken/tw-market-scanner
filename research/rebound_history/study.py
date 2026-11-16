"""Exploratory event study using an external, independently pinned frozen rule archive."""
import argparse
from bisect import bisect_right
from collections import Counter, defaultdict
import csv
from datetime import date
from itertools import groupby
import json
from pathlib import Path
from random import Random
from statistics import mean, median

from capture import END, STUDY
from series import annual_counts, assemble, frozen, load_source

HORIZONS=(1,3,5,10,20,40,60)
MATCH_DAILY=(-.03,-.015,-.005,0,.005,.015,.03)
MATCH_DRAWDOWN=(-.10,-.07,-.03)
MIN_BLOCKS=10
RESAMPLES=9999


def excursion(rows, i, h):
    if i+h>=len(rows):
        return None
    price=rows[i]['close']
    future=rows[i+1:i+h+1]
    return (100*(future[-1]['close']/price-1),
            100*min(0,min(r['low'] for r in future)/price-1),
            100*max(0,max(r['high'] for r in future)/price-1))


def describe(values):
    n=len(values)
    if not n:
        return {'n':0,'win_pct':None,'mean_pct':None,'median_pct':None,'mean_mae_pct':None,
                'worst_mae_pct':None,'mean_mfe_pct':None,'best_mfe_pct':None}
    returns, adverse, favorable=zip(*values)
    return {'n':n,'win_pct':100*sum(x>0 for x in returns)/n,'mean_pct':mean(returns),
            'median_pct':median(returns),'mean_mae_pct':mean(adverse),'worst_mae_pct':min(adverse),
            'mean_mfe_pct':mean(favorable),'best_mfe_pct':max(favorable)}


def disjoint(keys, horizon):
    """Keep earliest trigger and require next signal strictly after exit."""
    result=[];last={}
    for segment,index in keys:
        if index>last.get(segment,-1):
            result.append((segment,index));last[segment]=index+horizon
    return result


def stratum(row):
    if row.get('day_return') is None or row.get('drawdown20') is None:
        return None
    return (row['date'][:4],bisect_right(MATCH_DAILY,row['day_return']),
            bisect_right(MATCH_DRAWDOWN,row['drawdown20']))


def match_effect(active, controls, rows, values):
    """Control means use the same year and contemporaneous return/drawdown bins."""
    donors=defaultdict(list)
    for key in controls:
        label=stratum(rows[key])
        if label is not None:
            donors[label].append(values[key][0])
    effects=[];weights=Counter()
    for key in active:
        label=stratum(rows[key])
        if label in donors:
            effects.append(values[key][0]-mean(donors[label]))
            weights[label]+=1
    return {'n':len(effects),'unique_control_days':sum(len(donors[label]) for label in weights),
            'mean_delta_pp':mean(effects) if effects else None}


def block_score(active, controls, values, horizon):
    """Centered null score, cluster wild sign test over nonoverlapping time blocks."""
    if len(disjoint(active,horizon))<MIN_BLOCKS or len(controls)<30:
        return None,0
    n=len(active)+len(controls)
    average=mean(values[k][0] for k in (*active,*controls));p=len(active)/n
    clusters=defaultdict(float)
    block=max(20,2*horizon)
    for keys,weight in ((active,1-p),(controls,-p)):
        for segment,index in keys:
            key=(segment,index)
            clusters[segment,index//block]+=weight*(values[key][0]-average)
    if len(clusters)<MIN_BLOCKS or sum(abs(v)>1e-12 for v in clusters.values())<MIN_BLOCKS:
        return None,len(clusters)
    scores=tuple(clusters.values());observed=abs(sum(scores))
    rng=Random(20261116)
    extreme=0
    for _ in range(RESAMPLES):
        sample=abs(sum(score if rng.getrandbits(1) else -score for score in scores))
        extreme+=sample+1e-12>=observed
    return (extreme+1)/(RESAMPLES+1),len(clusters)


def holm(values, family_size):
    maximum=0;out={}
    for i,(key,value) in enumerate(sorted(values.items(),key=lambda item:item[1])):
        maximum=max(maximum,(family_size-i)*value)
        out[key]=min(1.,maximum)
    return out


def write_json(path, obj):
    path.write_text(json.dumps(obj,ensure_ascii=False,indent=2,allow_nan=False)+'\n')


def write_csv(path, records):
    if records:
        with path.open('w',newline='',encoding='utf-8-sig') as f:
            writer=csv.DictWriter(f,fieldnames=list(records[0]))
            writer.writeheader();writer.writerows(records)


def evaluate(rows, frozen_rules, freeze_as_of):
    labels=frozen_rules['LABELS'];keys=tuple(labels)
    records={};signals={};values={h:{} for h in HORIZONS};exit_dates={h:{} for h in HORIZONS}
    for segment,raw in groupby(rows,key=lambda row:row['segment']):
        ind=frozen_rules['indicators'](list(raw))
        for i,row in enumerate(ind):
            if row['date']<STUDY.isoformat():
                continue
            key=(segment,i);records[key]=row
            pred=frozen_rules['signals'](ind,i)
            # The frozen down-streak predicate becomes false after the first row even when
            # fewer than four changes are observed. Mask eligibility after gaps, not its rule.
            if i<4:
                pred['down4']=None
            signals[key]=pred
            for h in HORIZONS:
                outcome=excursion(ind,i,h)
                if outcome is not None:
                    values[h][key]=outcome;exit_dates[h][key]=ind[i+h]['date']
    all_keys=list(records)
    coverage=[]
    for s,label in labels.items():
        dates=[records[k]['date'] for k in all_keys if signals[k][s] is not None]
        coverage.append({'signal':s,'label':label,'computable_days':len(dates),
                         'unknown_days':len(all_keys)-len(dates),'first':dates[0] if dates else None,
                         'last':dates[-1] if dates else None,'pit_qualified_days':0})
    annual=[];holdout=[];table=[];joined=[];pvals={};baselines=[]
    years=sorted({r['date'][:4] for r in records.values()})
    for h in HORIZONS:
        v=values[h];end=exit_dates[h]
        baseline=describe(list(v.values()))
        baselines.append({'horizon':h,**baseline})
        for s in keys:
            triggers=[k for k in all_keys if signals[k][s] is True]
            active=[k for k in triggers if k in v]
            controls=[k for k in v if signals[k][s] is False]
            best=describe([v[k] for k in active])
            base_delta=best['mean_pct']-baseline['mean_pct'] if active else None
            base_win=best['win_pct']-baseline['win_pct'] if active else None
            p,blocks=block_score(active,controls,v,h)
            if p is not None:
                pvals[s,h]=p
            table.append({'signal':s,'label':labels[s],'horizon':h,'triggers':len(triggers),
                          'censored_or_gap':len(triggers)-len(active),**best,'market_baseline_n':baseline['n'],
                          'market_baseline_mean_pct':baseline['mean_pct'],'market_baseline_win_pct':baseline['win_pct'],
                          'market_delta_pp':base_delta,'market_win_delta_pp':base_win,
                          'nonoverlap_n':len(disjoint(active,h)),
                          'nonoverlap_mean_pct':describe([v[k] for k in disjoint(active,h)])['mean_pct'],
                          **{f'matched_{k}':val for k,val in match_effect(active,controls,records,v).items()},
                          'blocks':blocks,'exploratory_block_p':p})
            for yr in years:
                pool=[k for k in v if records[k]['date'][:4]==yr==end[k][:4]]
                chosen=[k for k in pool if signals[k][s] is True]
                ordinary=describe([v[k] for k in pool])
                sample=describe([v[k] for k in chosen])
                annual.append({'signal':s,'horizon':h,'year':yr,**sample,'baseline_n':ordinary['n'],
                               'baseline_mean_pct':ordinary['mean_pct'],
                               'delta_pp':sample['mean_pct']-ordinary['mean_pct'] if chosen else None})
            groups={'EARLY_2021_2023':lambda d,e:e<'2024-01-01',
                    'LATER_2024_TO_FREEZE':lambda d,e:d>='2024-01-01' and e<=freeze_as_of,
                    'AFTER_FREEZE_DESCRIPTIVE':lambda d,e:d>freeze_as_of}
            for name,valid in groups.items():
                pool=[k for k in v if valid(records[k]['date'],end[k])]
                chosen=[k for k in pool if signals[k][s] is True]
                ordinary=describe([v[k] for k in pool]);sample=describe([v[k] for k in chosen])
                holdout.append({'signal':s,'horizon':h,'split':name,**sample,
                                'baseline_n':ordinary['n'],'baseline_mean_pct':ordinary['mean_pct'],
                                'delta_pp':sample['mean_pct']-ordinary['mean_pct'] if chosen else None})
        # Common observable universe. Nested signals count as one explanatory family.
        families=(('seasonal_touch',),('drawdown7','drawdown10'),('kd_k20',),
                  ('day_drop3','down4'),('high_turnover_fall',),('lower_wick',))
        counts={k:sum(any(signals[k][s] for s in family) for family in families) for k in v
                if all(signals[k][s] is not None for family in families for s in family)}
        just_one=[k for k,n in counts.items() if n==1]
        for name,subset in (('0',[k for k,n in counts.items() if n==0]),('1',just_one),
                            ('2+',[k for k,n in counts.items() if n>=2])):
            matched = match_effect(subset,just_one,records,v) if name=='2+' else dict.fromkeys(('n','unique_control_days','mean_delta_pp'))
            joined.append({'group':name,'horizon':h,**describe([v[k] for k in subset]),
                           'nonoverlap_n':len(disjoint(subset,h)),
                           **{f'matched_vs_one_{k}':val for k,val in matched.items()}})
    adjusted=holm(pvals,len(keys)*len(HORIZONS))
    for r in table:
        r['holm_105_q']=adjusted.get((r['signal'],r['horizon']))
        r['status']='EXPLORATORY_PIT_UNVERIFIED' if r['n'] else 'INSUFFICIENT_OR_NO_TRIGGER'
    return {'coverage':coverage,'comparison':table,'annual':annual,'time_splits':holdout,
            'concurrence':joined,'baseline':baselines}


def main():
    p=argparse.ArgumentParser(description=__doc__)
    p.add_argument('raw',type=Path);p.add_argument('archive',type=Path)
    p.add_argument('archive_sha256');p.add_argument('out',type=Path)
    p.add_argument('--exclude-margin-date',action='append',default=[],type=date.fromisoformat)
    a=p.parse_args()
    rules,freeze=frozen(a.archive,a.archive_sha256)
    rows,audit,errors,margins=assemble(a.raw,{d.isoformat() for d in a.exclude_margin_date})
    if not rows:
        p.error('no matched official market rows')
    a.out.mkdir(parents=True,exist_ok=True)
    try:
        counts=annual_counts(load_source(a.raw,'official_checks','twse-factbook-2026'))
    except (OSError,ValueError,KeyError):
        counts={}
    observed=Counter(row['date'][:4] for row in rows)
    yearly=[{'year':yr,'confirmed_report_sessions':observed[yr],
             'official_factbook_sessions':counts.get(yr),
             'count_matches':observed[yr]==counts[yr] if yr in counts else None}
            for yr in map(str,range(2021,2027))]
    write_csv(a.out/'annual_trade_day_check.csv',yearly)
    out=evaluate(rows,rules,freeze['basis_as_of'])
    for name,records in out.items():
        write_csv(a.out/(name+'.csv'),records)
    write_csv(a.out/'sessions.csv',audit)
    write_csv(a.out/'input_series.csv',rows)
    # Next-session 'previous balance' is an ex-post reconciliation, never a signal input.
    quality=[]
    for i,row in enumerate(rows):
        day=date.fromisoformat(row['date'])
        if day not in margins:
            continue
        following=margins.get(date.fromisoformat(rows[i+1]['date'])) if i+1<len(rows) and rows[i+1]['segment']==row['segment'] else None
        record=margins[day]
        quality.append({'date':str(day),**record,'admitted':row['margin_100m'] is not None,
                        'next_report_revision_thousand':following['margin_previous_thousand']-record['margin_today_thousand'] if following else None})
    write_csv(a.out/'margin_quality.csv',quality)
    write_json(a.out/'source_exclusions.json',errors)
    write_json(a.out/'summary.json',{'study_from':str(STUDY),'through':str(END),
        'official_market_rows_including_warmup':len(rows),'first':rows[0]['date'],'last':rows[-1]['date'],
        'audit_total':dict(Counter(r['state'] for r in audit)),
        'audit_study':dict(Counter(r['state'] for r in audit if r['research_period'])),
        'margin_excluded_by_review':[d.isoformat() for d in a.exclude_margin_date],
        'freeze':freeze,'signals':15,'horizons':HORIZONS,'pit_qualified_days':0})


if __name__=='__main__':
    main()
