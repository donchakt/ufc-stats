import os as _o; UFC_ROOT=_o.environ.get('UFC_ROOT') or _o.path.abspath(_o.path.join(_o.path.dirname(_o.path.abspath(__file__)),'..'))+'/'
"""Build app-data.json for the UFC Stats app (Page + standalone HTML).
Sources (public only):
  - UFC.com: /events, event pages (upcoming cards + results after the mirror end), /rankings, athlete pages
    (record, nickname, division, age, height, reach, wins by KO/SUB/DEC)  -> fetched by fetch_sources.py into app/cache/
  - UFCStats.com (Greco1899 mirror, sources/featherweight/ufcstats-mirror/, UFC fights to 2026-10-17) -> fight history,
    per-round stats for career averages (UFCStats definitions), stance, nickname fallback
  - UFCStats public event pages supplement (sources/ufcstats-supplement/event-pages-2026-10.csv) -> landed totals
    for UFC 333 + Vegas 123 (counts/minutes only; no attempts, so they are left out of % stats)
Usage: python3 fetch_sources.py && python3 build_app_data.py   (then run make_html.py and refresh the Page)"""
import csv,re,os,json,glob,html,unicodedata,datetime as dt,collections
HERE=os.path.dirname(os.path.abspath(__file__)); C=HERE+'/cache/'
ROOT=UFC_ROOT+''; M=ROOT+'sources/featherweight/ufcstats-mirror/'
SUP=ROOT+'sources/ufcstats-supplement/event-pages-2026-10.csv'
NOW=dt.datetime.now()
def clean(s): return re.sub(r'\s+',' ',html.unescape(re.sub(r'<[^>]+>',' ',s or ''))).strip()
def norm(s):
    s=unicodedata.normalize('NFKD',s).encode('ascii','ignore').decode().lower()
    return re.sub(r'[^a-z ]','',s.replace('-',' ')).split()
def key(s): return ''.join(norm(s))
ALIAS={}  # ufc.com name -> mirror name, filled for known spelling differences
# ---------------- UFC.com events ----------------
def parse_event(path):
    t=open(path).read()
    title=clean(re.search(r'<title>(.*?)</title>',t,re.S).group(1)).replace(' | UFC','').replace('Polymarket ','')
    venue=re.search(r'field--name-venue[^>]*>(.*?)</div>',t,re.S)
    secs=[]
    for m in re.finditer(r'id="(main-card|prelims-card|early-prelims)"',t):
        ts=re.search(r'data-timestamp="(\d+)"',t[m.start():m.start()+3000])
        secs.append((m.start(),m.group(1),int(ts.group(1)) if ts else None))
    hero=re.search(r'data-main-card-timestamp="(\d+)"',t) or re.search(r'c-hero__headline-suffix[^>]*data-timestamp="(\d+)"',t)
    tss=[s[2] for s in secs if s[2]] or ([int(hero.group(1))] if hero else [int(x) for x in re.findall(r'data-timestamp="(\d+)"',t[:60000])][-1:])
    pos=[m.start() for m in re.finditer('<div class="c-listing-fight"',t)]
    bouts=[]
    for i,p in enumerate(pos):
        b=t[p:pos[i+1] if i+1<len(pos) else len(t)]
        if 'c-listing-fight__class--desktop' not in b: continue
        d=b[b.find('c-listing-fight__class--desktop'):]
        wc=clean(re.search(r'class-text">(.*?)</div>',d,re.S).group(1))
        ranks=[clean(x) for x in re.findall(r'corner-rank[^"]*">\s*<span>(.*?)</span>',d[:900],re.S)]
        names=re.findall(r'corner-name--(?:red|blue)">(.*?)</div>',b,re.S)
        sl=[(re.search(r'athlete/([a-z0-9-]+)',n).group(1) if 'athlete/' in n else None) for n in names[:2]]
        oc=[clean(x) for x in re.findall(r'corner-body--(?:red|blue)">(.*?)</div>\s*</div>\s*</div>',b,re.S)][:2]
        rt=[clean(x) for x in re.findall(r'result-text[^"]*"[^>]*>(.*?)</div>',b,re.S)][:3]
        sec=[s for q,s,_ in secs if q<p]
        bouts.append(dict(sec=sec[-1] if sec else '',wc=wc,names=[clean(n) for n in names[:2]],slugs=sl,
            ranks=(ranks+['',''])[:2] if len(ranks)>=2 else ['',''],out=oc,rd=rt[0] if rt else '',tm=rt[1] if len(rt)>1 else '',meth=rt[2] if len(rt)>2 else ''))
    when=dt.datetime.fromtimestamp(min(tss)) if tss else None
    vt=', '.join(x.strip(' ,') for x in html.unescape(re.sub(r'<[^>]+>','',venue.group(1))).split('\n') if x.strip(' ,')) if venue else ''
    for w in sorted(set(vt.replace(',',' ').split()+[' '.join(vt.split()[-2:])]),key=len,reverse=True):
        if len(w)>3 and title.endswith(' '+w) and len(title)-len(w)>8: title=title[:-len(w)-1]; break
    return dict(title=title,venue=vt,when=when,
                times={s:dt.datetime.fromtimestamp(ts).strftime('%-I:%M %p') for _,s,ts in secs if ts},bouts=bouts,url='https://www.ufc.com/event/'+os.path.basename(path)[4:-5])
