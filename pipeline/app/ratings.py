import os as _o; UFC_ROOT=_o.environ.get('UFC_ROOT') or _o.path.abspath(_o.path.join(_o.path.dirname(_o.path.abspath(__file__)),'..'))+'/'
"""Ratings v3: v2 (Elo + SoS + rank blend) plus pro-record prior for thin samples, implied rank for unranked fighters (cap 7.2), resume bonus for wins over elite pre-fight Elo with recency decay, 25% recent-peak Elo blend, champion-cap rule removed, overall cap 9.8."""
"""Overall fighter rating (1-10) for the UFC Stats app, v2 (2026-11-10): connected to results, opposition and rankings.
  RES   results rating: opponent-adjusted Elo over every UFC fight (elo.py: finishes x1.25, split/majority x0.5,
        faster moves for new fighters, inactivity decay), mapped RES = 1 + 9/(1+exp(-(Elo-1550)/130)).
  SKILL skill-area composite: area scores (analyst table where present, else data_ratings percentiles 60% career /
        40% last 4) adjusted for strength of schedule: SoS = recency-weighted (0.8^i) mean pre-fight Elo of the last 6
        UFC opponents; area' = 5.5 + (area-5.5)*m + (SoS-1500)/400, m = clip(1+(SoS-1500)/600, .6, 1.3), clipped 1-10
        (stats piled up against strong opposition are stretched and lifted; stats padded against weak opposition shrink).
        SKILL = .25 Striking + .15 Wrestling + .15 Grappling + .25 Defence + .20 Cardio/Durability (adjusted areas).
  RANK  official UFC ranking (best division, from UFC.com): champion 10, #1 9.3 ... #15 7.5 (linear), unranked 5.0.
  PERF  = prior + shrink*((.40*RES + .30*SKILL)/.70 - prior), shrink = min(1,(n+1)/3), n = UFC fights (v5; was .50/.20 and /5).
  Overall = .70*PERF + .30*RANK   (= .40 RES + .30 SKILL + .30 RANK for fighters with 2+ UFC fights).
  Consistency rule: a ranked contender whose most recent UFC fight was a loss to his division's current champion is
  capped at champion - 0.1.
Win probability (stats estimate, v3): P(A) = 1/(1+exp(-k*(OVERALL_A-OVERALL_B))) on the displayed overall, computed strictly
  before each fight with a point-in-time ranking proxy; k by max likelihood on UFC fights 2018-01-01 onward (fit_overall.py)."""
import os,sys,re,json,math,random,datetime as dt
sys.path.insert(0,UFC_ROOT+'backtest/tools')
os.environ['UFC_NAME_SPLIT']='1'
import data_ratings as DR
HERE=os.path.dirname(os.path.abspath(__file__)); ROOT=UFC_ROOT+''
DATA_ROWS={'so':'Striking offence','sd':'Striking defence','wo':'Wrestling offence','tdd':'TD defence','sub':'Submission offence',
           'cardio':'Cardio (proxy)','dur':'Durability (proxy)'}
W=dict(STR=.25,WRE=.15,GRA=.15,DEF=.25,CDU=.20)
def _akey(n):
    n=n.lower()
    for pre,k in (('striking offence','so'),('striking defence','sd'),('wrestling offence','wo'),('takedown defence','tdd'),('td defence','tdd'),
                  ('submission offence','sub'),('sub offence','sub'),('submission defence','subd'),('sub defence','subd'),('cardio','cardio'),
                  ('durability','dur'),('top control','top'),('getting back up','getup'),('get-ups','getup'),('scrambles','scr')):
        if n.startswith(pre): return k
def analyst(slug):
    p=ROOT+'fighters/'+slug+'.md'
    if not os.path.exists(p): return {}
    t=open(p).read(); m=re.search(r'## Technical scores \(1-10\)(.*?)(\n## |\Z)',t,re.S)
    if not m: return {}
    out={}
    for n,v in re.findall(r'^\|\s*([^|]+?)\s*\|\s*([0-9]+(?:\.[0-9]+)?)\s*\|',m.group(1),re.M):
        k=_akey(n)
        if k and k not in out: out[k]=float(v)
    return out
def _rate_recent(m,cutoff,last=4):
    cut=dt.date.fromisoformat(cutoff) if isinstance(cutoff,str) else cutoff
    allf=DR.FIGHTS.get(m,[]); prior=sorted([f for f in allf if f['date']<cut],key=lambda f:f['date'])
    if len(prior)<=last: return None
    DR.FIGHTS[m]=prior[-last:]
    try: return DR.rate(m,cutoff,resolve_name=False)
    finally: DR.FIGHTS[m]=allf
