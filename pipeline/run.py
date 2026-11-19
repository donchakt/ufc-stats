#!/usr/bin/env python3
"""UFC Stats app data pipeline (run by .github/workflows/update-data.yml, or by hand).
  python3 pipeline/run.py full   # UFCStats data + UFC.com events/rankings/athletes + news + odds -> rebuild -> publish
  python3 pipeline/run.py odds   # BestFightOdds only; rebuild + publish only if the lines changed
Publishing = writing index.html + data.json at the repo root (the workflow commits them if they changed).
Safety: every new build is checked against the last published data.json. If a critical source fails or the result looks
broken (no events, an event with no bouts, fighter count down >20%, rankings missing ...), nothing is published, the
previous pipeline files are restored, and the script exits 1 so the workflow run fails visibly."""
import os,sys,json,shutil,subprocess,time,datetime as dt
P=os.path.dirname(os.path.abspath(__file__)); A=P+'/app'; SITE=os.path.abspath(P+'/..')
os.environ.setdefault('TZ','America/Regina');
try: time.tzset()
except AttributeError: pass
MODE=(sys.argv[1:] or ['full'])[0]
STATE=A+'/cache/run_report.json'; REPORT=dict(mode=MODE,started=dt.datetime.now().isoformat(timespec='seconds'),steps={},problems=[])
def step(name,script,*args,fatal=True,ok_codes=(0,)):
    t=time.time(); r=subprocess.run([sys.executable,A+'/'+script,*args],cwd=A,capture_output=True,text=True)
    out=(r.stdout+r.stderr).strip(); print(f'--- {name} ({time.time()-t:.0f}s, exit {r.returncode})\n'+out[-3000:],flush=True)
    REPORT['steps'][name]=dict(exit=r.returncode,secs=round(time.time()-t),tail=out[-600:])
    if r.returncode not in ok_codes:
        msg=f'{name} failed (exit {r.returncode})'
        REPORT['problems'].append(msg)
        if fatal: abort(msg)
    return r
BACKUP=['app-data.json','news.json','cache/odds.json']
def backup():
    os.makedirs(A+'/cache/.prev',exist_ok=True)
    for f in BACKUP:
        if os.path.exists(A+'/'+f): shutil.copy(A+'/'+f,A+'/cache/.prev/'+os.path.basename(f))
def restore():
    for f in BACKUP:
        b=A+'/cache/.prev/'+os.path.basename(f)
        if os.path.exists(b): shutil.copy(b,A+'/'+f)
def save():
    REPORT['finished']=dt.datetime.now().isoformat(timespec='seconds'); json.dump(REPORT,open(STATE,'w'),indent=1)
def abort(msg):
    restore(); REPORT['aborted']=msg; save(); print('ABORTED - nothing published:',msg); sys.exit(1)
def validate():
    new=json.load(open(A+'/data.json')); old=json.load(open(SITE+'/data.json')) if os.path.exists(SITE+'/data.json') else None
    bad=[]
    if not new.get('cards'): bad.append('no upcoming events parsed')
    for c in new.get('cards',[])[:3]:
        if not c[6]: bad.append(f'event "{c[0]}" has no bouts')
    if new.get('cards') and new['cards'][0][7] and new['cards'][0][7]<(dt.date.today()-dt.timedelta(days=2)).isoformat(): bad.append('first event is in the past')
    if len(new.get('rk',[]))<10: bad.append(f'only {len(new.get("rk",[]))} ranking divisions parsed')
    if sum(1 for r in new['f'] if r[13])<0.6*len(new['f']): bad.append('fewer than 60% of fighters have a rating')
    if old:
        if len(new['f'])<0.8*len(old['f']): bad.append(f'fighter count dropped >20% ({len(old["f"])} -> {len(new["f"])})')
        ob=sum(1 for c in old['cards'] for b in c[6] if b[11]); nb=sum(1 for c in new['cards'] for b in c[6] if b[11])
        if ob>=10 and nb<0.3*ob: bad.append(f'bouts with odds dropped sharply ({ob} -> {nb})')
    return bad
backup()
if MODE=='full':
    step('UFCStats data','update_mirror.py',fatal=False)
    step('UFC.com pages','fetch_sources.py')          # exit 2 = events/rankings failed or layout changed -> abort
    step('News feeds','fetch_news.py',fatal=False)
    step('Odds','refresh_odds.py',fatal=False)          # odds failure: keep last odds, still publish the rest, flag it
    if REPORT['steps']['Odds']['exit']: REPORT['problems'].append('odds not refreshed this run (kept the last good odds)')
elif MODE=='odds':
    r=step('Odds','refresh_odds.py')
    if 'ODDS_CHANGED=1' not in r.stdout and '--force' not in sys.argv:
        REPORT['published']=False; save(); print('odds unchanged - nothing to publish'); sys.exit(0)
else: sys.exit('mode must be full or odds')
step('Build data','build_app_data.py')
step('Build page','make_html.py')
bad=validate()
if bad: abort('; '.join(bad))
shutil.copy(A+'/ufc-stats-app.html',SITE+'/index.html'); shutil.copy(A+'/data.json',SITE+'/data.json')
for f in ('manifest.webmanifest','icon-192.png','icon-512.png','apple-touch-icon.png'): shutil.copy(A+'/web/'+f,SITE+'/'+f)
REPORT['published']=True; save(); print('published index.html + data.json')