EVS=[parse_event(f) for f in glob.glob(C+'ufc-*.html')]
EVS=[e for e in EVS if e['when']]
upcoming=sorted([e for e in EVS if e['when']>NOW-dt.timedelta(hours=12)],key=lambda e:e['when'])
# ---------------- rankings ----------------
rk=open(C+'rankings.html').read(); cuts=[m.start() for m in re.finditer('<div class="view-content"',rk)]
rk=rk[:cuts[1]] if len(cuts)>1 else rk
RANK={}; RLISTS=[]
for g in re.split(r'<div class="view-grouping">',rk)[1:]:
    h=clean(re.search(r'view-grouping-header">(.*?)</div>',g,re.S).group(1))
    ch=re.search(r'<h5>\s*<a href="/athlete/([^"]+)"',g)
    lst=re.findall(r'views-field-title[^>]*>\s*<a href="/athlete/([^"]+)"',g)
    if 'Pound-for-Pound' in h:
        RLISTS.append((h.replace(' Top Rank',''),None,lst)); continue
    RLISTS.append((h,ch.group(1) if ch else None,lst))
    if ch: RANK.setdefault(ch.group(1),[]).append((h,'C'))
    for i,(s,_) in enumerate(re.findall(r'views-field-title[^>]*>\s*<a href="/athlete/([^"]+)"[^>]*>([^<]+)</a>',g)):
        rows=re.findall(r'views-field-weight-class-rank">\s*([^<]*?)\s*<',g)
        RANK.setdefault(s,[]).append((h,'#'+(rows[i].strip() if i<len(rows) and rows[i].strip() else str(i+1))))
# ---------------- athlete pages ----------------
def athlete(slug):
    p=C+'ath/'+slug+'.html'
    if not os.path.exists(p): return None
    t=open(p).read()
    g=lambda rx:(lambda m:clean(m.group(1)) if m else '')(re.search(rx,t,re.S))
    a=dict(slug=slug,name=g(r'hero-profile__name">(.*?)</h1>'),nick=g(r'hero-profile__nickname">(.*?)</p>').strip('"'),
           div=g(r'hero-profile__division-title">(.*?)</p>'),rec=g(r'hero-profile__division-body">(.*?)</p>').replace(' (W-L-D)',''),
           age=g(r'field--name-age[^>]*>(\d+)'))
    a['age']=int(a['age']) if a['age'].isdigit() else None
    if a['age'] is None: a.pop('age')
    bio={clean(l):clean(v) for l,v in re.findall(r'c-bio__label">(.*?)</div>\s*<div class="c-bio__text">(.*?)</div>',t,re.S)}
    for k,f in (('ht','Height'),('reach','Reach')):
        try: a[k]=float(bio.get(f,''))
        except ValueError: pass
    meth={clean(l):clean(v) for l,v in re.findall(r'c-stat-3bar__label">(.*?)</div>\s*<div class="c-stat-3bar__value">(.*?)</div>',t,re.S)}
    for k,f in (('ko','KO/TKO'),('dec','DEC'),('sub','SUB')):
        m=re.match(r'(\d+)',meth.get(f,''))
        if m: a[k]=int(m.group(1))
    hs=dict((clean(b),clean(a_)) for a_,b in re.findall(r'hero-profile__stat-numb">(.*?)</p>\s*<p class="hero-profile__stat-text">(.*?)</p>',t,re.S))
    if 'ko' not in a and 'Wins by Knockout' in hs: a['ko']=int(hs['Wins by Knockout'])
    if 'sub' not in a and 'Wins by Submission' in hs: a['sub']=int(hs['Wins by Submission'])
    if 'First Round Finishes' in hs: a['r1']=int(hs['First Round Finishes'])
    m=re.search(r'<img src="https://(?:www\.)?ufc\.com/images/styles/athlete_bio_full_body/s3/([^"?]+)\?(?:[^"]*?)itok=([^"&]+)"[^>]*class="hero-profile__image',t)
    if m and 'SHADOW' not in m.group(1): a['img']=m.group(1)+'|'+m.group(2)   # public UFC.com athlete photo (hotlinked, not rehosted)
    return a if a['name'] else None
