import os as _o; UFC_ROOT=_o.environ.get('UFC_ROOT') or _o.path.abspath(_o.path.join(_o.path.dirname(_o.path.abspath(__file__)),'..','..'))+'/'
"""Data-based 1-10 ratings from public UFCStats career stats (RATINGS-SCALE v1, 2026-11-01).
Doc: backtest/v05-study/RATINGS-SCALE.md.  Run from /workspace/ufc-analyst with UFC_NAME_SPLIT=1 (forced below).

Deterministic: same mirror + supplement + cutoff -> same scores. Cut-points (population distributions) are frozen in
backtest/tools/data_ratings_scale_v1.json the first time `build-scale` runs and are then only read, never refit silently.

Usage:
  python3 backtest/tools/data_ratings.py build-scale [--force]  # (re)build frozen population cut-points (cutoff 2026-11-01)
  python3 backtest/tools/data_ratings.py rate YYYY-MM-DD "Name" ...   # ratings using fights strictly before the date
  python3 backtest/tools/data_ratings.py snapshot events/<card>.json  # freeze pre-fight ratings -> events/<card>.ratings-snapshot.json
  python3 backtest/tools/data_ratings.py build-scale-lk   # (once) freeze the v1.1 leg-kick extension -> data_ratings_scale_v1_1_legkick.json
v1.1 (2026-11-01): adds 'Leg-kick offence' and 'Leg-kick defence' rows (flag LEGKICK-THIN under 3 fights with per-round data).
Library: rate(name, cutoff) -> dict(scores, flags, stats, n)."""
import os,sys,csv,json,math,bisect,hashlib,datetime as dt
os.environ['UFC_NAME_SPLIT']='1'
sys.path.insert(0,os.path.dirname(os.path.abspath(__file__)))
import prefight_profile as PP
import style_tags as STG
ROOT=UFC_ROOT+''
SUPP=ROOT+'sources/ufcstats-supplement/event-pages-2026-10.csv'
SCALE=os.path.join(os.path.dirname(os.path.abspath(__file__)),'data_ratings_scale_v1.json')
SCALE_CUTOFF='2026-11-01'
THIN_N=3
# smoothing priors (empirical-Bayes: add k pseudo-observations at the population mean)
K_ACC=100; K_STRDEF=100; K_TDACC=8; K_TDD=8; M0=15.0; K_KOL=3; K_LEGSH=60
FIGHTS={}
ROWS=['Striking offence','Striking defence','Wrestling offence','TD defence','Submission offence','Cardio (proxy)','Durability (proxy)',
      'Leg-kick offence','Leg-kick defence']   # last two added in RATINGS-SCALE v1.1 (2026-11-01)
SCALE_LK=os.path.join(os.path.dirname(os.path.abspath(__file__)),'data_ratings_scale_v1_1_legkick.json')

def _sec(s): return PP.sec(s)
def _of(s): return PP.of(s)
# dataset/profile spelling -> UFCStats spelling (checked by hand against the mirror, 2026-11-01)
EXTRA_ALIAS={"ode' osbourne":'Ode Osbourne','zachary reese':'Zach Reese','joseph kropschot':'Joe Kropschot',
  'eric mcconico jr.':'Eric McConico','stanley dorsainvil':'Stan Dorsainvil','wesley schultz':'Wes Schultz',
  'yoo joo-sang':'JooSang Yoo','eduardo henrique':'Eduardo Chapolin','osman diaz':'Ozzy Diaz',
  'matthieu letho duclos':'Matthieu Duclos','nina nikolija milošević':'Nina Milosevic','nina nikolija milosevic':'Nina Milosevic'}
def resolve(n):
    n2=EXTRA_ALIAS.get(n.lower().strip(),n)
    if n2 in FIGHTS: return n2
    return STG.fix(n2) or STG.fix(n2.replace('Zachary','Zach')) or STG.fix(n2.replace('Joseph','Joe')) or None