def data_areas(mirror,cutoff):
    if not mirror: return None,0,[]
    r=DR.rate(mirror,cutoff,resolve_name=False)
    if r['n']==0: return None,0,r['flags']
    rr=_rate_recent(mirror,cutoff)
    a={}
    for k,row in DATA_ROWS.items():
        p=r['pct'][row]
        if rr: p=.6*p+.4*rr['pct'][row]
        a[k]=1+9*p
    return a,r['n'],r['flags']
def groups(a):
    g=lambda ks:[a[k] for k in ks if k in a]
    mean=lambda xs:sum(xs)/len(xs) if xs else None
    G=dict(STR=mean(g(['so'])),WRE=mean(g(['wo','top'])),GRA=mean(g(['sub','subd','scr'])),DEF=mean(g(['sd','tdd','getup'])),CDU=mean(g(['cardio','dur'])))
    if any(v is None for v in G.values()): return None,None
    ov=sum(W[k]*G[k] for k in W)
    return round(ov,1),{k:round(v,1) for k,v in G.items()}
def fighter_rating(slug,mirror,cutoff):
    a,n,flags=data_areas(mirror,cutoff)
    an=analyst(slug)
    if a is None and not an: return None
    a=dict(a or {}); src='data'
    if an: a.update(an); src='analyst+data' if n else 'analyst'
    ov,G=groups(a)
    if ov is None: return None
    return dict(ov=ov,g=G,n=n,thin=n<3,src=src)
def fit_k(force=False):
    fp=HERE+'/winprob_fit.json'
    if os.path.exists(fp) and not force: return json.load(open(fp))
    import prefight_profile as PP
    random.seed(7); rows=[]
    for r in PP.RES:
        e=r['EVENT'].strip(); d=PP.EVD.get(e)
        if d is None or d<dt.date(2018,1,1): continue
        ab=[x.strip() for x in r['BOUT'].split(' vs. ')]; oc=r['OUTCOME'].strip()
        if len(ab)!=2 or oc not in ('W/L','L/W'): continue
        win=ab[0] if oc=='W/L' else ab[1]
        oa=[];ok=True
        for nm in ab:
            a,n,_=data_areas(nm,d)
            if a is None or n<1: ok=False;break
            oa.append(groups(a)[0])
        if not ok: continue
        if random.random()<.5: ab=ab[::-1]; oa=oa[::-1]
        rows.append((oa[0]-oa[1],1 if win==ab[0] else 0,d.year))
    def ll(k): return sum(-math.log(1/(1+math.exp(-k*x))) if y else -math.log(1-1/(1+math.exp(-k*x))) for x,y,_ in rows)
    best=min((ll(k/100),k/100) for k in range(1,301))
    k=best[1]; acc=sum(1 for x,y,_ in rows if x!=0 and (x>0)==bool(y))/max(1,sum(1 for x,_,_ in rows if x!=0))
    out=dict(k=k,n=len(rows),logloss=round(best[0]/len(rows),4),coinflip_logloss=round(math.log(2),4),accuracy=round(acc,3),
             range='2018-01-01..'+str(max(PP.EVD.values())),note='ratings computed strictly before each fight date')
    json.dump(out,open(fp,'w'),indent=1); return out
def winprob(ova,ovb,k): return 1/(1+math.exp(-k*(ova-ovb)))
if __name__=='__main__':
    print(fit_k(force='--force' in sys.argv))
    print(fighter_rating('ciryl-gane','Ciryl Gane','2026-11-11'))
    print(fighter_rating('alexander-volkanovski','Alexander Volkanovski','2026-11-11'))

# ======================= v2: connected rating =======================
import elo as EL
_E=None
def E():
    global _E
    if _E is None: _E=EL.Elo()
    return _E
def _opp_hist():
    H={}
    for d,a,b,ra,rb,S,na,nb in E().hist:
        H.setdefault(a,[]).append((d,rb)); H.setdefault(b,[]).append((d,ra))
    return H
_H=None
def sos(name,cutoff):
    global _H
    if _H is None: _H=_opp_hist()
    cut=dt.date.fromisoformat(cutoff) if isinstance(cutoff,str) else cutoff
    xs=[r for d,r in sorted(_H.get(name,[])) if d<cut][-6:][::-1]
    if not xs: return None
    w=[.8**i for i in range(len(xs))]
    return sum(a*b for a,b in zip(w,xs))/sum(w)
