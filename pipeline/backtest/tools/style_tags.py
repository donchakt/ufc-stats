import os as _o; UFC_ROOT=_o.environ.get('UFC_ROOT') or _o.path.abspath(_o.path.join(_o.path.dirname(_o.path.abspath(__file__)),'..','..'))+'/'
"""Style archetypes (v1, 2026-10-30) + upset-indicator columns for every bout in factor-inputs.csv.
PRE-FIGHT ONLY: every number comes from the UFCStats mirror restricted to fights strictly before the event date
(same cutoff rule as prefight_profile.py). Blank = could not source; never guessed.
Writes backtest/style/style-tags.csv (keyed by event_id+bout) — merge_style.py appends these as NEW columns."""
import csv,re,sys,json,datetime as dt
sys.path.insert(0,UFC_ROOT+'backtest/tools')
import prefight_profile as PP
from analyze import norm
B=UFC_ROOT+'backtest/'
EVLOC={k.strip():v['LOCATION'] for v in csv.DictReader(open(PP.M+'ufc_event_details.csv')) for k in [v['EVENT']]}
ALIAS={'choi doo-ho':'Dooho Choi','carlos diego ferreira':'Diego Ferreira','abdul-rakhman yakhyaev':'Abdul Rakhman Yakhyaev','giovanna canuto':'Gigi Canuto'}
ALLN=set(PP.TOTT)
for _r in PP.RES: ALLN.update(x.strip() for x in _r['BOUT'].split(' vs. '))
def nn(s): return norm(s).replace('ł','l').replace('-',' ')
def fix(n):
    n=n.replace(' (c)','').strip()
    if norm(n) in ALIAS: return ALIAS[norm(n)]
    if n in ALLN: return n
    k=nn(n)
    for t in ALLN:
        if nn(t)==k: return t
    return None
def of(s): return PP.of(s)
WC={}
for r in PP.RES: WC[(r['EVENT'].strip(),r['BOUT'].strip())]=r['WEIGHTCLASS'].strip()
def wcname(s):
    s=s.replace('UFC ','').replace(' Title','').replace(' Bout','').replace('Interim ','').strip()
    return s
def fights(name,cutoff):
    cutoff=dt.date.fromisoformat(cutoff); out=[]
    for r in PP.RES:
        e=r['EVENT'].strip(); d=PP.EVD.get(e)
        if d is None or d>=cutoff: continue
        a,b=[x.strip() for x in r['BOUT'].split(' vs. ')]
        if name not in (a,b): continue
        me=0 if name==a else 1; op=b if me==0 else a
        o=r['OUTCOME'].split('/'); wl=o[me] if len(o)==2 else '?'
        rnd=int(r['ROUND'] or 1); mins=((rnd-1)*300+PP.sec(r['TIME']))/60
        rows=PP.STX.get((e,r['BOUT'].strip()),[])
        per={}
        for s in rows:
            f=s['FIGHTER'].strip(); rn=s['ROUND'].strip()
            key='me' if f==name else 'op'
            d2=per.setdefault((key,rn),dict(kd=0,sl=0,sa=0,td=0,tda=0,sub=0,ctrl=0,head=0,body=0,leg=0,dist=0,clinch=0,ground=0))
            d2['kd']+=int(float(s['KD'] or 0)); x=of(s['SIG.STR.']); d2['sl']+=x[0]; d2['sa']+=x[1]
            x=of(s['TD']); d2['td']+=x[0]; d2['tda']+=x[1]; d2['sub']+=int(float(s['SUB.ATT'] or 0)); d2['ctrl']+=PP.sec(s['CTRL'])
            for k,c in [('head','HEAD'),('body','BODY'),('leg','LEG'),('dist','DISTANCE'),('clinch','CLINCH'),('ground','GROUND')]: d2[k]+=of(s[c])[0]
        out.append(dict(date=d,event=e,opp=op,wl=wl,method=r['METHOD'].strip(),round=rnd,mins=mins,per=per,wc=wcname(r['WEIGHTCLASS'])))
    out.sort(key=lambda f:f['date'],reverse=True); return out
