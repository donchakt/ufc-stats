"""Refresh the UFCStats.com fight data (public CSV scrape maintained at github.com/Greco1899/scrape_ufc_stats, refreshed
after each event) into sources/featherweight/ufcstats-mirror/. Each file is only replaced if the header is unchanged and
it has at least as many rows as the current copy (and the newest event is not older), so a bad upstream push never
replaces good data. Writes cache/mirror_report.json. Never fatal."""
import os,csv,io,json,subprocess,datetime as dt
HERE=os.path.dirname(os.path.abspath(__file__)); ROOT=os.path.abspath(HERE+'/..')+'/'
M=ROOT+'sources/featherweight/ufcstats-mirror/'; C=HERE+'/cache/'; os.makedirs(C,exist_ok=True)
BASE='https://raw.githubusercontent.com/Greco1899/scrape_ufc_stats/main/'
UA='Mozilla/5.0 (compatible; ufc-stats-fan-app/1.0; +https://github.com/donchakt/ufc-stats)'
FILES=['ufc_event_details','ufc_fight_results','ufc_fight_stats','ufc_fighter_details','ufc_fighter_tott']
def rows(t): return list(csv.reader(io.StringIO(t)))
def newest(t):
    ds=[]
    for r in csv.DictReader(io.StringIO(t)):
        try: ds.append(dt.datetime.strptime(r['DATE'].strip(),'%B %d, %Y').date())
        except Exception: pass
    return max(ds) if ds else None
rep={}
for f in FILES:
    p=M+f+'.csv'
    r=subprocess.run(['curl','-s','-L','-m','60','-A',UA,BASE+f+'.csv'],capture_output=True)
    if r.returncode or len(r.stdout)<1000: rep[f]='download failed - kept current copy'; continue
    new=r.stdout.decode('utf-8','replace'); old=open(p,encoding='utf-8',errors='replace').read() if os.path.exists(p) else ''
    nr,orr=rows(new),rows(old) if old else []
    if orr and nr[0]!=orr[0]: rep[f]='upstream header changed - kept current copy (scraper needs a look)'; continue
    if len(nr)<len(orr): rep[f]=f'upstream has fewer rows ({len(nr)} < {len(orr)}) - kept current copy'; continue
    if f=='ufc_event_details' and old and newest(new) and newest(old) and newest(new)<newest(old): rep[f]='upstream newest event is older - kept current copy'; continue
    if new!=old: open(p,'w',encoding='utf-8').write(new); rep[f]=f'updated ({len(orr)} -> {len(nr)} rows)'
    else: rep[f]='unchanged'
ev=open(M+'ufc_event_details.csv',encoding='utf-8').read()
rep['_newest_event']=str(newest(ev))
json.dump(rep,open(C+'mirror_report.json','w'),indent=1)
print('mirror',rep)
