"""Fetch the public UFC.com pages used by build_app_data.py (events listing, event pages, rankings, athlete pages)
into app/cache/. Public pages only, ~0.5 s between requests, identifying user agent.
Listing pages (events, rankings) and event pages are always re-downloaded; athlete pages are re-downloaded when older
than MAX_AGE_H hours (default 20) or with --refresh.  Writes cache/fetch_report.json for the health check.
Exit code 2 = a critical source (events listing / rankings) failed or looks broken; the cached copy is kept untouched."""
import re,os,sys,time,glob,json,subprocess
C=os.path.dirname(os.path.abspath(__file__))+'/cache/'
os.makedirs(C+'ath',exist_ok=True)
REF='--refresh' in sys.argv
MAX_AGE_H=float(os.environ.get('ATH_MAX_AGE_H','20'))
UA='Mozilla/5.0 (compatible; ufc-stats-fan-app/1.0; +https://github.com/donchakt/ufc-stats)'
REP=dict(failed=[],critical=[],counts={})
def get(url,path,force=False,minsize=5000,max_age_h=None):
    if os.path.exists(path) and os.path.getsize(path)>minsize and not force:
        if max_age_h is None or time.time()-os.path.getmtime(path)<max_age_h*3600: return True
    for k in range(3):
        r=subprocess.run(['curl','-s','-L','-m','40','-A',UA,'-o',path+'.tmp','-w','%{http_code}',url],capture_output=True,text=True)
        time.sleep(0.5)
        if r.stdout=='200' and os.path.exists(path+'.tmp') and os.path.getsize(path+'.tmp')>minsize:
            os.replace(path+'.tmp',path); return True
        time.sleep(2+3*k)
    if os.path.exists(path+'.tmp'): os.remove(path+'.tmp')
    REP['failed'].append(url)
    return False   # keep any older cached copy
def crit(msg): REP['critical'].append(msg); print('CRITICAL',msg)
# listing pages: validate before replacing the cached copy
for url,name,check in (('https://www.ufc.com/events','events.html',lambda t:len(set(re.findall(r'href="/event/([^"#?]+)"',t)))>=3),
                       ('https://www.ufc.com/rankings','rankings.html',lambda t:t.count('view-grouping-header')>=10)):
    tmp=C+name+'.new'
    if get(url,tmp,True):
        if check(open(tmp).read()): os.replace(tmp,C+name)
        else: crit(f'{url} downloaded but its layout no longer matches the scraper (selectors broke?) - kept the last good copy'); os.remove(tmp)
    else: crit(f'{url} could not be downloaded - kept the last good copy')
if not os.path.exists(C+'events.html') or not os.path.exists(C+'rankings.html'):
    json.dump(REP,open(C+'fetch_report.json','w'),indent=1); sys.exit(2)
t=open(C+'events.html').read()
slugs=sorted(set(re.findall(r'href="/event/([^"#?]+)"',t)))
REP['counts']['event_links']=len(slugs)
for s in slugs: get('https://www.ufc.com/event/'+s,C+'ufc-'+s+'.html',True)
ath=set()
for f in glob.glob(C+'ufc-*.html'): ath|=set(re.findall(r'ufc\.com/athlete/([a-z0-9-]+)',open(f).read()))
rk=open(C+'rankings.html').read(); rk=rk[:[m.start() for m in re.finditer('<div class="view-content"',rk)][1]] if rk.count('<div class="view-content"')>1 else rk
ath|=set(re.findall(r'href="/athlete/([a-z0-9-]+)"',rk))
REP['counts']['athletes']=len(ath)
print(len(slugs),'events',len(ath),'athletes',flush=True)
bad=[a for a in sorted(ath) if not get('https://www.ufc.com/athlete/'+a,C+'ath/'+a+'.html',REF,max_age_h=MAX_AGE_H)]
REP['athlete_failed']=bad
print('failed',bad)
json.dump(REP,open(C+'fetch_report.json','w'),indent=1)
sys.exit(2 if REP['critical'] else 0)