def tot(fs,who):
    T=dict(kd=0,sl=0,sa=0,td=0,tda=0,sub=0,ctrl=0,head=0,body=0,leg=0,dist=0,clinch=0,ground=0)
    for f in fs:
        for (k,rn),d in f['per'].items():
            if k==who:
                for x in T: T[x]+=d[x]
    return T
def rnd_sl(f,rn,who='me'):
    d=f['per'].get((who,f'Round {rn}')); return d['sl'] if d else None
def prof(name,cutoff):
    m=fix(name)
    if not m: return dict(found=0)
    fs=fights(m,cutoff); t=PP.TOTT.get(m,{})
    P=dict(found=1,mirror_name=m,n=len(fs),stance=(t.get('STANCE') or '').strip() or None)
    rr=re.match(r'(\d+)',t.get('REACH') or ''); P['reach']=int(rr[1]) if rr else None
    hh=re.match(r"(\d+)' (\d+)",t.get('HEIGHT') or ''); P['height']=int(hh[1])*12+int(hh[2]) if hh else None
    if t.get('DOB') and t['DOB']!='--':
        P['age']=round((dt.date.fromisoformat(cutoff)-dt.datetime.strptime(t['DOB'],'%b %d, %Y').date()).days/365.25,1)
    else: P['age']=None
    if not fs: return P
    mins=sum(f['mins'] for f in fs) or 1e-9
    me=tot(fs,'me'); op=tot(fs,'op')
    P.update(mins=round(mins,1),slpm=me['sl']/mins,sapm=op['sl']/mins,strdef=(1-op['sl']/op['sa']) if op['sa'] else None,
      td15=15*me['td']/mins,tda15=15*me['tda']/mins,tdacc=(me['td']/me['tda']) if me['tda'] else None,
      tdd=(1-op['td']/op['tda']) if op['tda'] else None,opp_tda=op['tda'],ctrl=me['ctrl']/(60*mins),octrl=op['ctrl']/(60*mins),
      sub15=15*me['sub']/mins,kd15=15*me['kd']/mins,kdabs=op['kd'],kd_n=me['kd'],kdabs15=15*op['kd']/mins,
      leg_share=me['leg']/me['sl'] if me['sl'] else None,body_share=me['body']/me['sl'] if me['sl'] else None,
      dist_share=me['dist']/me['sl'] if me['sl'] else None,clinch_share=me['clinch']/me['sl'] if me['sl'] else None,
      ground_share=me['ground']/me['sl'] if me['sl'] else None)
    W=[f for f in fs if f['wl']=='W']; L=[f for f in fs if f['wl']=='L']
    P['wins']=len(W); P['losses']=len(L)
    P['ko_wins']=sum('KO' in f['method'] for f in W); P['sub_wins']=sum('Submission' in f['method'] for f in W)
    P['finish_wins']=sum('Decision' not in f['method'] for f in W)
    P['finish_rate']=P['finish_wins']/len(W) if W else None
    P['ko_losses']=sum('KO' in f['method'] for f in L)
    P['last_result']=fs[0]['wl']; P['last_method']=fs[0]['method']
    P['last_fight_ko_loss']=int(fs[0]['wl']=='L' and 'KO' in fs[0]['method'])
    P['last_loss_ko']=(int('KO' in L[0]['method']) if L else None)
    P['last3_wins']=sum(f['wl']=='W' for f in fs[:3]); P['last3_n']=len(fs[:3])
    s=0
    for f in fs:
        if f['wl']=='W': s+=1
        else: break
    P['win_streak']=s
    P['layoff']=(dt.date.fromisoformat(cutoff)-fs[0]['date']).days
    P['prev_wc']=fs[0]['wc']
    l3=fs[:3]; m3=sum(f['mins'] for f in l3) or 1e-9; a3=tot(l3,'me'); o3=tot(l3,'op')
    P['diff']=P['slpm']-P['sapm']; P['diff_l3']=(a3['sl']-o3['sl'])/m3
    # fades late: fights reaching R3 (>=2 such fights): R3 sig landed < 70% of R1
    r3=[f for f in fs if f['round']>=3 and rnd_sl(f,1) is not None and rnd_sl(f,3) is not None and (f['round']>3 or f['mins']>=14.5)]
    if len(r3)>=2:
        r1s=sum(rnd_sl(f,1) for f in r3); r3s=sum(rnd_sl(f,3) for f in r3)
        P['fade_ratio']=r3s/r1s if r1s else None
    else: P['fade_ratio']=None
    r2=[f for f in fs if f['round']>=2 and rnd_sl(f,1) is not None and rnd_sl(f,2) is not None]
    if len(r2)>=2:
        a=sum(rnd_sl(f,1) for f in r2); b=sum(rnd_sl(f,2) for f in r2)
        P['start_ratio']=a/b if b else None
    else: P['start_ratio']=None
    return P
