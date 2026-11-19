"""Area scores v4 (2026-11-10): opponent-adjusted, recency-weighted sub-scores on a smooth scale (no hard cap at 10).

For every UFC fight before the cutoff (UFCStats per-round data via data_ratings.FIGHTS):
  weight w = 0.85^(fights ago) * q,  q = clip(exp((opponent pre-fight Elo - 1500)/250), 0.5, 2.0)
  so recent fights and fights against strong opponents count more; padding stats against weak opposition counts less.
Opponent adjustment: each rate is compared with what that opponent usually allows (or usually lands, for defence),
  shrunk toward the league mean; adjusted = own weighted rate - (expected vs those opponents - league mean).
Every sub-metric is turned into a z-score vs all UFC fighters with 3+ fights active in the last 6 years,
  shrunk for small samples (z * n/(n+2)), and mapped smoothly: sub-score = 1 + 8.9/(1+exp(-z)) (1.0-9.9; z=0 -> 5.45). Area = weighted blend of sub z's, re-standardised,
  mapped with a flatter slope 1 + 8.9/(1+exp(-0.85 z)) so only z >= ~3.6 (truly elite) reaches 9.5.
  Striking   : Output .20, Accuracy .15, Defence .15, Differential .20, Power .15, Opp. quality .15
  Wrestling  : TD rate .45, TD accuracy .35, Opp. quality .20
  Grappling  : Sub attempts .35, Sub finishes .35, Sub defence .15, Opp. quality .15
  Defence    : Str. defence .25, Absorbed .25, TD defence .20, Durability .20, Opp. quality .10
  Cardio     : Late output .35, Late differential .30, Durability .20, Opp. quality .15
"""
import math, datetime as dt, statistics as stx
import ratings as R
DR = R.DR
AREAS = {
 'STR': [('out', 'Output', .20), ('acc', 'Accuracy', .15), ('sdef', 'Defence', .15), ('diff', 'Differential', .20), ('pow', 'Power', .15), ('oq', 'Opp. quality', .15)],
 'WRE': [('td', 'TD rate', .45), ('tdacc', 'TD accuracy', .35), ('oq', 'Opp. quality', .20)],
 'GRA': [('subatt', 'Sub attempts', .35), ('subfin', 'Sub finishes', .35), ('subdef', 'Sub defence', .15), ('oq', 'Opp. quality', .15)],
 'DEF': [('sdef', 'Str. defence', .25), ('abs', 'Absorbed', .25), ('tdd', 'TD defence', .20), ('dur', 'Durability', .20), ('oq', 'Opp. quality', .10)],
 'CDU': [('late', 'Late output', .35), ('ldiff', 'Late differential', .30), ('dur', 'Durability', .20), ('oq', 'Opp. quality', .15)],
}
SHR = 4.; ASL = 0.85; SSL = 1.0
def M(z, a=1.25): return 1 + 8.9 / (1 + math.exp(-a * z))
def _tot(f):
    t = {'me': dict(kd=0, sl=0, sa=0, td=0, tda=0, sub=0), 'op': dict(kd=0, sl=0, sa=0, td=0, tda=0, sub=0)}
    for rn, pr in f['per'].items():
        for s in ('me', 'op'):
            for k in t[s]: t[s][k] += pr[s].get(k, 0)
    return t
_PRE = None
def _pre():
    global _PRE
    if _PRE is None:
        _PRE = {}
        for d, a, b, ra, rb, S, na, nb in R.E().hist: _PRE[(d, a)] = rb; _PRE[(d, b)] = ra
    return _PRE
def _fights(name, cut): return sorted([f for f in DR.FIGHTS.get(name, []) if f['date'] < cut], key=lambda f: f['date'])
def _career(name, cut):
    """Unweighted career totals used as an opponent's 'usually allows / usually lands' profile."""
    S = dict(m=0., sl=0, osl=0, sa=0, osa=0, sla=0, osla=0, td=0, otd=0, tda=0, otda=0, tdl=0, otdl=0, sub=0, osub=0, kd=0, okd=0)
    for f in _fights(name, cut):
        t = _tot(f); S['m'] += f['mins']
        S['sl'] += t['me']['sl']; S['osl'] += t['op']['sl']; S['kd'] += t['me']['kd']; S['okd'] += t['op']['kd']
        S['td'] += t['me']['td']; S['otd'] += t['op']['td']; S['sub'] += t['me']['sub']; S['osub'] += t['op']['sub']
        if f['attempts']:
            S['sla'] += t['me']['sl']; S['sa'] += t['me']['sa']; S['osla'] += t['op']['sl']; S['osa'] += t['op']['sa']
            S['tdl'] += t['me']['td']; S['tda'] += t['me']['tda']; S['otdl'] += t['op']['td']; S['otda'] += t['op']['tda']
    return S
