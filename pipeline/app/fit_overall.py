"""Point-in-time OVERALL rating for every UFC fight 2018+ and a logistic fit of P(win) on the overall gap.
Historical UFC rankings are not in the data, so the ranking part uses a proxy built only from information before each
fight: champion = winner of the most recent title bout in that weight class (vacated if they leave the class or are idle
2+ years); #1-#15 = pre-fight Elo order among fighters whose latest fight was in that class within the last 2 years;
others unranked (implied rank = min(7.2, PERF), as in the app). Pro-record prior unknown historically -> 5.5."""
import os, ratings as R, areas as AR, csv, datetime as dt, math, json, collections, random, re, sys, time
DR=R.DR; E=R.E(); M=R.ROOT+'sources/featherweight/ufcstats-mirror/'
def build_components():
    EVD={r['EVENT'].strip():dt.datetime.strptime(r['DATE'].strip(),'%B %d, %Y').date() for r in csv.DictReader(open(M+'ufc_event_details.csv'))}
    def wcn(w):
        w=w.replace('UFC ','').replace('Interim ','').replace(' Title','').replace(' Bout','').strip(); return w
    WC={}
    for r in csv.DictReader(open(M+'ufc_fight_results.csv')):
        d=EVD.get(r['EVENT'].strip());
        if not d: continue
        ns=[DR.resolve(n.strip()) or n.strip() for n in r['BOUT'].split(' vs. ')]
        WC[(d,frozenset(ns))]=(wcn(r['WEIGHTCLASS']),'Title' in r['WEIGHTCLASS'])
    def wc_of(d,a,b):
        x=WC.get((d,frozenset((a,b))))
        if x: return x
        for k in ((d,frozenset((a,b))),):pass
        return None
    # chronological pass (same updates as elo.Elo) with the rank proxy at each fight
    EL=R.EL; P=EL.P
    Rr={}; N={}; L={}; lastc={}; champ={}; RANKP={}
    def ranklist(W,d):
        key=(W,d)
        if key in RANKP: return RANKP[key]
        ch=champ.get(W)
        if ch and (lastc.get(ch)!=W or (d-L[ch]).days>730): champ.pop(W); ch=None
        cand=sorted(((EL.decay(Rr[n],L[n],d),n) for n in Rr if lastc.get(n)==W and (d-L[n]).days<=730 and n!=ch),reverse=True)
        RANKP[key]=(ch,{n:i+1 for i,(_,n) in enumerate(cand[:15])}); return RANKP[key]
    rows=[]; t0=time.time()
    for d,a,b,S,meth in EL.bouts():
        ra=EL.decay(Rr.get(a,P['DEBUT']),L.get(a),d); rb=EL.decay(Rr.get(b,P['DEBUT']),L.get(b),d)
        x=WC.get((d,frozenset((a,b))))
        W,title=x if x else (lastc.get(a) or lastc.get(b),False)
        if S is None:
            Rr[a]=ra;Rr[b]=rb;L[a]=L[b]=d
            if x: lastc[a]=lastc[b]=W
            continue
        na,nb=N.get(a,0),N.get(b,0)
        if d>=dt.date(2018,1,1) and S!=.5 and na>=1 and nb>=1 and W:
            ch,rk=ranklist(W,d); comp=[]
            for nm,r_,n in ((a,ra,na),(b,rb,nb)):
                q,pk=R.resume(nm,d); el=r_+R.V3['PEAK']*(pk-r_) if (pk is not None and pk>r_) else r_
                m=AR.model(d).score(nm)
                if m: sk=sum(R.W[k]*m['g'][k] for k in R.W)
                else:
                    ar,_,_=R.data_areas(nm,d)
                    if ar is None: comp=None;break
                    Sx=R.sos(nm,d); sk,_=R.groups({k:R.adj_area(v,Sx) for k,v in ar.items()})
                lab='Champion' if nm==ch else ('#%d'%rk[nm] if nm in rk else None)
                comp.append(dict(R=R.res10(el),sk=sk,n=n,lab=lab,bn=R.bonus10(q)*min(1,(n+1)/5)))
            if comp: rows.append(dict(d=str(d),a=a,b=b,y=1 if S==1 else 0,A=comp[0],B=comp[1]))
        e=1/(1+10**((rb-ra)/400)); mu=EL.mult(meth) if S!=.5 else 1.0
        ka=P['K']*(1+P['NEWK']/(na+1)); kb=P['K']*(1+P['NEWK']/(nb+1))
        Rr[a]=ra+ka*mu*(S-e); Rr[b]=rb-kb*mu*(S-e); N[a]=na+1; N[b]=nb+1; L[a]=L[b]=d
        if x:
            lastc[a]=lastc[b]=W
            if title and S in (0,1): champ[W]=a if S==1 else b
        else: lastc.setdefault(a,W); lastc.setdefault(b,W)
    print('rows',len(rows),round(time.time()-t0),'s',file=sys.stderr)
    json.dump(rows,open(CF,'w'))
    T=dt.date(2026,11,11); prox={}
    for W in set(lastc.values()):
        ch,rk=ranklist(W,T)
        if ch: prox[ch]='Champion'
        for n,i in rk.items(): prox[n]='#%d'%i
    json.dump(prox,open(HERE+'/rank_proxy_now.json','w'))
    return rows