# ---------- per-fighter fight index ----------
def _add(name,f): FIGHTS.setdefault(name,[]).append(f)
def _build():
    for r in PP.RES:
        e=r['EVENT'].strip(); d=PP.EVD.get(e)
        if d is None: continue
        ab=[x.strip() for x in r['BOUT'].split(' vs. ')]
        if len(ab)!=2: continue
        rows=PP.STX.get((e,r['BOUT'].strip()),[])
        rnd=int(r['ROUND'] or 1); last=_sec(r['TIME']); mins=((rnd-1)*300+last)/60
        o=r['OUTCOME'].split('/')
        for i,(me,op) in enumerate(((ab[0],ab[1]),(ab[1],ab[0]))):
            per={}
            for s in rows:
                rn=int((s['ROUND'] or 'Round 0').split()[-1] or 0)
                who=s['FIGHTER'].strip()
                if who not in (me,op): continue
                side='me' if who==me else 'op'
                d0=per.setdefault(rn,{'me':dict(kd=0,sl=0,sa=0,td=0,tda=0,sub=0,leg=0),'op':dict(kd=0,sl=0,sa=0,td=0,tda=0,sub=0,leg=0)})[side]
                d0['kd']+=int(float(s['KD'] or 0)); x=_of(s['SIG.STR.']); d0['sl']+=x[0]; d0['sa']+=x[1]
                x=_of(s['TD']); d0['td']+=x[0]; d0['tda']+=x[1]; d0['sub']+=int(float(s['SUB.ATT'] or 0))
                d0['leg']+=_of(s.get('LEG') or '0 of 0')[0]
            wl=o[i] if len(o)==2 else '?'
            _add(me,dict(date=d,opp=op,wl=wl,method=r['METHOD'].strip(),round=rnd,last_sec=last,mins=mins,per=per,attempts=True))
    _mend=max(PP.EVD.values())   # pipeline: supplement only for events the UFCStats mirror does not cover yet (no double counting)
    for r in csv.DictReader(open(SUPP)):
        d=dt.date.fromisoformat(r['date'])
        if d<=_mend: continue
        rnd=int(r['round']); last=_sec(r['time']); mins=((rnd-1)*300+last)/60
        for me,op,a,b in ((r['winner'],r['loser'],'w','l'),(r['loser'],r['winner'],'l','w')):
            m=resolve(me) or me; opn=resolve(op) or op
            tot={'me':dict(kd=int(r[a+'_kd']),sl=int(r[a+'_sl']),sa=0,td=int(r[a+'_td']),tda=0,sub=int(r[a+'_sub'])),
                 'op':dict(kd=int(r[b+'_kd']),sl=int(r[b+'_sl']),sa=0,td=int(r[b+'_td']),tda=0,sub=int(r[b+'_sub']))}
            _add(m,dict(date=d,opp=opn,wl='W' if a=='w' else 'L',method=r['method'],round=rnd,last_sec=last,mins=mins,per={0:tot},attempts=False))
_build()

def raw_stats(name,cutoff):
    """Pooled career numbers from UFC fights strictly before cutoff."""
    cutoff=dt.date.fromisoformat(cutoff) if isinstance(cutoff,str) else cutoff
    fs=[f for f in FIGHTS.get(name,[]) if f['date']<cutoff]
    S=dict(n=len(fs),mins=0.0,sl=0,kd=0,td=0,sub=0,osl=0,okd=0,otd=0,
           sl_a=0,sa_a=0,osl_a=0,osa_a=0,td_a=0,tda_a=0,otd_a=0,otda_a=0,kol=0,
           early_sl=0,early_min=0.0,late_sl=0,late_min=0.0,late_fights=0,last=None,
           leg=0,oleg=0,leg_min=0.0,leg_sl=0,leg_osl=0,leg_fights=0)
    for f in fs:
        S['mins']+=f['mins']; S['kol']+=int(f['wl']=='L' and 'KO' in f['method'])
        tot={'me':dict(kd=0,sl=0,sa=0,td=0,tda=0,sub=0,leg=0),'op':dict(kd=0,sl=0,sa=0,td=0,tda=0,sub=0,leg=0)}
        for rn,pr in f['per'].items():
            for side in ('me','op'):
                for k,v in pr[side].items(): tot[side][k]+=v
        S['sl']+=tot['me']['sl']; S['kd']+=tot['me']['kd']; S['td']+=tot['me']['td']; S['sub']+=tot['me']['sub']
        S['osl']+=tot['op']['sl']; S['okd']+=tot['op']['kd']; S['otd']+=tot['op']['td']
        if f['attempts']:
            S['sl_a']+=tot['me']['sl']; S['sa_a']+=tot['me']['sa']; S['osl_a']+=tot['op']['sl']; S['osa_a']+=tot['op']['sa']
            S['td_a']+=tot['me']['td']; S['tda_a']+=tot['me']['tda']; S['otd_a']+=tot['op']['td']; S['otda_a']+=tot['op']['tda']
            # leg strikes (v1.1, 2026-11-01): only fights with per-round UFCStats rows (the supplement has no LEG column)
            S['leg']+=tot['me']['leg']; S['oleg']+=tot['op']['leg']; S['leg_min']+=f['mins']; S['leg_sl']+=tot['me']['sl']; S['leg_osl']+=tot['op']['sl']; S['leg_fights']+=1
            if f['round']>=3 and f['per']:
                for rn,pr in f['per'].items():
                    m=5.0 if rn<f['round'] else f['last_sec']/60
                    if rn<=2: S['early_sl']+=pr['me']['sl']; S['early_min']+=m
                    else: S['late_sl']+=pr['me']['sl']; S['late_min']+=m
                S['late_fights']+=1
        S['last']=max(S['last'] or f['date'],f['date'])
    S['last']=str(S['last']) if S['last'] else None
    return S

