#!/usr/bin/env python3
"""Self-check for the UFC Stats app: lists anything that needs a human/AI fix and writes pipeline/app/cache/health.md (issue body)
and health.json. The workflow opens/updates a GitHub issue labelled 'data-health' with it, and closes the issue
when the list is empty. Never fails the job by itself."""
import os,json,datetime as dt,re
P=os.path.dirname(os.path.abspath(__file__)); A=P+'/app'; C=A+'/cache/'
def J(p,d=None):
    try: return json.load(open(p))
    except Exception: return d
run=J(C+'run_report.json',{}); fr=J(C+'fetch_report.json',{}); orp=J(C+'odds_report.json',{}); nr=J(C+'news_report.json',{}); mr=J(C+'mirror_report.json',{})
D=J(A+'/app-data.json',{}); F=D.get('fighters',{}); today=dt.date.today()
S={'Pipeline / publishing':[],'Scrapers & sources':[],'Odds missing (fights in the next 10 days)':[],'Fighter data gaps (cards in the next 21 days)':[],'Rankings':[]}
info=[]
# pipeline
if run.get('aborted'): S['Pipeline / publishing'].append(f"Last **{run.get('mode')}** run did NOT publish (kept last good data): {run['aborted']}")
for p in run.get('problems',[]):
    if not run.get('aborted') or p not in run['aborted']: S['Pipeline / publishing'].append(p)
# scrapers
for c in fr.get('critical',[]): S['Scrapers & sources'].append('UFC.com: '+c)
fa=fr.get('athlete_failed',[])
if fa: S['Scrapers & sources'].append(f"UFC.com athlete pages failed to download ({len(fa)}): "+', '.join(fa[:15])+(' ...' if len(fa)>15 else ''))
oth=[u for u in fr.get('failed',[]) if '/athlete/' not in u]
if oth: S['Scrapers & sources'].append('UFC.com pages failed: '+', '.join(oth[:10]))
if orp:
    if orp.get('failed'): S['Scrapers & sources'].append('BestFightOdds event pages failed: '+', '.join(orp['failed']))
    if orp.get('index_events') and not orp.get('bouts'): S['Scrapers & sources'].append('BestFightOdds: pages downloaded but 0 odds parsed - odds table layout probably changed')
for k,v in nr.items():
    if not k.startswith('_') and not re.match(r'ok [1-9]',str(v)): S['Scrapers & sources'].append(f'News feed {k}: {v}')
for k,v in mr.items():
    if not k.startswith('_') and 'kept current copy' in str(v): S['Scrapers & sources'].append(f'UFCStats data {k}: {v}')
ne=mr.get('_newest_event')
if ne and ne!='None' and (today-dt.date.fromisoformat(ne)).days>16: S['Scrapers & sources'].append(f'UFCStats fight data is stale: newest event {ne} (upstream CSV not updated?) - recent results only come from UFC.com pages')
evs=D.get('events',[])
if not evs: S['Scrapers & sources'].append('No upcoming events parsed from UFC.com')
for e in evs:
    if not e['bouts']: S['Scrapers & sources'].append(f"{e['title']} ({e['date']}): no bouts parsed - event page layout changed or card not announced")
    tbd=[b for b in e['bouts'] if not b.get('sa') or not b.get('sb')]
    if tbd and (dt.date.fromisoformat(e['iso'])-today).days<=21: S['Scrapers & sources'].append(f"{e['title']}: {len(tbd)} bout(s) with a fighter that has no UFC.com profile link (TBD/new signing?): "+', '.join(f"{b['a']} vs {b['b']}" for b in tbd[:6]))
# odds
for e in evs:
    d=(dt.date.fromisoformat(e['iso'])-today).days
    if d<0 or d>10: continue
    miss=[f"{b['a']} vs {b['b']}" for b in e['bouts'] if not b.get('odds')]
    if miss: S['Odds missing (fights in the next 10 days)'].append(f"{e['title']} ({e['date']}): {len(miss)}/{len(e['bouts'])} bouts without odds - "+'; '.join(miss)+' (name mismatch with BestFightOdds, or no lines posted yet)')
# fighter gaps
near=set()
for e in evs:
    if (dt.date.fromisoformat(e['iso'])-today).days<=21:
        for b in e['bouts']: near|={b.get('sa'),b.get('sb')}
near.discard(None)
for s in sorted(near):
    f=F.get(s)
    if not f: S['Fighter data gaps (cards in the next 21 days)'].append(f'`{s}`: no data at all (UFC.com athlete page missing or unparsable)'); continue
    miss=[l for k,l in (('ht','height'),('reach','reach')) if not f.get(k)]
    if not f.get('dob') and f.get('age') is None: miss.append('age')
    if not f.get('rec'): miss.append('pro record')
    if not f.get('rating') and f.get('ufc',0)>0: miss.append('rating')
    if f.get('ufc',0)>0 and not f.get('stats'): miss.append('fight stats (has UFC fights but none matched in UFCStats data - name mismatch?)')
    if miss: S['Fighter data gaps (cards in the next 21 days)'].append(f"{f['name']} (`{s}`, {f.get('ufc',0)} UFC fights): missing "+', '.join(miss))
for g in D.get('gaps',[]):
    s,msg=(g[0],g[1]) if isinstance(g,(list,tuple)) else (g,'')
    if s in near and 'debut' in msg: info.append(f'{msg} (UFC debut is expected to have no UFC stats)')
# rankings
for r in D.get('rankings',[]):
    if 'Pound' in r['div']: continue
    if not r.get('champ'): info.append(f"{r['div']}: no champion listed (vacant?)")
    if len(r.get('list',[]))<15: S['Rankings'].append(f"{r['div']}: only {len(r.get('list',[]))} ranked fighters parsed (expected 15)")
if len(D.get('rankings',[]))<10: S['Rankings'].append(f"only {len(D.get('rankings',[]))} ranking divisions parsed")
n=sum(len(v) for v in S.values())
now=dt.datetime.now().strftime('%b %-d, %Y %-I:%M %p')+' CST'
body=[f'Automated data health check for the [UFC Stats app](https://donchakt.github.io/ufc-stats/). **{n} item(s) need attention.**',
      f"Last checked {now} ({run.get('mode','?')} run). Data on the site: updated {D.get('asof')}, odds as of {D.get('odds_asof')}, UFCStats fight data to {ne or D.get('mirror_end')}.",'']
for k,v in S.items():
    if v: body+=[f'### {k}']+[f'- [ ] {x}' for x in v]+['']
if info: body+=['<details><summary>FYI (no action needed)</summary>','']+[f'- {x}' for x in info]+['','</details>','']
body+=['This issue is updated by the `Update data` workflow on every run and closes itself when everything is clean.']
open(C+'health.md','w').write('\n'.join(body)+'\n')
json.dump(dict(count=n,checked=now,sections=S,info=info),open(C+'health.json','w'),indent=1)
print(f'health: {n} item(s)'); print('\n'.join(body))
