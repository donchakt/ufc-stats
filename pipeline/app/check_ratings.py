"""Sanity checks for ratings v2: named fighters, top/bottom, per-division Spearman vs UFC rankings."""
import json,sys,datetime as dt
sys.path.insert(0,'.'); import ratings as R
d=json.load(open('app-data.json')); F=d['fighters']
def sp(x,y):
    n=len(x)
    def rk(v):
        o=sorted(range(n),key=lambda i:v[i]); r=[0]*n; i=0
        while i<n:
            j=i
            while j+1<n and v[o[j+1]]==v[o[i]]: j+=1
            for t in range(i,j+1): r[o[t]]=(i+j)/2
            i=j+1
        return r
    a,b=rk(x),rk(y); ma=sum(a)/n; mb=sum(b)/n
    num=sum((p-ma)*(q-mb) for p,q in zip(a,b)); den=(sum((p-ma)**2 for p in a)*sum((q-mb)**2 for q in b))**.5
    return num/den if den else float('nan')
out={}
for r in d['rankings']:
    if 'Pound' in r['div']: continue
    L=([r['champ']] if r['champ'] else [])+r['list']
    pos=list(range(len(L)))
    ov=[F[s]['rating']['ov'] if F.get(s) and F[s].get('rating') else None for s in L]
    ok=[(p,o) for p,o in zip(pos,ov) if o is not None]
    rho=sp([-p for p,_ in ok],[o for _,o in ok])
    champ=F[r['champ']]['rating']['ov'] if r['champ'] and F[r['champ']].get('rating') else None
    out[r['div']]=dict(rho=round(rho,2),n=len(ok),champ=champ,top=max(o for _,o in ok),inv=[(F[L[p]]['name'],o) for p,o in ok if champ and o>champ])
    print(f"{r['div']:22s} rho={rho:.2f} n={len(ok)} champ={champ} " + ' '.join(f"{F[s]['name'].split()[-1]}:{o}" for s,o in zip(L,ov)))
# unranked above champ of own division
divchamp={}
for r in d['rankings']:
    if r['champ'] and 'Pound' not in r['div']: divchamp[r['div']]=F[r['champ']]['rating']['ov']
bad=[]
for s,f in F.items():
    if f.get('rating') and not f.get('rank'):
        dv=(f['div'] or '').replace(' Division','')
        c=divchamp.get(dv)
        if c and f['rating']['ov']>=c: bad.append((f['name'],f['rating']['ov'],dv,c))
print('unranked >= own champ:',bad)
rated=sorted([(f['rating']['ov'],f['name'],f.get('rank')) for f in F.values() if f.get('rating')],reverse=True)
print('top',rated[:6]); print('bottom',rated[-6:])
json.dump(out,open('spearman.json','w'),indent=1)
