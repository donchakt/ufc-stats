import os as _o; UFC_ROOT=_o.environ.get('UFC_ROOT') or _o.path.abspath(_o.path.join(_o.path.dirname(_o.path.abspath(__file__)),'..','..'))+'/'
"""Pre-fight UFCStats profile from the mirror, using ONLY fights strictly before the cutoff date.
Usage: python3 prefight_profile.py YYYY-MM-DD "Fighter Name" ["Fighter 2" ...]  -> prints + returns dict"""
import csv,re,sys,json,datetime as dt
M=UFC_ROOT+'sources/featherweight/ufcstats-mirror/'
def D(s): return dt.datetime.strptime(s.strip(),'%B %d, %Y').date()
EVD={r['EVENT'].strip():D(r['DATE']) for r in csv.DictReader(open(M+'ufc_event_details.csv'))}
RES=list(csv.DictReader(open(M+'ufc_fight_results.csv')))
ST=list(csv.DictReader(open(M+'ufc_fight_stats.csv')))
TOTT={r['FIGHTER'].strip():r for r in csv.DictReader(open(M+'ufc_fighter_tott.csv'))}
# Name-collision split (added 2026-10-31 ~11:00 CST after the U4 Bruno Silva merge). The mirror keys fighters by name only,
# so two different "Bruno Silva"s are merged: flyweight 'Bulldog' (DOB 1990-03-16, 5'4", fighter-details 294aa73dbf37d281)
# and middleweight 'Blindado' (DOB 1989-07-13, 6'0", 12ebd7d157e91701). With UFC_NAME_SPLIT=1 the middleweight's bouts,
# stat rows and tott row are renamed "Bruno Silva (Blindado)"; "Bruno Silva" then means the flyweight only (incl. his
# 2019 bantamweight NC vs Khalid Taha). OPT-IN for now so the 2026-10-31 live lock run is byte-for-byte unaffected;
# enable it in batch runs (export UFC_NAME_SPLIT=1). Add further collisions to NAME_SPLIT.
import os as _os
NAME_SPLIT=[dict(name='Bruno Silva',alias='Bruno Silva (Blindado)',weightclass='Middleweight',tott_weight='185',url_id='12ebd7d157e91701',keep_tott_weight='125')]
def _apply_name_split():
    for c in NAME_SPLIT:
        nm,al=c['name'],c['alias']; moved=set()
        for r in RES:
            a,b=[x.strip() for x in r['BOUT'].split(' vs. ')]
            if nm in (a,b) and c['weightclass'] in r['WEIGHTCLASS']:
                key=(r['EVENT'].strip(),r['BOUT'].strip()); moved.add(key)
                r['BOUT']=' vs. '.join(al if x==nm else x for x in (a,b))
        for s_ in ST:
            key=(s_['EVENT'].strip(),s_['BOUT'].strip())
            if key in moved:
                a,b=[x.strip() for x in s_['BOUT'].split(' vs. ')]
                s_['BOUT']=' vs. '.join(al if x==nm else x for x in (a,b))
                if s_['FIGHTER'].strip()==nm: s_['FIGHTER']=al
        rows=[r for r in csv.DictReader(open(M+'ufc_fighter_tott.csv')) if r['FIGHTER'].strip()==nm]
        for r in rows:
            if r['WEIGHT'].startswith(c['tott_weight']): TOTT[al]=dict(r,FIGHTER=al)
            if r['WEIGHT'].startswith(c['keep_tott_weight']): TOTT[nm]=r
NAME_SPLIT_ON=_os.environ.get('UFC_NAME_SPLIT')=='1'
def of(s):
    m=re.match(r'(\d+) of (\d+)',s or '');return (int(m[1]),int(m[2])) if m else (0,0)
def sec(s):
    try: m,s2=s.split(':');return int(m)*60+int(s2)
    except: return 0