MIN_MINS=15  # need >=15 UFC minutes AND >=2 UFC fights to tag an archetype
def archetype(P):
    if not P.get('found') or P.get('n',0)<2 or P.get('mins',0)<MIN_MINS: return ''
    td,ctrl,sub,kd,sl=P['td15'],P['ctrl'],P['sub15'],P['kd15'],P['slpm']
    if P['tda15']>=6 and ctrl>=0.40: return 'chain wrestler'
    if sub>=1.2 and (ctrl>=0.15 or P['sub_wins']>=2): return 'BJJ/submission grappler'
    if td>=1.5 and ctrl>=0.25: return 'pressure wrestler'
    if (P['clinch_share'] or 0)>=0.25: return 'clinch/dirty boxer'
    if (kd>=0.6 and P['kd_n']>=2) or (P['ko_wins']>=3 and P['ko_wins']>=0.6*P['wins']): return 'power puncher/brawler'
    if sl>=5.0 and (P['leg_share'] or 0)<0.20: return 'volume boxer'
    if ((P['leg_share'] or 0)+(P['body_share'] or 0))>=0.35 and (P['dist_share'] or 0)>=0.75: return 'kickboxer/range striker'
    if sl<4.5 and (P['strdef'] or 0)>=0.57: return 'counter-striker'
    return 'well-rounded'
def traits(P,O,short_notice):
    t=[]
    if P.get('stance')=='Southpaw': t.append('southpaw')
    if P.get('stance')=='Switch': t.append('switch')
    if P.get('reach') and O.get('reach') and P['reach']-O['reach']>=3: t.append('long reach')
    if P.get('fade_ratio') is not None and P['fade_ratio']<0.70: t.append('fades late')
    if P.get('start_ratio') is not None and P['start_ratio']<0.70: t.append('slow starter')
    if P.get('n',0)>=5 and P.get('ko_losses',1)==0 and P.get('kdabs',9)<=1: t.append('durable chin')
    if P.get('ko_losses',0)>=1: t.append('chin questions')
    if P.get('age') is not None and P['age']>=35: t.append('age 35+')
    if short_notice: t.append('short notice')
    if P.get('layoff') is not None and P['layoff']>=300: t.append('layoff 300+')
    if P.get('found') and P.get('n',0)==0: t.append('UFC debut')
    elif P.get('n',0) and P['n']<=3: t.append('thin UFC sample')
    return '|'.join(t)
# documented short-notice / late replacements (pre-fight announcements; sources noted)
SHORT={('ufc-fn-ankalaev-guskov','Bogdan Guskov'):'Wikipedia card changes (backtest/sources): moved in on Jul 13 for Jul 25 headliner after Rountree withdrew',
       ('ufc-fn-allen-costa','Christian Edwards'):'Wikipedia background: replaced Rodolfo Bellato during fight week (catchweight 215) — added 2026-10-30 batch 4'}
