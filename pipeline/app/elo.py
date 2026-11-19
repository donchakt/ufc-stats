import os as _o; UFC_ROOT=_o.environ.get('UFC_ROOT') or _o.path.abspath(_o.path.join(_o.path.dirname(_o.path.abspath(__file__)),'..'))+'/'
"""Opponent-strength-adjusted results rating (Elo-style) over every UFC fight in the UFCStats mirror + Oct-2026 supplement
+ UFC.com results after the supplement (app-data cache). Chronological; each fight updates both fighters by
K_eff * mult * (S - E), E = 1/(1+10^((Ro-Rm)/400)).
  * K_eff = K * (1 + NEWK/(n_prev+1))  (moves faster for fighters with few UFC fights; Glicko-like uncertainty)
  * mult: KO/TKO or SUB finish 1.25, unanimous decision 1.0, split/majority decision 0.5, DQ 0.5; draws S=0.5; NC skipped
  * debut rating 1500; no contests count as activity only
  * inactivity decay: before a fight and at query time, R <- 1500 + (R-1500)*exp(-max(0,years_idle-IDLE0)/TAU)
Opponent strength propagates because every update uses both fighters' current ratings."""
import os,sys,json,math,datetime as dt
sys.path.insert(0,UFC_ROOT+'backtest/tools'); os.environ['UFC_NAME_SPLIT']='1'
import data_ratings as DR
HERE=os.path.dirname(os.path.abspath(__file__))
P=dict(K=64,NEWK=1.0,DEBUT=1500,IDLE0=0.75,TAU=2.5,FIN=1.25,SPLIT=0.5)
def mult(m):
    m=(m or '').lower()
    if 'ko' in m or 'sub' in m: return P['FIN']
    if 'split' in m or 'majority' in m or 's-dec' in m or 'm-dec' in m: return P['SPLIT']
    if 'dq' in m: return .5
    return 1.0
def bouts(extra=True):
    seen=set(); out=[]
    for me,fs in DR.FIGHTS.items():
        for f in fs:
            k=(f['date'],tuple(sorted([me,f['opp']])))
            if k in seen: continue
            seen.add(k)
            wl=f['wl'].strip()
            if wl not in ('W','L','D','NC'): continue
            out.append((f['date'],me,f['opp'],None if wl=='NC' else 1.0 if wl=='W' else 0.0 if wl=='L' else .5,f['method']))
    if extra:
        mx=max(b[0] for b in out); fp=HERE+'/app-data.json'
        if os.path.exists(fp):
            d=json.load(open(fp))
            for s,a in d['fighters'].items():
                me=a.get('mirror') or a['name']
                for x in a.get('last6',[]):
                    dd=dt.date.fromisoformat(x[0])
                    if dd<=mx or x[2] not in ('W','L','D','NC'): continue
                    op=DR.resolve(x[1]) or x[1]
                    k=(dd,tuple(sorted([me,op])))
                    if k in seen: continue
                    seen.add(k); out.append((dd,me,op,None if x[2]=='NC' else 1.0 if x[2]=='W' else 0.0 if x[2]=='L' else .5,x[3]))
    out.sort(key=lambda b:(b[0],b[1]))
    return out
def decay(r,last,when):
    if last is None: return r
    y=(when-last).days/365.25
    return 1500+(r-1500)*math.exp(-max(0,y-P['IDLE0'])/P['TAU'])
class Elo:
    def __init__(s,B=None,**kw):
        P.update(kw); s.R={}; s.N={}; s.L={}; s.hist=[]  # hist: (date,a,b,Ra_pre,Rb_pre,S)
        for d,a,b,S,m in (B if B is not None else bouts()):
            ra=decay(s.R.get(a,P['DEBUT']),s.L.get(a),d); rb=decay(s.R.get(b,P['DEBUT']),s.L.get(b),d)
            if S is None:  # no contest: counts as activity only
                s.R[a]=ra; s.R[b]=rb; s.L[a]=d; s.L[b]=d; continue
            s.hist.append((d,a,b,ra,rb,S,s.N.get(a,0),s.N.get(b,0)))
            e=1/(1+10**((rb-ra)/400)); mu=mult(m) if S!=.5 else 1.0
            ka=P['K']*(1+P['NEWK']/(s.N.get(a,0)+1)); kb=P['K']*(1+P['NEWK']/(s.N.get(b,0)+1))
            s.R[a]=ra+ka*mu*(S-e); s.R[b]=rb-kb*mu*(S-e)
            s.N[a]=s.N.get(a,0)+1; s.N[b]=s.N.get(b,0)+1; s.L[a]=d; s.L[b]=d
    def now(s,name,when):
        if name not in s.R: return None
        return decay(s.R[name],s.L[name],when)
def tune():
    B=bouts(); best=None
    for K in (32,40,48,56,64):
        for NK in (0.5,1.0,2.0):
            for DEB in (1400,1450,1500):
                for TAU in (3.0,5.0):
                    e=Elo(B,K=K,NEWK=NK,DEBUT=DEB,TAU=TAU); ll=0;n=0
                    for d,a,b,ra,rb,S,na,nb in e.hist:
                        if d.year<2015 or S==.5: continue
                        p=1/(1+10**((rb-ra)/400)); p=min(max(p,1e-6),1-1e-6)
                        ll+=-math.log(p if S==1 else 1-p); n+=1
                    r=(ll/n,K,NK,DEB,TAU)
                    if best is None or r<best: best=r
    return best
if __name__=='__main__':
    print(tune())