if NAME_SPLIT_ON: _apply_name_split()
STX={}
for s in ST: STX.setdefault((s['EVENT'].strip(),s['BOUT'].strip()),[]).append(s)
def profile(name,cutoff):
    cutoff=dt.date.fromisoformat(cutoff) if isinstance(cutoff,str) else cutoff
    fights=[]
    for r in RES:
        e=r['EVENT'].strip(); d=EVD.get(e)
        if d is None or d>=cutoff: continue
        a,b=[x.strip() for x in r['BOUT'].split(' vs. ')]
        if name not in (a,b): continue
        me_i=0 if name==a else 1; op=b if me_i==0 else a
        o=r['OUTCOME'].split('/'); wl=o[me_i] if len(o)==2 else '?'
        rnd=int(r['ROUND'] or 1); mins=((rnd-1)*300+sec(r['TIME']))/60
        rows=STX.get((e,r['BOUT'].strip()),[])
        def agg(f):
            d=dict(kd=0,sl=0,sa=0,td=0,tda=0,sub=0,ctrl=0)
            for s in rows:
                if s['FIGHTER'].strip()!=f: continue
                d['kd']+=int(float(s['KD'] or 0)); x=of(s['SIG.STR.']); d['sl']+=x[0]; d['sa']+=x[1]
                x=of(s['TD']); d['td']+=x[0]; d['tda']+=x[1]; d['sub']+=int(float(s['SUB.ATT'] or 0)); d['ctrl']+=sec(s['CTRL'])
            return d
        fights.append(dict(date=str(d),event=e,opp=op,wl=wl,method=r['METHOD'].strip(),round=rnd,mins=round(mins,2),me=agg(name),op=agg(op),fmt=r['TIME FORMAT']))
    fights.sort(key=lambda f:f['date'],reverse=True)
    t=TOTT.get(name,{})
    out=dict(name=name,cutoff=str(cutoff),n=len(fights),height=t.get('HEIGHT'),reach=t.get('REACH'),stance=t.get('STANCE'),dob=t.get('DOB'))
    if t.get('DOB') and t['DOB']!='--':
        dob=dt.datetime.strptime(t['DOB'],'%b %d, %Y').date(); out['age']=round((cutoff-dob).days/365.25,1)
    W=sum(f['wl']=='W' for f in fights); L=sum(f['wl']=='L' for f in fights)
    out['ufc_record']=f"{W}-{L}" + (f"-{len(fights)-W-L}" if len(fights)-W-L else '')
    def stats(fs):
        m=sum(f['mins'] for f in fs) or 1e-9
        sl=sum(f['me']['sl'] for f in fs); sa=sum(f['me']['sa'] for f in fs)
        osl=sum(f['op']['sl'] for f in fs); osa=sum(f['op']['sa'] for f in fs)
        td=sum(f['me']['td'] for f in fs); tda=sum(f['me']['tda'] for f in fs)
        otd=sum(f['op']['td'] for f in fs); otda=sum(f['op']['tda'] for f in fs)
        return dict(mins=round(m,1),SLpM=round(sl/m,2),acc=round(100*sl/sa) if sa else None,SApM=round(osl/m,2),
          strdef=round(100*(1-osl/osa)) if osa else None,TD15=round(15*td/m,2),TDacc=f"{td}/{tda}",TDdef=f"{otda-otd}/{otda}",
          ctrl_pct=round(100*sum(f['me']['ctrl'] for f in fs)/(60*m)),opp_ctrl_pct=round(100*sum(f['op']['ctrl'] for f in fs)/(60*m)),
          sub15=round(15*sum(f['me']['sub'] for f in fs)/m,2),KD15=round(15*sum(f['me']['kd'] for f in fs)/m,2),KDabs=sum(f['op']['kd'] for f in fs))
    if fights:
        out['career']=stats(fights); out['last3']=stats(fights[:3])
        out['layoff_days']=(cutoff-dt.date.fromisoformat(fights[0]['date'])).days
        ko=[f for f in fights if f['wl']=='L' and 'KO' in f['method']]
        out['ko_losses']=len(ko); out['last_ko_loss']=ko[0]['date'] if ko else None
        out['finish_wins']=sum(f['wl']=='W' and 'Decision' not in f['method'] for f in fights)
        out['recent']=[f"{f['date']} {f['wl']} vs {f['opp']} {f['method']} R{f['round']} | sig {f['me']['sl']}-{f['op']['sl']} TD {f['me']['td']}/{f['me']['tda']} v {f['op']['td']}/{f['op']['tda']} ctrl {f['me']['ctrl']//60}:{f['me']['ctrl']%60:02d}-{f['op']['ctrl']//60}:{f['op']['ctrl']%60:02d} KD {f['me']['kd']}-{f['op']['kd']}" for f in fights[:6]]
    return out
if __name__=='__main__':
    c=sys.argv[1]
    for n in sys.argv[2:]:
        p=profile(n,c)
        print(json.dumps(p,indent=1,ensure_ascii=False))

# v0.4.3 (added 2026-11-01): decline markers for the symmetric-scoring rule (rule 3). Same data as profile(), fights strictly before cutoff.
# Returned for EVERY fighter (favourite and underdog alike); backtest/tools/v043.py requires each present marker to be scored.
def decline_markers(name,cutoff):
    p=profile(name,cutoff); cutoff=dt.date.fromisoformat(cutoff) if isinstance(cutoff,str) else cutoff
    lk=p.get('last_ko_loss'); last=(p.get('recent') or [''])[0]
    last_ko=bool(last) and ' L vs ' in last and 'KO' in last.split(' | ')[0]
    return dict(name=name,ufc_fights=p['n'],layoff_days=p.get('layoff_days'),
        last_fight_ko_loss=last_ko,
        ko_loss_within_365=bool(lk) and (cutoff-dt.date.fromisoformat(lk)).days<=365,
        last_ko_loss=lk,age=p.get('age'))