# ---------------- mirror ----------------
def D(s): return dt.datetime.strptime(s.strip(),'%B %d, %Y').date()
EVD={r['EVENT'].strip():D(r['DATE']) for r in csv.DictReader(open(M+'ufc_event_details.csv'))}
RES=list(csv.DictReader(open(M+'ufc_fight_results.csv'))); ST=list(csv.DictReader(open(M+'ufc_fight_stats.csv')))
TOTT=collections.defaultdict(list)
for r in csv.DictReader(open(M+'ufc_fighter_tott.csv')): TOTT[r['FIGHTER'].strip()].append(r)
NICK={}
for r in csv.DictReader(open(M+'ufc_fighter_details.csv')): NICK.setdefault((r['FIRST']+' '+r['LAST']).strip(),r['NICKNAME'].strip())
MIRROR_END=max(EVD.values())
BYK=collections.defaultdict(set)
for r in RES:
    for n in r['BOUT'].split(' vs. '): BYK[key(n)].add(n.strip())
def of(s):
    m=re.match(r'(\d+) of (\d+)',s or ''); return (int(m[1]),int(m[2])) if m else (0,0)
def sec(s):
    try: m_,s2=s.split(':'); return int(m_)*60+int(s2)
    except Exception: return 0
STB=collections.defaultdict(list)
for s in ST: STB[(s['EVENT'].strip(),s['BOUT'].strip())].append(s)
def wc_ok(wc,div):  # used only for same-name collisions
    return div.replace(' Division','').lower() in wc.lower() or 'catch' in wc.lower() or 'open' in wc.lower()
COLLIDE={n for n,v in TOTT.items() if len(v)>1}
def mirror_name(name,slug):
    if name in ALIAS: return ALIAS[name]
    k=key(name)
    if k in BYK: return sorted(BYK[k])[0]
    toks=norm(name)
    if len(toks)>1:  # try first+last tokens only, and reversed order (Asian names)
        for cand in (toks[0]+toks[-1],toks[-1]+toks[0],''.join(reversed(toks))):
            if cand in BYK: return sorted(BYK[cand])[0]
    sk=key(slug)
    if sk in BYK: return sorted(BYK[sk])[0]
    return None
def mirror_fights(mn,div):
    out=[]
    for r in RES:
        a,b=[x.strip() for x in r['BOUT'].split(' vs. ')]
        if mn not in (a,b): continue
        if mn in COLLIDE and not wc_ok(r['WEIGHTCLASS'],div): continue
        ev=r['EVENT'].strip(); me=0 if a==mn else 1; opp=b if me==0 else a
        oc=r['OUTCOME'].split('/'); res=oc[me] if len(oc)==2 else r['OUTCOME']
        res={'W':'W','L':'L','D':'D','NC':'NC'}.get(res.strip(),res.strip())
        meth=r['METHOD'].strip()
        if 'Could Not Continue' in meth or 'Overturned' in meth: res='NC' if res not in ('W','L') else res
        rd=int(r['ROUND']) if r['ROUND'].strip().isdigit() else 0
        rows=STB.get((ev,r['BOUT'].strip()),[])
        out.append(dict(date=EVD.get(ev),opp=opp,res=res,meth=meth,rd=rd,tm=r['TIME'].strip(),ev=ev,
            secs=(rd-1)*300+sec(r['TIME']) if rd else 0,rows=rows,me=mn))
    return out
