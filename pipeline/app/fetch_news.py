"""Build news.json for the News tab from public RSS feeds (UFC.com, MMA Fighting, MMA Mania, Sherdog, Bloody Elbow).
Keeps headlines from the last NEWS_DAYS days that name a fighter in the app (card fighters first), tags a category from
keywords, and merges hand-curated items from news_manual.json (kept NEWS_DAYS days). Headlines + links only; nothing rehosted.
Writes cache/news_report.json (feed status) for the health check. Never fails the run: on total failure the old news.json stays."""
import re,os,json,html,time,subprocess,datetime as dt,email.utils,unicodedata
HERE=os.path.dirname(os.path.abspath(__file__)); C=HERE+'/cache/'; os.makedirs(C+'news',exist_ok=True)
UA='Mozilla/5.0 (compatible; ufc-stats-fan-app/1.0; +https://github.com/donchakt/ufc-stats)'
FEEDS=[('UFC.com','https://www.ufc.com/rss/news'),('MMA Fighting','https://www.mmafighting.com/rss/current.xml'),
       ('MMA Mania','https://www.mmamania.com/rss/current.xml'),('Sherdog','https://www.sherdog.com/rss/news.xml'),
       ('Bloody Elbow','https://bloodyelbow.com/feed/')]   # ESPN's feed answers GitHub Actions with HTTP 202 (bot check), so it is left out
DAYS=int(os.environ.get('NEWS_DAYS','10')); TODAY=dt.date.today()
def fold(s): return unicodedata.normalize('NFKD',s).encode('ascii','ignore').decode().lower()
def clean(s): return re.sub(r'\s+',' ',html.unescape(re.sub(r'<[^>]+>',' ',html.unescape(re.sub(r'<!\[CDATA\[(.*?)\]\]>',r'\1',s or '',flags=re.S))))).strip()
rep={}; items=[]
for src,url in FEEDS:
    p=C+'news/'+re.sub(r'\W','',src.lower())+'.xml'
    r=subprocess.run(['curl','-s','-L','-m','30','-A',UA,'-o',p,'-w','%{http_code}',url],capture_output=True,text=True); time.sleep(0.5)
    if r.stdout!='200' or not os.path.exists(p): rep[src]=f'HTTP {r.stdout}'; continue
    t=open(p,errors='ignore').read(); n=0
    for it in re.findall(r'<(?:item|entry)\b.*?</(?:item|entry)>',t,re.S):
        g=lambda tag:(lambda m:m.group(1) if m else '')(re.search(r'<'+tag+r'\b[^>]*>(.*?)</'+tag+'>',it,re.S))
        link=clean(g('link')) or (lambda m:m.group(1) if m else '')(re.search(r'<link[^>]+href="([^"]+)"',it))
        ds=clean(g('pubDate') or g('published') or g('updated') or g('dc:date'))
        try: d=email.utils.parsedate_to_datetime(ds).date()
        except Exception:
            try: d=dt.date.fromisoformat(ds[:10])
            except Exception: continue
        items.append(dict(src=src,title=clean(g('title')),desc=clean(g('description') or g('summary'))[:400],url=link,date=d)); n+=1
    rep[src]=f'ok {n} items' if n else 'ok but 0 items parsed (feed layout changed?)'
D=json.load(open(HERE+'/app-data.json')) if os.path.exists(HERE+'/app-data.json') else {'fighters':{}}
names=[(a['name'],a.get('card')) for a in D['fighters'].values() if len(a.get('name',''))>5]
def cat(h):
    h=h.lower()
    for k,c in ((r'injur|withdraw|pulls? out|out of|forced out|medical','Injury / withdrawal'),(r'replace|steps? in|short notice|new opponent','Replacement'),
                (r'cancel|scrapped|called off|falls? through','Bout cancelled'),(r'retire','Retirement'),(r'weigh-in|misses weight|missed weight|weight miss','Weigh-ins'),
                (r'suspend|usada|drug test|doping','Suspension'),(r'\bdef\.|defeats|knocks? out|submits|stops|results|wins|upset','Result'),
                (r'booked|set for|targeted|to headline|headline|title fight|rematch|vs\.? ','Booking')):
        if re.search(k,h): return c
    return 'News'
out=[]; seen=set()
for it in sorted(items,key=lambda x:x['date'],reverse=True):
    if (TODAY-it['date']).days>DAYS or not it['url'] or it['url'] in seen: continue
    tt=fold(it['title']); txt=tt+' '+fold(it['desc']); hit=[n for n,c in names if fold(n) in tt] or [n for n,c in names if fold(n) in txt]
    if not hit: continue
    hit.sort(key=lambda n:-len(n)); hit=[n for n in hit if not any(n!=m and fold(n) in fold(m) for m in hit)][:4]
    card=any(c for n,c in names if n in hit)
    seen.add(it['url'])
    out.append((card,[it['date'].isoformat(),it['title'],cat(it['title']),'Confirmed' if it['src']=='UFC.com' else 'Reported',hit,it['url'],it['src']]))
man=json.load(open(HERE+'/news_manual.json')) if os.path.exists(HERE+'/news_manual.json') else []
man=[m for m in man if (TODAY-dt.date.fromisoformat(m[0])).days<=DAYS and m[5] not in seen]
auto=[x for c,x in out if c][:30]; auto+= [x for c,x in out if not c][:max(0,40-len(auto))]
news=sorted(man+auto,key=lambda x:x[0],reverse=True)
rep['_kept']=len(news); rep['_auto']=len(auto); rep['_manual']=len(man)
json.dump(rep,open(C+'news_report.json','w'),indent=1)
if news: json.dump(news,open(HERE+'/news.json','w'),ensure_ascii=False,indent=0)
print('news',rep)