def elo_at(name,cutoff):
    cut=dt.date.fromisoformat(cutoff) if isinstance(cutoff,str) else cutoff
    e=E()
    if cut>max(h[0] for h in e.hist): return e.now(name,cut)
    # pre-fight value: last update before cut
    last=None
    for d,a,b,ra,rb,S,na,nb in _byname().get(name,[]):
        if d>=cut: break
        last=(d,a,b,ra,rb,S,na,nb)
    if last is None: return None
    return None  # (historical values are taken from hist directly in fit_k2)
_BN=None
def _byname():
    global _BN
    if _BN is None:
        _BN={}
        for h in E().hist: _BN.setdefault(h[1],[]).append(h); _BN.setdefault(h[2],[]).append(h)
    return _BN
def res10(elo): return 1+9/(1+math.exp(-(elo-1550)/130))
def adj_area(v,S):
    if S is None: return v
    m=min(1.3,max(.6,1+(S-1500)/600))
    return min(10,max(1,5.5+(v-5.5)*m+(S-1500)/400))
def rank10(rank_label):
    if not rank_label: return 5.0
    if rank_label.startswith('Champion'): return 10.0
    mm=re.match(r'#(\d+)',rank_label)
    return 9.3-(int(mm.group(1))-1)*1.8/14 if mm else 5.0
W2=dict(RES=.40,SKILL=.30,RANK=.30)   # v5 2026-11-10: tuned on pre-2022 fights, better on 2022+ held-out (fit_overall.py)
SHRINK_D=3   # perf shrink toward the prior = min(1,(n+1)/SHRINK_D); was 5
def pro_prior(rec):
    """Light prior for thin UFC samples from the pro record 'W-L-D': 5.5 + 3*(win% - .70), +0.3 if unbeaten, clipped 4.5-6.8."""
    try: w,l,*_=[int(x) for x in str(rec).split('-')]
    except Exception: return 5.5
    if w+l==0: return 5.5
    return max(4.5,min(6.8,5.5+3*(w/(w+l)-.70)+(.3 if l==0 and w>=5 else 0)))
UNRANKED_CAP=7.2   # an unranked fighter's ranking component never reaches #15's 7.5
def overall2(res,skill,rank,n,prior=5.5,unranked=False):
    sh=min(1,(n+1)/SHRINK_D)
    base=(W2['RES']*res+W2['SKILL']*skill)/(W2['RES']+W2['SKILL'])
    perf=prior+sh*(base-prior)
    if rank is None and not unranked: return perf
    if unranked: rank=min(UNRANKED_CAP,perf)   # implied by own results instead of a flat 5.0
    return (W2['RES']+W2['SKILL'])*perf+W2['RANK']*rank
_QC={}
def resume(mirror,cutoff):
    """Quality-of-wins Q: sum over UFC wins of max(0,(opp pre-fight Elo-1600)/100), decayed with 8-yr e-folding;
    and recent peak Elo = max pre-fight Elo in the last 4 years (or now)."""
    T=dt.date.fromisoformat(cutoff) if isinstance(cutoff,str) else cutoff
    key=(mirror,T)
    if key in _QC: return _QC[key]
    q=0.0; pk=None
    for d,a,b,ra,rb,S,na,nb in E().hist:
        if d>=T or mirror not in (a,b): continue
        me,op,s_=(ra,rb,S) if a==mirror else (rb,ra,1-S)
        if s_==1: q+=max(0,(op-1600)/100)*math.exp(-((T-d).days/365.25)/8)
        if (T-d).days<=4*365.25: pk=me if pk is None else max(pk,me)
    _QC[key]=(q,pk); return q,pk