SUPR=[r for r in csv.DictReader(open(SUP)) if dt.date.fromisoformat(r['date'])>MIRROR_END]   # only events the mirror does not cover yet
def mstat(fs,mn,name):
    t=collections.Counter()
    for f in fs:
        if not f['rows'] or not f['secs']: continue
        t['sec']+=f['secs']; t['psec']+=f['secs']
        for r in f['rows']:
            mine=r['FIGHTER'].strip()==mn
            sl,sa=of(r['SIG.STR.']); tl,ta=of(r['TD']); sub=int(float(r['SUB.ATT'] or 0))
            p='' if mine else 'o_'
            t[p+'sl']+=sl;t[p+'sa']+=sa;t[p+'tl']+=tl;t[p+'ta']+=ta;t[p+'sub']+=sub
            t[p+'psl']+=sl;t[p+'pta']+=ta;t[p+'ptl']+=tl
    for r in SUPR:  # landed-only supplement: counts + minutes, not % stats
        nm=[key(r['winner']),key(r['loser'])]
        if key(mn) in nm or key(name) in nm:
            w=key(r['winner']) in (key(mn),key(name)); a,b=('w','l') if w else ('l','w')
            s_=(int(r['round'])-1)*300+sec(r['time']); t['sec']+=s_
            t['sl']+=int(r[a+'_sl']);t['o_sl']+=int(r[b+'_sl']);t['tl']+=int(r[a+'_td']);t['sub']+=int(r[a+'_sub'])
    if t['sec']<=0: return None
    mn_=t['sec']/60
    st=dict(slpm=round(t['sl']/mn_,2),sapm=round(t['o_sl']/mn_,2),tdavg=round(t['tl']/mn_*15,2),subavg=round(t['sub']/mn_*15,1))
    if t['sa']: st['acc']=round(100*t['psl']/t['sa'])
    if t['o_sa']: st['def']=round(100*(1-t['o_psl']/t['o_sa']))
    if t['ta']: st['tdacc']=round(100*t['ptl']/t['ta'])
    if t['o_ta']: st['tddef']=round(100*(1-t['o_ptl']/t['o_ta']))
    return st
# post-mirror results from UFC.com event pages
POST=[]
for e in EVS:
    if e['when'].date()<=MIRROR_END or e['when']>NOW: continue
    for b in e['bouts']:
        if len(b['names'])<2 or not b['out'] or not any(b['out']): continue
        POST.append(dict(e=e,b=b))
def post_fights(slug,name):
    out=[]
    for x in POST:
        b=x['b']; idx=[i for i in (0,1) if b['slugs'][i]==slug or key(b['names'][i])==key(name)]
        if not idx: continue
        i=idx[0]; o=b['out'][i] if i<len(b['out']) else ''
        res={'Win':'W','Loss':'L','Draw':'D','No Contest':'NC','NC':'NC'}.get(o,'')
        if not res: continue
        out.append(dict(date=x['e']['when'].date(),opp=b['names'][1-i],res=res,meth=b['meth'],rd=int(b['rd']) if b['rd'].isdigit() else 0,tm=b['tm'],ev=x['e']['title']))
    return out
def short_m(m):
    m=m.replace('Decision - Unanimous','U-DEC').replace('Decision - Split','S-DEC').replace('Decision - Majority','M-DEC')
    m=m.replace('Submission','SUB').replace('Could Not Continue','CNC').replace("TKO - Doctor's Stoppage",'TKO (Dr)')
    return m.replace('Overturned','Overturned').strip()
def short_ev(ev):
    ev=ev.strip().replace('UFC Fight Night:','UFC FN:').replace('UFC on ESPN:','UFC on ESPN:')
    return ev
# ---------------- assemble ----------------
card=[]; seen=[]
for e in upcoming:
    for b in e['bouts']:
        for s in b['slugs']:
            if s and s not in seen: seen.append(s)