def features(S,P):
    """Smoothed per-stat features. P = population pooled means (from the frozen scale)."""
    m=S['mins']
    F={}
    F['SLpM']=(S['sl']+M0*P['SLpM'])/(m+M0)
    F['acc']=(S['sl_a']+K_ACC*P['acc'])/(S['sa_a']+K_ACC)
    F['KD15']=15*(S['kd']+M0*P['KD15']/15)/(m+M0)
    F['SApM']=(S['osl']+M0*P['SApM'])/(m+M0)
    F['strdef']=1-(S['osl_a']+K_STRDEF*(1-P['strdef']))/(S['osa_a']+K_STRDEF)
    F['TD15']=15*(S['td']+M0*P['TD15']/15)/(m+M0)
    F['TDacc']=(S['td_a']+K_TDACC*P['TDacc'])/(S['tda_a']+K_TDACC)
    F['TDD']=1-(S['otd_a']+K_TDD*(1-P['TDD']))/(S['otda_a']+K_TDD)
    F['SUB15']=15*(S['sub']+M0*P['SUB15']/15)/(m+M0)
    late=(S['late_sl']/S['late_min']) if S['late_min']>0 else None; early=(S['early_sl']/S['early_min']) if S['early_min']>0 else None
    r=(late/early) if (late is not None and early) else 1.0
    w=min(S['late_fights'],4)/4  # shrink the late/early ratio toward 1.0 until 4 fights reached R3
    F['LATE_RATIO']=1+(r-1)*w if r is not None else 1.0
    F['KOL_RATE']=(S['kol']+K_KOL*P['KOL_RATE'])/(S['n']+K_KOL)
    F['KDABS15']=15*(S['okd']+M0*P['KDABS15']/15)/(m+M0)
    # v1.1 leg-kick features (shrunk toward the population mean: M0 minutes / K_LEGSH strikes of pseudo-data)
    if 'LEG_PM' in P:
        lm=S.get('leg_min',0.0)
        F['LEG_PM']=(S.get('leg',0)+M0*P['LEG_PM'])/(lm+M0)
        F['LEG_SHARE']=(S.get('leg',0)+K_LEGSH*P['LEG_SHARE'])/(S.get('leg_sl',0)+K_LEGSH)
        F['OLEG_PM']=(S.get('oleg',0)+M0*P['OLEG_PM'])/(lm+M0)
        F['OLEG_SHARE']=(S.get('oleg',0)+K_LEGSH*P['OLEG_SHARE'])/(S.get('leg_osl',0)+K_LEGSH)
    return F
