"""Pack app-data.json into compact arrays for the Page and the HTML app.
compact(page=True): card fighters keep 6 fights, other ranked fighters keep 3 (size limit); HTML keeps 6 for everyone."""
import json,os
HERE=os.path.dirname(os.path.abspath(__file__))
SK=['slpm','acc','sapm','def','tdavg','tdacc','tddef','subavg']
def num(x):
    if x is None: return None
    return int(x) if float(x).is_integer() else x
def compact(page=True):
    d=json.load(open(HERE+'/app-data.json'))
    F=d['fighters']; slugs=list(F.keys()); IX={s:i for i,s in enumerate(slugs)}
    EVN=[]; eix={}
    def ev(n):
        if n not in eix: eix[n]=len(EVN); EVN.append(n)
        return eix[n]
    rows=[]
    for s in slugs:
        f=F[s]; st=f.get('stats') or {}; r=f.get('rating')
        keep=6 if (f['card'] or not page) else 3
        fights=';'.join('|'.join(str(v) for v in [x[0],x[1],x[2],x[3],x[4],x[5],ev(x[6])]) for x in f['last6'][:keep])
        rows.append([s,f['name'],f.get('nick') or 0,f['div'].replace(' Division','').replace("Women's ","W ") or 0,f.get('rec') or 0,
            f.get('stance') or 0,num(f.get('ht')) or 0,num(f.get('reach')) or 0,f.get('dob') or f.get('age') or 0,f.get('rank') or 0,f['ufc'],
            [num(st.get(k)) for k in SK] if st else 0,[f.get('ko'),f.get('sub'),f.get('dec'),f.get('r1')] if f.get('ko') is not None else 0,
            [r['ov'],r['g']['STR'],r['g']['WRE'],r['g']['GRA'],r['g']['DEF'],r['g']['CDU'],1 if r['thin'] else 0,1 if r['src']!='data' else 0,r['perf'],r.get('elo') or 0,r.get('res') or 0,r.get('skill') or 0,r.get('rank') or 0,r.get('sos') or 0,1 if r.get('capped') else 0,{'prospect':1,'small':2}.get(r.get('badge'),0)]+([] if page else [[[v for l,v in r['sub'][k]] for k in ('STR','WRE','GRA','DEF','CDU')] if r.get('sub') else 0]) if r else 0,
            fights]+([] if page else [f.get('img') or 0,f.get('lk') or 0]))
    cards=[]
    for e in d['events']:
        bs=[[b['sec'],b['wc'],IX.get(b['sa'],b['a']),IX.get(b['sb'],b['b']),b['ra'],b['rb'],b.get('est'),b.get('mkt'),b.get('ours'),b.get('mkt_books'),b.get('mkt_src')]+([] if page else [b.get('odds')]) for b in e['bouts']]
        cards.append([e['title'],e['date'],e['venue'],e['times'].get('main-card'),e['times'].get('prelims-card'),e['times'].get('early-prelims'),bs,e.get('iso')])
    rk=[[r['div'],IX.get(r['champ'],-1) if r['champ'] else -1,[IX[x] for x in r['list'] if x in IX]] for r in d['rankings']]
    news=[[n['date'],n['h'],n['cat'],n['conf'],[IX.get(x,x) for x in n['f']],n['url'],n['src']] for n in d['news']]
    out=dict(asof=d['asof'],ts=d.get('ts'),**({} if page else {'oasof':d.get('odds_asof')}),mirror_end=d['mirror_end'],fit=d['fit'],ev=EVN,f=rows,cards=cards,rk=rk,news=news)
    return out
if __name__=='__main__':
    for p in (True,False):
        j=json.dumps(compact(p),ensure_ascii=False,separators=(',',':')); print(p,len(j))