def ip(o):
    try: o=int(o)
    except: return None
    return 100/(o+100) if o>0 else -o/(-o+100)
# open/close odds only where already saved on the box
OPENCLOSE={('ufc-329','Conor McGregor'):('Max Holloway',-270,-272,'BFO fighter page (backtest/odds)'),
 ('ufc-fn-song-figueiredo','Zhang'):None}
U333={'Petr Yan':(-175,-150),"Lone'er Kavanagh":(-114,-110),'Alexander Volkov':(-127,-122),'Aaron Pico':(-107,-140),
 'Azamat Murzakanov':(-205,-217),'Abdul-Rakhman Yakhyaev':(-600,-475),'Abus Magomedov':(-106,-120),'Grant Dawson':(-110,-128),
 'Asaf Chopurov':(-500,-525),'Daniel Santos':(-145,-125),'Kody Steele':(-150,-160),'Iasmin Lucindo':(-239,-365),'Alexander Volkanovski':(-120,-112)}
def build():
    FI=list(csv.DictReader(open(B+'factor-inputs.csv')))
    G=json.load(open(B+'graded.json'))
    gfav={(g['event_id'],norm(g['pick']),norm(g['opp'])):g.get('favourite') for g in G}
    blog=list(csv.DictReader(open(UFC_ROOT+'backtest-log.csv')))
    cards={}
    import glob
    for p in glob.glob(B+'cards/*.json'):
        c=json.load(open(p))
        for b in c.get('bouts',[]): cards[(c['event_id'],frozenset([norm(b['fighter_a']),norm(b['fighter_b'])]))]=b.get('weight','')
    odds={}
    for p in glob.glob(B+'odds/*.json'):
        eid=p.split('/')[-1][:-5]
        for k,v in json.load(open(p)).items(): odds[(eid,frozenset([norm(v['fighter_a']),norm(v['fighter_b'])]))]=v
    out=[]
    for r in FI:
        pick,opp=r['pick'],r['opponent']; mp=r['market_prob_pick']
        basis='market'
        if mp not in ('',None) and abs(float(mp)-0.5)>1e-9:
            fav,dog=(pick,opp) if float(mp)>0.5 else (opp,pick); pfav=max(float(mp),1-float(mp))
        else:
            f=gfav.get((r['event_id'],norm(pick),norm(opp)))
            if r['event_id']=='ufc-333':
                bl=[b for b in blog if b['event']=='UFC 333' and norm(b['pick'])==norm(pick)]
                f=bl[0]['betting_favourite'] if bl else None
                if f and 'marginal' in f: f=f.split(';')[1].replace('(marginal)','').strip()
                elif f and "pick'em" in f.lower(): f=None
            if mp=='' and f: basis='graded favourite (no two-sided odds)'
            else: basis='pickem'
            if f and norm(f)==norm(opp): fav,dog=opp,pick
            elif f and norm(f)==norm(pick): fav,dog=pick,opp
            else: fav,dog=pick,opp; basis='pickem (fav=model pick, no market fav)'
            pfav=float(mp) if mp else ''
        if str(r['pick_correct']).strip()=='': upset=''   # draw / no contest (batch 8+): no winner, excluded from upset tables
        else:
            ok=int(r['pick_correct']); winner=pick if ok else opp
            upset=int(norm(winner)!=norm(fav)) if not basis.startswith('pickem') else ''
        sn_f=SHORT.get((r['event_id'],fav)); sn_d=SHORT.get((r['event_id'],dog))
        F=prof(fav,r['event_date']); D=prof(dog,r['event_date'])
        def g(P,k,nd=3):
            v=P.get(k); 
            if v is None or v=='': return ''
            return round(v,nd) if isinstance(v,float) else v
        o=dict(event_id=r['event_id'],bout=r['bout'],fav_name=fav,dog_name=dog,fav_basis=basis,p_fav_market=round(pfav,4) if pfav!='' else '',upset=upset)
        o['fav_style']=archetype(F); o['fav_traits']=traits(F,D,sn_f); o['dog_style']=archetype(D); o['dog_traits']=traits(D,F,sn_d)
        o['fav_ufc_fights']=F.get('n',''); o['dog_ufc_fights']=D.get('n','')
        # upset-signal columns
        o['fav_last_result']=g(F,'last_result'); o['dog_last_result']=g(D,'last_result')
        o['fav_last_fight_ko_loss']=g(F,'last_fight_ko_loss'); o['fav_last_loss_ko']=g(F,'last_loss_ko')
        o['dog_kd15']=g(D,'kd15',2); o['dog_finish_rate']=g(D,'finish_rate',2); o['dog_ko_wins']=g(D,'ko_wins')
        o['fav_kd_absorbed']=g(F,'kdabs'); o['fav_kdabs15']=g(F,'kdabs15',2); o['fav_ko_losses']=g(F,'ko_losses'); o['fav_strdef']=g(F,'strdef',2)
        # one-weapon dependence
        wpn=dep=dd=''
        if F.get('n',0)>=2:
            if F['td15']>=1.5 and F['ctrl']>=0.25: wpn,dep,dd='takedowns/control',F['ctrl'],D.get('tdd') if D.get('opp_tda',0)>=5 else None
            elif (F.get('sub15') or 0)>=1.2: wpn,dep,dd='submissions',(F['sub_wins']/F['wins']) if F['wins'] else None,D.get('tdd') if D.get('opp_tda',0)>=5 else None
            elif (F.get('clinch_share') or 0)>=0.25: wpn,dep,dd='clinch striking',F['clinch_share'],D.get('strdef')
            else: wpn,dep,dd='distance striking',F.get('dist_share'),D.get('strdef')
        o['fav_main_weapon']=wpn; o['fav_weapon_dependence']=round(dep,2) if isinstance(dep,float) else (dep if dep is not None else '')
        o['dog_defence_vs_weapon']=round(dd,2) if isinstance(dd,float) else ''
        if o['fav_weapon_dependence']!='' and o['dog_defence_vs_weapon']!='':
            thr=0.75 if wpn in('takedowns/control','submissions') else 0.58
            depthr=0.40 if wpn in('takedowns/control','submissions') else 0.80
            o['weapon_blocked_flag']=int(o['fav_weapon_dependence']>=depthr and o['dog_defence_vs_weapon']>=thr)
        else: o['weapon_blocked_flag']=''
        # odds open/close (only where saved on box)
        ov=odds.get((r['event_id'],frozenset([norm(fav),norm(dog)])))
        o['fav_odds_open']=o['fav_odds_close']=o['line_direction']=''; o['odds_source']=''
        if ov and 'open' in ov.get('source',''):
            s=ov['source']; nm=lambda n: n.split()[-1]
            mo=None
            for tok in fav.replace(' (c)','').split():
                mo=mo or re.search(re.escape(tok)+r' open ([+-]\d+) / close(?: range)? ([+-]\d+)\.\.([+-]\d+)',s)
            if mo:
                op_=int(mo[1]); _pm=(ip(int(mo[2]))+ip(int(mo[3])))/2; cl=(-100*_pm/(1-_pm)) if _pm>=0.5 else (100*(1-_pm)/_pm)  # 2026-10-31: implied-prob midpoint (American average broke across even money, e.g. -125..+115 -> -5)
                o['fav_odds_open']=op_; o['fav_odds_close']=int(round(cl)); po,pc=ip(op_),ip(int(round(cl)))
                o['line_direction']='toward fav' if pc-po>0.02 else ('toward dog' if po-pc>0.02 else 'flat')
                o['odds_source']='BFO fighter page saved in backtest/odds (close = midpoint of range)'
        if r['event_id']=='ufc-333' and fav in U333:
            op_,cl=U333[fav]; o['fav_odds_open']=op_; o['fav_odds_close']=cl; po,pc=ip(op_),ip(cl)
            o['line_direction']='toward fav' if pc-po>0.02 else ('toward dog' if po-pc>0.02 else 'flat')
            o['odds_source']='ufc-333.md: consensus open -> fight-week consensus (not true close)'
        # extra indicators
        def gap(k):
            a,b=F.get(k),D.get(k)
            return round(a-b,2) if a is not None and b is not None else ''
        o['reach_gap_fav']=gap('reach'); o['height_gap_fav']=gap('height'); o['age_gap_fav']=gap('age')
        o['fav_age']=g(F,'age',1); o['dog_age']=g(D,'age',1)
        sf,sd=F.get('stance'),D.get('stance')
        o['stance_matchup']=f"{sf}-v-{sd}" if sf and sd else ''
        o['open_stance']=(int((sf=='Southpaw')!=(sd=='Southpaw')) if sf in('Orthodox','Southpaw') and sd in('Orthodox','Southpaw') else '')
        o['ufc_fights_gap_fav']=(F['n']-D['n']) if F.get('found') and D.get('found') else ''
        o['finish_rate_gap_fav']=gap('finish_rate')
        o['fav_str_diff']=g(F,'diff',2); o['dog_str_diff']=g(D,'diff',2); o['str_diff_gap_fav']=gap('diff')
        o['fav_str_diff_l3_minus_career']=round(F['diff_l3']-F['diff'],2) if F.get('n',0)>=4 else ''
        o['dog_str_diff_l3_minus_career']=round(D['diff_l3']-D['diff'],2) if D.get('n',0)>=4 else ''
        def tdthreat(A,Dd):
            if A.get('n',0)<2 or Dd.get('n',0)<2 or Dd.get('opp_tda',0)<5 or Dd.get('tdd') is None: return ''
            return round(A['tda15']*(A['tdacc'] or 0)*(1-Dd['tdd']),2)
        o['fav_td_threat']=tdthreat(F,D); o['dog_td_threat']=tdthreat(D,F)
        o['fav_layoff']=g(F,'layoff'); o['dog_layoff']=g(D,'layoff')
        o['fav_last3_wins']=g(F,'last3_wins'); o['dog_last3_wins']=g(D,'last3_wins')
        o['fav_win_streak']=g(F,'win_streak'); o['dog_win_streak']=g(D,'win_streak')
        bw=cards.get((r['event_id'],frozenset([norm(fav),norm(dog)])),'')
        cur=wcname(bw) if bw else ''
        if not cur:
            # UFC 333 etc.: from backtest-log weight_class if present
            bl=[b for b in blog if norm(b['pick'])==norm(pick) and b['event_date']==r['event_date']]
            cur=bl[0]['weight_class'].split('(')[0].strip() if bl else ''
        def wch(P):
            if not cur or not P.get('prev_wc'): return ''
            if 'catch' in cur.lower(): return 'catchweight'
            return 'same' if norm(P['prev_wc']).split()[-1]==norm(cur).split()[-1] or norm(P['prev_wc'])==norm(cur) else f"{P['prev_wc']} -> {cur}"
        o['weight_class']=cur; o['fav_wc_change']=wch(F); o['dog_wc_change']=wch(D)
        o['live_dog_flag']=(int((D.get('kd15') or 0)>=0.5 and (F.get('ko_losses') or 0)>=1) if D.get('n',0)>=2 and F.get('found') else '')
        o['event_location']='Abu Dhabi, Abu Dhabi, United Arab Emirates' if r['event_id']=='ufc-333' else EVLOC.get(next((e for e,d in PP.EVD.items() if str(d)==r['event_date'] and e.strip()),''),'')
        o['style_tag_version']='v1 2026-10-30'
        out.append(o)
    return out
if __name__=='__main__':
    out=build()
    with open(B+'style/style-tags.csv','w',newline='') as f:
        w=csv.DictWriter(f,fieldnames=list(out[0])); w.writeheader(); w.writerows(out)
    print(len(out),'rows')