# row composites: (feature, weight, sign)
COMP={'Striking offence':[('SLpM',.5,1),('acc',.25,1),('KD15',.25,1)],
      'Striking defence':[('SApM',.5,-1),('strdef',.5,1)],
      'Wrestling offence':[('TD15',.7,1),('TDacc',.3,1)],
      'TD defence':[('TDD',1,1)],
      'Submission offence':[('SUB15',1,1)],
      'Cardio (proxy)':[('LATE_RATIO',.7,1),('SLpM',.3,1)],
      'Durability (proxy)':[('KOL_RATE',.6,-1),('KDABS15',.4,-1)],
      # v1.1 (2026-11-01): leg kicks. Offence = leg strikes landed/min + share of own sig. strikes to the legs.
      # Defence = leg strikes ABSORBED/min + share of absorbed sig. strikes that were leg strikes (both lower = better).
      'Leg-kick offence':[('LEG_PM',.6,1),('LEG_SHARE',.4,1)],
      'Leg-kick defence':[('OLEG_PM',.6,-1),('OLEG_SHARE',.4,-1)]}
COMP_V1=['Striking offence','Striking defence','Wrestling offence','TD defence','Submission offence','Cardio (proxy)','Durability (proxy)']
COMP_LK=['Leg-kick offence','Leg-kick defence']
def pct(sorted_vals,x):
    lo=bisect.bisect_left(sorted_vals,x); hi=bisect.bisect_right(sorted_vals,x)
    return (lo+0.5*(hi-lo))/len(sorted_vals)
def to_score(p): return max(1,min(10,math.ceil(10*p-1e-9))) if p>0 else 1

def build_scale():
    allS=[]
    for name in FIGHTS:
        S=raw_stats(name,dt.date(2026,11,2))  # include 2026-10-31 card in the reference population
        if S['n']>=3 and S['last'] and S['last']>='2018-01-01': allS.append((name,S))
    t=lambda k:sum(S[k] for _,S in allS)
    P=dict(SLpM=t('sl')/t('mins'),acc=t('sl_a')/t('sa_a'),KD15=15*t('kd')/t('mins'),SApM=t('osl')/t('mins'),
           strdef=1-t('osl_a')/t('osa_a'),TD15=15*t('td')/t('mins'),TDacc=t('td_a')/t('tda_a'),TDD=1-t('otd_a')/t('otda_a'),
           SUB15=15*t('sub')/t('mins'),KOL_RATE=t('kol')/t('n'),KDABS15=15*t('okd')/t('mins'))
    Fs=[features(S,P) for _,S in allS]
    feat_sorted={k:sorted(F[k] for F in Fs) for k in Fs[0]}
    comp_sorted={}
    for row,parts in [(r,COMP[r]) for r in COMP_V1]:
        vals=[sum(w*(pct(feat_sorted[k],F[k]) if s>0 else 1-pct(feat_sorted[k],F[k])) for k,w,s in parts) for F in Fs]
        comp_sorted[row]=sorted(vals)
    # human-readable cut-points for single stats (score k = percentile in ((k-1)*10%, k*10%])
    cuts={k:[round(v[min(len(v)-1,int(len(v)*q/10))],4) for q in range(1,10)] for k,v in feat_sorted.items()}
    out=dict(version='RATINGS-SCALE v1',built=dt.datetime.now().isoformat(timespec='seconds'),reference_cutoff=SCALE_CUTOFF,
             population=dict(rule='UFC fighters with >=3 UFC fights and a UFC fight on/after 2018-01-01 (mirror to 2026-10-17 + supplement to 2026-10-31), UFC_NAME_SPLIT=1',n=len(allS)),
             priors=P,smoothing=dict(K_ACC=K_ACC,K_STRDEF=K_STRDEF,K_TDACC=K_TDACC,K_TDD=K_TDD,M0_minutes=M0,K_KOL=K_KOL),
             decile_cuts=cuts,feature_sorted=feat_sorted,composite_sorted=comp_sorted,composites={r:[list(p) for p in v] for r,v in COMP.items()})
    json.dump(out,open(SCALE,'w'))
    return out