card_slugs=list(seen)
ranked=[s for s in dict.fromkeys(sorted(RANK.keys()|set(x for _,c,l in RLISTS for x in ([c] if c else [])+l))) if s not in seen]
F={}; gaps=[]
for s in card_slugs+ranked:
    a=athlete(s)
    if not a: gaps.append((s,'no UFC.com athlete page')); continue
    mn=mirror_name(a['name'],s)
    fs=[]; st=None
    if mn:
        mf=mirror_fights(mn,a['div']); st=mstat(mf,mn,a['name']); fs=mf
        tott=[r for r in TOTT.get(mn,[])]
        if tott and tott[0]['STANCE'].strip(): a['stance']=tott[0]['STANCE'].strip()
        if tott:   # UFCStats tale of the tape: DOB (age computed in the app as of today), height/reach fallback
            try: a['dob']=dt.datetime.strptime(tott[0]['DOB'].strip(),'%b %d, %Y').date().isoformat()
            except ValueError: pass
            if a.get('dob') and a.get('age') is not None:   # same-name collision guard: DOB must agree with UFC.com age
                d0=dt.date.fromisoformat(a['dob']);t0=dt.date.today();ag=t0.year-d0.year-((t0.month,t0.day)<(d0.month,d0.day))
                if abs(ag-a['age'])>1: a.pop('dob')
            if not a.get('ht'):
                m=re.match(r"(\d+)' (\d+)\"",tott[0]['HEIGHT'].strip())
                if m: a['ht']=float(int(m[1])*12+int(m[2]))
            if not a.get('reach'):
                m=re.match(r'(\d+(?:\.\d+)?)"',tott[0]['REACH'].strip())
                if m: a['reach']=float(m[1])
        if not a['nick'] and NICK.get(mn): a['nick']=NICK[mn]
    pf=post_fights(s,a['name'])
    allf=[dict(date=f['date'],opp=f['opp'],res=f['res'],meth=f['meth'],rd=f['rd'],tm=f['tm'],ev=f['ev']) for f in fs if f['date']]+pf
    allf.sort(key=lambda f:f['date'],reverse=True)
    if not mn and not pf: gaps.append((s,a['name']+': no UFC fights in UFCStats data (debut or name mismatch)'))
    a['nick']=(a.get('nick') or '').strip()
    if a.get('rec')=='0-0-0': a.pop('rec')
    if not any(a.get(k) for k in ('ko','sub','dec','r1')):
        for k in ('ko','sub','dec','r1'): a.pop(k,None)
    a['ufc']=len(allf)
    a['stats']=st
    a['last6']=[[f['date'].isoformat(),f['opp'],f['res'],short_m(f['meth']),f['rd'],f['tm'],short_ev(f['ev'])] for f in allf[:6]]
    if s in RANK:
        rr=[r for r in RANK[s] if r[0]==a['div'].replace(' Division','')] or RANK[s]
        a['rank']=('Champion' if rr[0][1]=='C' else rr[0][1])+' · '+rr[0][0]
    a['card']=s in card_slugs
    a['mirror']=mn
    F[s]=a
events=[]
for e in upcoming:
    bs=[]
    for b in e['bouts']:
        bs.append(dict(sec={'main-card':'Main card','prelims-card':'Prelims','early-prelims':'Early prelims'}.get(b['sec'],''),
            wc=b['wc'].replace(' Bout',''),a=b['names'][0],b=b['names'][1],sa=b['slugs'][0],sb=b['slugs'][1],ra=b['ranks'][0],rb=b['ranks'][1]))
    events.append(dict(title=e['title'],date=e['when'].strftime('%a %b %-d, %Y'),iso=e['when'].date().isoformat(),venue=e['venue'],
        times=e['times'],url=e['url'],bouts=bs))
# ---------------- ratings, odds, win probabilities, rankings, news ----------------
import ratings as RT
CUT=NOW.date().isoformat()
for s_,a in F.items():
    a['rating']=RT.fighter_rating2(s_,a.get('mirror'),CUT,a.get('rank'),rec=a.get('rec'))
import fit_overall as FO
FIT=FO.fit()   # v3: logistic on the displayed OVERALL gap (point-in-time, 2018+)
# consistency: a contender who lost his last UFC fight to the reigning champ of that division is capped just below the champ
CAPPED=[]
_last={}
for d_,a_,b_,ra,rb,S,na,nb in RT.E().hist:
    _last[a_]=(d_,b_,S); _last[b_]=(d_,a_,1-S)
for h,c,l in RLISTS:
    if 'Pound' in h or not c or not F.get(c) or not F[c].get('rating'): continue
    cm=F[c].get('mirror'); cov=F[c]['rating']['ov']
    for s_ in l:
        f=F.get(s_); r=f and f.get('rating')
        if not r: continue
        lt=_last.get(f.get('mirror'))
        if False and lt and lt[1]==cm and lt[2]==0 and r['ov']>cov-0.1:   # cap rule removed (v3)
            CAPPED.append((f['name'],r['ov'],round(cov-0.1,1))); r['ov_uncapped']=r['ov']; r['ov']=round(cov-0.1,1); r['capped']=1
