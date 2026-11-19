"""Historical check for the Parlay builder (run by hand when the model changes; output parlay_calib.json is committed and
embedded in the app; the parlays themselves are recomputed in the page from each data refresh).
Joins point-in-time stats estimates (winprob_hist_components.json, UFC fights 2018+, inputs strictly pre-fight) with public
vig-free closing odds (sources/parlay-hist.csv, from the analyst's hindsight-upsets study dataset, 6,747 bouts 2010-2026).
Applies the SAME leg rule as the app (LEG below), buckets eligible legs by blended-probability band, model/market agreement
and risk flags, and reports actual win rates on 2022+ fights (the leg rule's weights/penalties were set by hand, not fitted;
the rating->probability slope k was fitted on 2018+, so 2022+ is not perfectly untouched). Also replays 'top 3 / top 4 legs
per card' on 2022+ cards. Historical rates only - not a guarantee."""
import os,csv,json,math,collections,datetime as dt
import fit_overall as FO
HERE=os.path.dirname(os.path.abspath(__file__)); ROOT=os.path.abspath(HERE+'/..')+'/'
LEG=dict(w_model=0.4,layoff_days=730,pen_layoff=0.06,pen_layoff_opp=0.02,thin_n=2,pen_thin=0.04,pen_thin_opp=0.02,gap_free=0.15,pen_gap=0.5,tight=0.10)
BANDS=[(0.5,0.6,'50-60%'),(0.6,0.7,'60-70%'),(0.7,0.8,'70-80%'),(0.8,1.01,'80%+')]
def band(p): return next(l for lo,hi,l in BANDS if lo<=p<hi)
def leg(pS,pM,lay_me,lay_op,n_me,n_op):
    if not (pS>0.5 and pM>0.5): return None
    L=LEG; bl=L['w_model']*pS+(1-L['w_model'])*pM; gap=abs(pS-pM); pen=0; fl=[]
    if lay_me is not None and lay_me>=L['layoff_days']: pen+=L['pen_layoff']; fl.append('layoff')
    if lay_op is not None and lay_op>=L['layoff_days']: pen+=L['pen_layoff_opp']; fl.append('opp_layoff')
    if n_me is not None and n_me<L['thin_n']: pen+=L['pen_thin']; fl.append('thin')
    if n_op is not None and n_op<L['thin_n']: pen+=L['pen_thin_opp']; fl.append('opp_thin')
    if gap>L['gap_free']: pen+=(gap-L['gap_free'])*L['pen_gap']; fl.append('gap')
    return dict(bl=bl,adj=bl-pen,gap=gap,flags=fl,agree='tight' if gap<L['tight'] else 'loose',risk=any(f in fl for f in ('layoff','thin','opp_layoff','opp_thin')))
FIT=FO.fit(); k=FIT['k']
comp=json.load(open(HERE+'/winprob_hist_components.json'))
EST={}
for r in comp:
    x=FO.ov_hist(r['A'])-FO.ov_hist(r['B']); EST[(r['d'],frozenset((r['a'],r['b'])))]=(r['a'],1/(1+math.exp(-k*x)))
legs=[]; joined=0
for r in csv.DictReader(open(ROOT+'sources/parlay-hist.csv')):
    d=r['date'][:10]; key=frozenset((r['fav'],r['dog']))
    e=None
    for dd in (d,(dt.date.fromisoformat(d)-dt.timedelta(days=1)).isoformat(),(dt.date.fromisoformat(d)+dt.timedelta(days=1)).isoformat()):
        e=EST.get((dd,key))
        if e: break
    if not e: continue
    joined+=1
    pfS=e[1] if e[0]==r['fav'] else 1-e[1]; pfM=float(r['p_fav']); yf=int(r['fav_won'])
    f=lambda c:float(r[c]) if r[c] not in ('','nan','None') else None
    for pick,pS,pM,y,lm,lo,nm,no in ((r['fav'],pfS,pfM,yf,f('F_layoff'),f('G_layoff'),f('F_n'),f('G_n')),(r['dog'],1-pfS,1-pfM,1-yf,f('G_layoff'),f('F_layoff'),f('G_n'),f('F_n'))):
        L=leg(pS,pM,lm,lo,nm,no)
        if L: L.update(date=d,y=y,five=r['five']=='1',pick=pick); legs.append(L)
def rate(sub):
    n=len(sub); w=sum(x['y'] for x in sub); return dict(n=n,won=w,rate=round(w/n,3) if n else None,pred=round(sum(x['adj'] for x in sub)/n,3) if n else None)
oos=[x for x in legs if x['date']>='2022-01-01']; ins=[x for x in legs if x['date']<'2022-01-01']
B=collections.defaultdict(list)
for x in oos:
    b=band(x['bl']); B[b].append(x); B[b+'|'+x['agree']].append(x); B[b+'|'+x['agree']+'|'+('risk' if x['risk'] else 'clean')].append(x)
    if x['five']: B[b+'|five'].append(x)
buckets={kk:rate(v) for kk,v in sorted(B.items())}
# parlay replay on 2022+ cards: top-k legs by adjusted probability per card date
cards=collections.defaultdict(list)
for x in oos: cards[x['date']].append(x)
par={}
for kk in (3,4):
    hits=n=0; pred=[]
    for d,L in cards.items():
        if len(L)<kk: continue
        top=sorted(L,key=lambda x:-x['adj'])[:kk]; n+=1; hits+=all(x['y'] for x in top); pred.append(math.prod(x['adj'] for x in top))
    par[str(kk)]=dict(cards=n,hit=hits,rate=round(hits/n,3) if n else None,pred=round(sum(pred)/len(pred),3) if pred else None)
out=dict(version=1,leg=LEG,k=k,bands=[l for _,_,l in BANDS],joined=joined,legs_all=len(legs),legs_oos=len(oos),
    period_oos='2022-01-01..'+max(x['date'] for x in oos),period_in='2018-01-01..2021-12-31',
    in_sample={b:rate([x for x in ins if band(x['bl'])==b]) for _,_,b in BANDS},buckets=buckets,parlays=par,
    note='Win rates of legs passing the app rule (stats estimate and vig-free closing market agree) on UFC fights since 2022. Historical rates, not guarantees; correlation between legs ignored.')
json.dump(out,open(HERE+'/parlay_calib.json','w'),indent=1)
print(json.dumps({kk:v for kk,v in out.items() if kk!='buckets'},indent=1))
for kk,v in buckets.items(): print(kk,v)