def build_scale_lk():
    """RATINGS-SCALE v1.1 extension: leg-kick priors, feature and composite distributions over the SAME reference population
    as v1 (>=3 UFC fights, a UFC fight on/after 2018-01-01, data through 2026-10-31). Written to a separate frozen file; the v1
    file and all v1 scores are untouched."""
    base=json.load(open(SCALE)); allS=[]
    for name in FIGHTS:
        S=raw_stats(name,dt.date(2026,11,2))
        if S['n']>=3 and S['last'] and S['last']>='2018-01-01': allS.append((name,S))
    t=lambda k:sum(S[k] for _,S in allS)
    P=dict(base['priors']); P.update(LEG_PM=t('leg')/t('leg_min'),LEG_SHARE=t('leg')/t('leg_sl'),OLEG_PM=t('oleg')/t('leg_min'),OLEG_SHARE=t('oleg')/t('leg_osl'))
    Fs=[features(S,P) for _,S in allS]; ks=['LEG_PM','LEG_SHARE','OLEG_PM','OLEG_SHARE']
    fsort={k:sorted(F[k] for F in Fs) for k in ks}; csort={}
    for row in COMP_LK:
        csort[row]=sorted(sum(w*(pct(fsort[k],F[k]) if sg>0 else 1-pct(fsort[k],F[k])) for k,w,sg in COMP[row]) for F in Fs)
    out=dict(version='RATINGS-SCALE v1.1 leg-kick extension',built=dt.datetime.now().isoformat(timespec='seconds'),population_n=len(allS),
             priors={k:P[k] for k in ks},smoothing=dict(M0_minutes=M0,K_LEGSH=K_LEGSH),feature_sorted=fsort,composite_sorted=csort,
             composites={r:[list(p) for p in COMP[r]] for r in COMP_LK},
             decile_cuts={k:[round(v[min(len(v)-1,int(len(v)*q/10))],4) for q in range(1,10)] for k,v in fsort.items()})
    json.dump(out,open(SCALE_LK,'w')); return out
_SC=None
def scale():
    global _SC
    if _SC is None:
        if not os.path.exists(SCALE): build_scale()
        _SC=json.load(open(SCALE))
        if os.path.exists(SCALE_LK):   # merge the v1.1 leg-kick extension (separate frozen file)
            X=json.load(open(SCALE_LK)); _SC['priors'].update(X['priors']); _SC['feature_sorted'].update(X['feature_sorted'])
            _SC['composite_sorted'].update(X['composite_sorted']); _SC['version']=_SC['version']+' + v1.1 leg-kick extension'
    return _SC

def rate(name,cutoff,resolve_name=True):
    sc=scale(); m=resolve(name) if resolve_name else name
    if not m:
        return dict(name=name,mirror=None,n=0,scores={r:5 for r in ROWS},pct={r:0.5 for r in ROWS},flags=['NO-UFCSTATS-MATCH','THIN'],stats={})
    S=raw_stats(m,cutoff); F=features(S,sc['priors']); fs=sc['feature_sorted']
    flags=[]; w=1.0
    if S['n']<THIN_N: flags.append('THIN'); w=S['n']/THIN_N
    if S['n']==0: flags.append('NO-UFC-FIGHTS')
    scores={}; pcts={}
    for row,parts in COMP.items():
        if row not in sc['composite_sorted']: continue
        c=sum(wt*(pct(fs[k],F[k]) if s>0 else 1-pct(fs[k],F[k])) for k,wt,s in parts)
        p=pct(sc['composite_sorted'][row],c)
        wr=min(1.0,S.get('leg_fights',0)/THIN_N) if row in COMP_LK else w
        p=0.5+(p-0.5)*wr
        pcts[row]=round(p,3); scores[row]=to_score(p)
    if S['late_fights']<2: flags.append('CARDIO-PROXY-THIN')
    if S.get('leg_fights',0)<THIN_N: flags.append('LEGKICK-THIN')
    st=dict(n=S['n'],mins=round(S['mins'],1),SLpM=round(S['sl']/S['mins'],2) if S['mins'] else None,
            acc=round(100*S['sl_a']/S['sa_a']) if S['sa_a'] else None,KD15=round(15*S['kd']/S['mins'],2) if S['mins'] else None,
            SApM=round(S['osl']/S['mins'],2) if S['mins'] else None,strdef=round(100*(1-S['osl_a']/S['osa_a'])) if S['osa_a'] else None,
            TD15=round(15*S['td']/S['mins'],2) if S['mins'] else None,TDacc=f"{S['td_a']}/{S['tda_a']}",TDD=f"{S['otda_a']-S['otd_a']}/{S['otda_a']}",
            SUB15=round(15*S['sub']/S['mins'],2) if S['mins'] else None,ko_losses=S['kol'],kd_absorbed=S['okd'],
            late_ratio=round(F['LATE_RATIO'],2),fights_to_r3=S['late_fights'],last_fight=S['last'],
            LEGpM=round(S['leg']/S['leg_min'],2) if S.get('leg_min') else None,leg_share=round(S['leg']/S['leg_sl'],2) if S.get('leg_sl') else None,
            LEGabs_pM=round(S['oleg']/S['leg_min'],2) if S.get('leg_min') else None,leg_abs_share=round(S['oleg']/S['leg_osl'],2) if S.get('leg_osl') else None,leg_fights=S.get('leg_fights',0))
    return dict(name=name,mirror=m,cutoff=str(cutoff),n=S['n'],scores=scores,pct=pcts,flags=flags,stats=st)