print('CAPPED',CAPPED)
for s_,a in F.items():   # badge: prospect = <=4 UFC fights, pro win% >= 80%, winning UFC record
    r=a.get('rating')
    if not r: continue
    uw=sum(1 for x in a.get('last6',[]) if x[2]=='W'); ul=sum(1 for x in a.get('last6',[]) if x[2]=='L')
    if r['badge']=='prospect' and uw<=ul: r['badge']='small' if r['n']<3 else None
for s_,a in F.items():   # leg-kick rate (UFCStats per-round data) for the fun fight sim's kick weighting
    if a.get('mirror'):
        S_=RT.DR.raw_stats(a['mirror'],CUT)
        if S_.get('leg_min',0)>5: a['lk']=round(S_['leg']/S_['leg_min'],2)
def nk(n):
    t=[x for x in norm(n) if x not in ('jr','sr','ii','iii')]; return ' '.join(t)
ODDS={}  # from refresh_odds.py -> cache/odds.json (public BestFightOdds pages)
OJ=json.load(open(C+'odds.json')) if os.path.exists(C+'odds.json') else {'asof':None,'bouts':[]}
for o_ in OJ['bouts']:
    ODDS[(nk(o_['f1']['name']),nk(o_['f2']['name']))]=(o_['p1'],o_['n'],o_)
def market(a,b):
    A,B=nk(a),nk(b)
    for (x,y),v in ODDS.items():
        def same(p,q): return p==q or (set(p.split())&set(q.split()) and (p.split()[-1]==q.split()[-1] or p.split()[0]==q.split()[0]))
        if same(x,A) and same(y,B): return v[0],v[1],v[2],v[2]['f1'],v[2]['f2']
        if same(x,B) and same(y,A): return 1-v[0],v[1],v[2],v[2]['f2'],v[2]['f1']
    return None
OURS={}  # our v0.4.4 model output for a card, if the Wednesday routine has drafted one: events/<id>.v044.json
for fp in glob.glob(ROOT+'events/*.v044.json'):
    try: d_=json.load(open(fp))
    except Exception: continue
    for b in d_.get('bouts',[]):
        v=b.get('v044') or {}
        if v.get('pick') and v.get('conf'):
            OURS[frozenset((nk(b['a']),nk(b['b'])))]=(v['pick'],v['conf']/100,d_.get('event_date'))
for e in events:
    for b in e['bouts']:
        fa,fb=F.get(b['sa']),F.get(b['sb'])
        o=OURS.get(frozenset((nk(b['a']),nk(b['b']))))
        if o and o[2] and o[2]>=CUT:
            b['ours']=round(100*(o[1] if nk(o[0])==nk(b['a']) else 1-o[1]))
        if fa and fb and fa.get('rating') and fb.get('rating'):
            b['est']=round(100*RT.winprob(fa['rating']['ov'],fb['rating']['ov'],FIT['k']))
        mk=market(b['a'],b['b'])
        if mk:
            b['mkt']=round(100*mk[0]); b['mkt_books']=mk[1]; b['mkt_src']=mk[2]['url']
            b['odds']=[mk[3]['med'],mk[4]['med'],mk[3]['best'],mk[3]['book'],mk[4]['best'],mk[4]['book'],mk[1],mk[3].get('open'),mk[4].get('open'),round(100*mk[0],1)]
rankings=[dict(div=h,champ=c,list=l) for h,c,l in RLISTS]
NAME2SLUG={key(a['name']):s_ for s_,a in F.items()}
news=[]
for d_,h,cat,conf,names,url,src in json.load(open(HERE+'/news.json')):
    news.append(dict(date=d_,h=h,cat=cat,conf=conf,f=[NAME2SLUG.get(key(n)) or n for n in names],url=url,src=src))
out=dict(asof=NOW.strftime('%b %-d, %Y %-I:%M %p')+' CST',ts=int(NOW.timestamp()),odds_asof=OJ.get('asof'),mirror_end=MIRROR_END.isoformat(),
    sources=['UFC.com (events, rankings, athlete pages)','UFCStats.com (fight history and per-round stats; Greco1899 mirror to '+MIRROR_END.isoformat()+' + public event pages)'],
    events=events,fighters=F,gaps=gaps,rankings=rankings,news=news,fit=FIT)
json.dump(out,open(HERE+'/app-data.json','w'),default=str,ensure_ascii=False)
print(len(events),'events',sum(len(e['bouts']) for e in events),'bouts',len(F),'fighters',sum(1 for f in F.values() if f['card']),'card fighters')
for g in gaps: print('GAP',g)