class Model:
    def __init__(self, cutoff):
        self.cut = dt.date.fromisoformat(cutoff) if isinstance(cutoff, str) else cutoff
        self.C = {}
        pop = [n for n, fs in DR.FIGHTS.items() if len([f for f in fs if f['date'] < self.cut]) >= 3
               and max(f['date'] for f in fs if f['date'] < self.cut) >= self.cut - dt.timedelta(days=6 * 365)]
        # league means
        T = dict(m=0., sl=0, sla=0, sa=0, td=0, tdl=0, tda=0, sub=0, kd=0)
        for n in pop:
            c = self.car(n)
            for k in T: T[k] += c[k]
        self.L = dict(slpm=T['sl'] / T['m'], acc=T['sla'] / T['sa'], td15=15 * T['td'] / T['m'], tdacc=T['tdl'] / T['tda'],
                      sub15=15 * T['sub'] / T['m'], kd15=15 * T['kd'] / T['m'])
        raws = {n: self.raw(n) for n in pop}
        self.mu, self.sd = {}, {}
        for k in raws[pop[0]]:
            if k in ('n', '_show'): continue
            v = sorted(r[k] for r in raws.values() if r.get(k) is not None)
            lo, hi = v[int(.01 * len(v))], v[int(.99 * len(v)) - 1]
            v = [min(hi, max(lo, x)) for x in v]
            self.mu[k] = stx.mean(v); self.sd[k] = stx.pstdev(v) or 1; self.clip = getattr(self, 'clip', {}); self.clip[k] = (lo, hi)
        self.asd = {}
        for a in AREAS:
            zs = [self._az(a, self.zs(r)) for r in raws.values()]
            self.asd[a] = stx.pstdev(zs) or 1
        self.npop = len(pop)
    def car(self, n):
        if n not in self.C: self.C[n] = _career(n, self.cut)
        return self.C[n]
    def raw(self, name):
        fs = _fights(name, self.cut)[::-1]
        if not fs: return None
        L = self.L; P = _pre()
        A = dict(w=0., wm=0., sl=0., osl=0., e_sl=0., e_osl=0., sla=0., sa=0., e_acc=0., wa=0., osla=0., osa=0., e_oacc=0., woa=0.,
                 td=0., e_td=0., tdl=0., tda=0., e_tdacc=0., wt=0., otdl=0., otda=0., e_otdacc=0., wot=0.,
                 sub=0., e_sub=0., kd=0., e_kd=0., okd=0., e_okd=0., ko=0., subw=0., subl=0., kol=0., wf=0.,
                 lsl=0., losl=0., lm=0., esl=0., em=0., oq=0., wq=0.)
        sh = lambda x, m, l, k=30.: (x + k * l) / (m + k)     # opponent profile shrunk toward league (k minutes)
        for i, f in enumerate(fs):
            op = f['opp']; oe = P.get((f['date'], name)); q = min(2., max(.5, math.exp(((oe or 1500) - 1500) / 250)))
            w = .85 ** i * q; m = max(f['mins'], .5); t = _tot(f); c = self.car(op)
            cm = c['m']
            # opponent's usual: strikes allowed/min, strikes landed/min, acc allowed, acc landed, td allowed, ...
            a_sl = sh(c['osl'], cm, L['slpm']); u_sl = sh(c['sl'], cm, L['slpm'])
            a_td = sh(c['otd'] * 1., cm, L['td15'] / 15); a_sub = sh(c['osub'] * 1., cm, L['sub15'] / 15)
            a_kd = sh(c['okd'] * 1., cm, L['kd15'] / 15); u_kd = sh(c['kd'] * 1., cm, L['kd15'] / 15)
            A['w'] += w; A['wm'] += w * m; A['wf'] += w
            A['sl'] += w * t['me']['sl']; A['osl'] += w * t['op']['sl']; A['e_sl'] += w * m * a_sl; A['e_osl'] += w * m * u_sl
            A['td'] += w * t['me']['td']; A['e_td'] += w * m * a_td; A['sub'] += w * t['me']['sub']; A['e_sub'] += w * m * a_sub
            A['kd'] += w * t['me']['kd']; A['e_kd'] += w * m * a_kd; A['okd'] += w * t['op']['kd']; A['e_okd'] += w * m * u_kd
            if f['attempts']:
                A['sla'] += w * t['me']['sl']; A['sa'] += w * t['me']['sa']; A['e_acc'] += w * t['me']['sa'] * sh(c['osla'], c['osa'], L['acc'], 60)
                A['osla'] += w * t['op']['sl']; A['osa'] += w * t['op']['sa']; A['e_oacc'] += w * t['op']['sa'] * sh(c['sla'], c['sa'], L['acc'], 60)
                A['tdl'] += w * t['me']['td']; A['tda'] += w * t['me']['tda']; A['e_tdacc'] += w * t['me']['tda'] * sh(c['otdl'], c['otda'], L['tdacc'], 8)
                A['otdl'] += w * t['op']['td']; A['otda'] += w * t['op']['tda']; A['e_otdacc'] += w * t['op']['tda'] * sh(c['tdl'], c['tda'], L['tdacc'], 8)
                if f['round'] >= 3:
                    for rn, pr in f['per'].items():
                        mm = 5. if int(rn) < f['round'] else f['last_sec'] / 60
                        if int(rn) >= 3: A['lsl'] += w * pr['me']['sl']; A['losl'] += w * pr['op']['sl']; A['lm'] += w * mm
                        elif int(rn) >= 1: A['esl'] += w * pr['me']['sl']; A['em'] += w * mm
            met = f['method'].upper(); won = f['wl'] == 'W'; lost = f['wl'] == 'L'
            A['ko'] += w * (won and 'KO' in met); A['subw'] += w * (won and 'SUB' in met)
            A['subl'] += w * (lost and 'SUB' in met); A['kol'] += w * (lost and 'KO' in met)
            if i < 6 and oe: A['oq'] += .8 ** i * oe; A['wq'] += .8 ** i
        M0 = 15.  # pseudo-minutes at league average
        wm = A['wm']; adj = lambda x, e, l: (x - (e - l * wm) + M0 * l) / (wm + M0)
        out = adj(A['sl'], A['e_sl'], L['slpm']); absb = adj(A['osl'], A['e_osl'], L['slpm'])
        acc = ((A['sla'] - (A['e_acc'] - L['acc'] * A['sa'])) + 60 * L['acc']) / (A['sa'] + 60) if A['sa'] else L['acc']
        oacc = ((A['osla'] - (A['e_oacc'] - L['acc'] * A['osa'])) + 60 * L['acc']) / (A['osa'] + 60) if A['osa'] else L['acc']
        tdacc = ((A['tdl'] - (A['e_tdacc'] - L['tdacc'] * A['tda'])) + 8 * L['tdacc']) / (A['tda'] + 8) if A['tda'] else L['tdacc']
        otdacc = ((A['otdl'] - (A['e_otdacc'] - L['tdacc'] * A['otda'])) + 8 * L['tdacc']) / (A['otda'] + 8) if A['otda'] else L['tdacc']
        td15 = 15 * adj(A['td'], A['e_td'], L['td15'] / 15); sub15 = 15 * adj(A['sub'], A['e_sub'], L['sub15'] / 15)
        kd15 = 15 * adj(A['kd'], A['e_kd'], L['kd15'] / 15); okd15 = 15 * adj(A['okd'], A['e_okd'], L['kd15'] / 15)
        rate = lambda x, p, k=3.: (x + k * p) / (A['wf'] + k)
        ko = rate(A['ko'], .17); subw = rate(A['subw'], .08); subl = rate(A['subl'], .08); kol = rate(A['kol'], .12)
        late = ((A['lsl'] / A['lm']) / (A['esl'] / A['em'])) if A['lm'] > 2 and A['em'] > 2 and A['esl'] > 0 else 1.
        lw = A['lm'] / (A['lm'] + 10); late = 1 + (late - 1) * lw
        ldiff = ((A['lsl'] - A['losl']) / (A['lm'] + 10))
        oq = A['oq'] / A['wq'] if A['wq'] else 1500.
        return dict(n=len(fs), out=out, acc=acc, sdef=1 - oacc, diff=out - absb, pow=.5 * kd15 / (L['kd15'] or 1) + .5 * ko / .17,
                    oq=oq, td=td15, tdacc=tdacc, subatt=sub15, subfin=subw, subdef=-subl, abs=-absb, tdd=1 - otdacc,
                    dur=-(.6 * kol / .12 + .4 * okd15 / (L['kd15'] or 1)), late=late, ldiff=ldiff,
                    _show=dict(SLpM=round(out, 2), acc=round(100 * acc), SApM=round(absb, 2), strdef=round(100 * (1 - oacc)), KD15=round(kd15, 2), oq=round(oq)))
    def zs(self, r):
        n = r['n']; s = n / (n + SHR)
        out = {}
        for k in self.mu:
            lo, hi = self.clip[k]; x = min(hi, max(lo, r[k]))
            out[k] = s * (x - self.mu[k]) / self.sd[k] if k != 'oq' else (x - self.mu[k]) / self.sd[k] * min(1, n / 4)
        return out
    def _az(self, a, z): return sum(w * z[k] for k, _, w in AREAS[a])
    def score(self, name):
        r = self.raw(name)
        if not r: return None
        z = self.zs(r)
        g, sub = {}, {}
        for a in AREAS:
            g[a] = round(M(self._az(a, z) / self.asd[a], ASL), 1)
            sub[a] = [[lab, round(M(z[k], SSL), 1)] for k, lab, _ in AREAS[a]]
        return dict(g=g, sub=sub, n=r['n'], raw=r['_show'])
_MC = {}
def model(cutoff):
    if cutoff not in _MC: _MC[cutoff] = Model(cutoff)
    return _MC[cutoff]
if __name__ == '__main__':
    import sys, time
    t = time.time(); m = model('2026-11-11'); print('pop', m.npop, 'build', round(time.time() - t, 1), 's')
    for n in sys.argv[1:] or ['Ciryl Gane', 'Josh Hokit', 'Islam Makhachev', 'Max Holloway', 'Alex Pereira', 'Merab Dvalishvili']:
        print(n, m.score(n))