V3=dict(PEAK=0.25,BMAX=0.6,BQ=6,S0=8.5,SF=1.0)
def bonus10(q): return V3['BMAX']*(1-math.exp(-q/V3['BQ']))
def stretch(ov): return ov if ov<=V3['S0'] else V3['S0']+(ov-V3['S0'])*V3['SF']
def fighter_rating2(slug,mirror,cutoff,rank_label=None,n_ufc=None,rec=None):
    """Current rating. rank_label like 'Champion · X' / '#4 · X' / None."""
    a,n,flags=data_areas(mirror,cutoff) if mirror else (None,0,[])
    an=analyst(slug)
    el=E().now(mirror,dt.date.fromisoformat(cutoff) if isinstance(cutoff,str) else cutoff) if mirror else None
    if a is None and not an and el is None: return None
    n=E().N.get(mirror,0) if mirror else 0
    if n==0 and not an: return None
    S=sos(mirror,cutoff) if mirror else None
    a=dict(a or {}); src='data'
    if an: a.update(an); src='analyst+data' if n else 'analyst'
    import areas as AR
    ar=AR.model(cutoff).score(mirror) if (mirror and n>0) else None
    if ar:   # v4 areas: opponent-adjusted, recency-weighted, smooth 1-9.9 scale (areas.py)
        G=ar['g']; SUB=ar['sub']
        if an and n<3:   # thin data: lean on the analyst table too
            a2={k:adj_area(v,S) for k,v in a.items()}; _,Ga=groups(a2)
            if Ga: G={k:round(.5*G[k]+.5*min(9.9,Ga[k]),1) for k in G}
        sk=sum(W[k]*G[k] for k in W)
    else:
        a2={k:adj_area(v,S) for k,v in a.items()}
        sk,G=groups(a2); SUB=None
        if sk is None: return None
        G={k:min(9.9,v) for k,v in G.items()}
    q,pk=resume(mirror,cutoff) if mirror else (0,None)
    el_eff=el+V3['PEAK']*(pk-el) if (el is not None and pk is not None and pk>el) else el   # one loss costs a little, not a lot
    R=res10(el_eff if el_eff is not None else 1500)
    pr=pro_prior(rec) if n<5 else 5.5
    ur=not rank_label
    pf=overall2(R,sk,None,n,pr)
    rk=min(UNRANKED_CAP,pf) if ur else rank10(rank_label)
    ov=overall2(R,sk,None if ur else rk,n,pr,unranked=ur)
    bn=bonus10(q)*min(1,(n+1)/5)
    ov=min(9.8,stretch(ov+bn))
    try: w_,l_=[int(x) for x in str(rec).split('-')[:2]]
    except Exception: w_,l_=0,0
    badge='prospect' if n<=4 and w_+l_>0 and w_/(w_+l_)>=.8 else ('small' if n<3 else None)
    return dict(ov=round(ov,1),perf=round(pf,2),g=G,sub=SUB,n=n,thin=n<3,src=src,elo=round(el) if el is not None else None,res=round(R,1),skill=round(sk,1),
                rank=round(rk,1),rank_implied=ur,badge=badge,resume_q=round(q,2),bonus=round(bn,2),elo_peak4=round(pk) if pk else None,prior=round(pr,2),sos=round(S) if S else None)
def fit_k2(force=False):
    fp=HERE+'/winprob_fit.json'
    if os.path.exists(fp) and not force:
        j=json.load(open(fp))
        if j.get('version')==2: return j
    random.seed(7); rows=[]; e=E()
    for d,a,b,ra,rb,S,na,nb in e.hist:
        if d<dt.date(2018,1,1) or S==.5 or na<1 or nb<1: continue
        pre=[]
        for nm,r,n in ((a,ra,na),(b,rb,nb)):
            ar,_,_=data_areas(nm,d)
            if ar is None: pre=None;break
            Sx=sos(nm,d); sk,_=groups({k:adj_area(v,Sx) for k,v in ar.items()})
            pre.append(overall2(res10(r),sk,None,n))
        if not pre: continue
        y=1 if S==1 else 0
        if random.random()<.5: pre=pre[::-1]; y=1-y
        rows.append((pre[0]-pre[1],y,d,a if y==1 else b,b if y==1 else a))
    def ll(k): return sum(-math.log(1/(1+math.exp(-k*x))) if y else -math.log(1-1/(1+math.exp(-k*x))) for x,y,*_ in rows)
    best=min((ll(k/100),k/100) for k in range(1,301))
    k=best[1]; dec=[(x,y) for x,y,*_ in rows if x!=0]
    acc=sum(1 for x,y in dec if (x>0)==bool(y))/len(dec)
    # calibration bins
    bins=[]
    for lo in (.5,.6,.7,.8):
        sel=[(1/(1+math.exp(-k*abs(x))),(x>0)==bool(y)) for x,y in dec if lo<=1/(1+math.exp(-k*abs(x)))<lo+.1]
        if sel: bins.append([lo,round(sum(p for p,_ in sel)/len(sel),3),round(sum(w for _,w in sel)/len(sel),3),len(sel)])
    out=dict(version=2,k=k,n=len(rows),logloss=round(best[0]/len(rows),4),coinflip_logloss=round(math.log(2),4),accuracy=round(acc,3),
             calibration=bins,range='2018-01-01..'+str(max(r[2] for r in rows)),note='pre-fight ratings without the ranking part')
    json.dump(out,open(fp,'w'),indent=1)
    json.dump([[str(r[2]),r[3],r[4],round(r[0] if r[1] else -r[0],3)] for r in rows],open(HERE+'/winprob_rows.json','w'))
    return out