def str2(A,B):
    """STR2-TDD (tracked lead, not live): side whose Striking offence leads by >=2 and TD defence >= opp Wrestling offence - 1."""
    out=None
    for me,op,lab in ((A,B,'a'),(B,A,'b')):
        try: so,oso,tdd,owo=me['Striking offence'],op['Striking offence'],me['TD defence'],op['Wrestling offence']
        except (KeyError,TypeError): continue
        if None in (so,oso,tdd,owo): continue
        if so-oso>=2: out=dict(striker=lab,lead=so-oso,tdd_gap=tdd-owo,group='QUAL' if tdd-owo>=-1 else ('COMP' if tdd-owo<=-2 else 'MID'))
    return out
def snapshot(card_path,late=False):
    card=json.load(open(card_path))
    if dt.date.today()>dt.date.fromisoformat(card['event_date']) and not late:
        sys.exit('REFUSED: event_date is in the past; a snapshot now is not pre-fight. Use --late to write one labelled POST-FIGHT.')
    out=card_path[:-5]+'.ratings-snapshot.json' if card_path.endswith('.json') else card_path+'.ratings-snapshot.json'
    if os.path.exists(out): sys.exit(f'REFUSED: {out} exists (snapshots are frozen; never overwrite).')
    cut=card['event_date']; bouts=[]
    for b in card['bouts']:
        ra,rb=rate(b['a'],cut),rate(b['b'],cut); an=b.get('ratings') or {}
        def col(i): return {k:(v[i] if isinstance(v,list) and len(v)==2 and isinstance(v[i],(int,float)) else None) for k,v in an.items()}
        bouts.append(dict(n=b.get('n'),a=b['a'],b=b['b'],analyst_ratings=b.get('ratings'),
            data_ratings={'a':ra,'b':rb},
            str2_tdd=dict(analyst=str2(col(0),col(1)),data=str2(ra['scores'],rb['scores']))))
    snap=dict(label='POST-FIGHT (late)' if late else 'PRE-FIGHT',event_id=card.get('event_id'),event_date=cut,frozen_at=dt.datetime.now().astimezone().isoformat(timespec='seconds'),
        scale=scale()['version'],data_cutoff_rule='UFC fights strictly before event_date',source_card=card_path,
        source_card_sha256=hashlib.sha256(open(card_path,'rb').read()).hexdigest(),bouts=bouts)
    body=json.dumps(snap,indent=1,ensure_ascii=False); snap['sha256']=hashlib.sha256(body.encode()).hexdigest()
    json.dump(snap,open(out,'w'),indent=1,ensure_ascii=False); os.chmod(out,0o444); print('wrote',out)

if __name__=='__main__':
    a=sys.argv[1:]
    if not a: print(__doc__); sys.exit()
    if a[0]=='build-scale':
        if os.path.exists(SCALE) and '--force' not in a: sys.exit(f'REFUSED: {SCALE} is frozen. Rebuilding changes every score; use --force and bump the version in RATINGS-SCALE.md.')
        o=build_scale(); print('population',o['population']['n']); print(json.dumps(o['decile_cuts'],indent=0))
    elif a[0]=='build-scale-lk':
        if os.path.exists(SCALE_LK) and '--force' not in a: sys.exit(f'REFUSED: {SCALE_LK} is frozen.')
        o=build_scale_lk(); print('population',o['population_n']); print(json.dumps(o['priors']))
    elif a[0]=='rate':
        for n in a[2:]: print(json.dumps(rate(n,a[1]),indent=1,ensure_ascii=False))
    elif a[0]=='snapshot': snapshot(a[1],late='--late' in a)
    else: print(__doc__)