HERE=os.path.dirname(os.path.abspath(__file__)); CF=HERE+'/winprob_hist_components.json'; FP=HERE+'/winprob_fit.json'
def ov_hist(c):
    """Displayed overall (1 dp) from point-in-time components, with the same functions the app uses (pro prior unknown -> 5.5)."""
    ur=c['lab'] is None
    pf=R.overall2(c['R'],c['sk'],None,c['n'])
    rk=min(R.UNRANKED_CAP,pf) if ur else R.rank10(c['lab'])
    ov=R.overall2(c['R'],c['sk'],None if ur else rk,c['n'],unranked=ur)
    return round(min(9.8,R.stretch(ov+c['bn'])),1)
sig=lambda z:1/(1+math.exp(-z))
def _fitk(xy): return min((sum(-math.log(max(1e-12,sig(k*x) if y else 1-sig(k*x))) for x,y in xy),k) for k in [i/100 for i in range(1,400)])[1]
def _met(xy,k):
    n=len(xy); dec=[(x,y) for x,y in xy if x!=0]; bins=[]
    for lo in (.5,.6,.7,.8,.9):
        sl=[(sig(k*abs(x)),(x>0)==bool(y)) for x,y in dec if lo<=sig(k*abs(x))<lo+.1]
        if sl: bins.append([lo,round(sum(p for p,_ in sl)/len(sl),3),round(sum(w for _,w in sl)/len(sl),3),len(sl)])
    return dict(k=k,n=n,logloss=round(sum(-math.log(max(1e-12,sig(k*x) if y else 1-sig(k*x))) for x,y in xy)/n,4),
                brier=round(sum((sig(k*x)-y)**2 for x,y in xy)/n,4),accuracy=round(sum((x>0)==bool(y) for x,y in dec)/len(dec),3),ties=n-len(dec),calibration=bins)
def fit(force=False):
    if os.path.exists(FP) and not force:
        j=json.load(open(FP))
        if j.get('version')==3: return j
    rows=json.load(open(CF)) if os.path.exists(CF) else build_components()
    xy=[(ov_hist(r['A'])-ov_hist(r['B']),r['y']) for r in rows]
    k=_fitk(xy); out=_met(xy,k)
    tr=[(x,y) for (x,y),r in zip(xy,rows) if r['d']<'2022']; te=[(x,y) for (x,y),r in zip(xy,rows) if r['d']>='2022']
    kt=_fitk(tr); ho=_met(te,kt)
    out.update(version=3,coinflip_logloss=round(math.log(2),4),range='2018-01-01..'+max(r['d'] for r in rows),
               holdout=dict(train='2018-2021',test='2022+',k=kt,n=ho['n'],logloss=ho['logloss'],brier=ho['brier'],accuracy=ho['accuracy']),
               weights=dict(R.W2),shrink_d=R.SHRINK_D,
               note='P(A) = 1/(1+exp(-k*(overall_A - overall_B))) on the displayed overall rating (1 dp), each computed before the fight; ranking part uses a point-in-time proxy (title-bout champion + Elo order in class)')
    json.dump(out,open(FP,'w'),indent=1); return out
if __name__=='__main__':
    import sys as _s
    if '--rebuild' in _s.argv: build_components()
    print(json.dumps(fit(force=True),indent=1))
