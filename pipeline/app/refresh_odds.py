#!/usr/bin/env python3
"""Refresh betting odds for the Fight Stats site from public BestFightOdds pages.

1. Re-fetches the BestFightOdds index + every UFC event page listed on it (public pages only).
2. Parses each fight's moneyline per book, then works out the consensus (median) line, best line + book,
   no-vig implied win % (median across books quoting both sides), the number of books, and the opening line
   (from the first-listed fighter's public BFO page; cached in cache/bfo/open.json since openers never change).
3. Writes cache/odds.json (only when the lines changed, so the stamp is the time of the last change) and prints
   ODDS_CHANGED=1/0. Building and publishing are done by run.py (GitHub Actions workflow).
Exit code 2 = BestFightOdds could not be fetched or parsed (cached odds kept).

Usage: python3 refresh_odds.py [--force]
Nothing is ever invented: a bout with no posted lines gets no odds.
"""
import re, os, sys, json, time, html, glob, shutil, hashlib, subprocess, datetime as dt, statistics as stx
HERE = os.path.dirname(os.path.abspath(__file__)); C = HERE + '/cache/'; B = C + 'bfo/'
ARG = set(sys.argv[1:]); T0 = time.time()
CST = dt.timezone(dt.timedelta(hours=-6))
def log(*a): print(f'[{time.time()-T0:5.1f}s]', *a, flush=True)
def get(url, path):
    for k in range(3):
        r = subprocess.run(['curl', '-s', '-m', '40', '-A', 'Mozilla/5.0 (compatible; ufc-stats-fan-app/1.0; +https://github.com/donchakt/ufc-stats)',
                            '-o', path + '.tmp', '-w', '%{http_code}', url], capture_output=True, text=True)
        if r.stdout == '200' and os.path.getsize(path + '.tmp') > 3000:
            os.replace(path + '.tmp', path); return True
        time.sleep(2 + 3 * k)
    if os.path.exists(path + '.tmp'): os.remove(path + '.tmp')
    return False
def dec(o): return 1 + (o / 100 if o > 0 else 100 / -o)
def amer(d): return round((d - 1) * 100) if d >= 2 else round(-100 / (d - 1))
def imp(o): return 100 / (o + 100) if o > 0 else -o / (-o + 100)

# 1. fetch
os.makedirs(B + 'fighters', exist_ok=True); os.makedirs(B + 'old', exist_ok=True)
if not get('https://www.bestfightodds.com/', B + 'index.html'): print('CRITICAL could not fetch BestFightOdds index'); sys.exit(2)
evs = sorted(set(re.findall(r'href="/events/(ufc-[a-z0-9-]+)"', open(B + 'index.html').read())))
for f in glob.glob(B + 'ufc-*.html'):                       # retire event pages no longer listed
    if os.path.basename(f)[:-5] not in evs: shutil.move(f, B + 'old/' + os.path.basename(f))
ok = [e for e in evs if time.sleep(0.5) is None and get('https://www.bestfightodds.com/events/' + e, B + e + '.html')]
log(f'fetched {len(ok)}/{len(evs)} UFC event pages')

# 2. parse
bouts = []
for e in ok:
    t = open(B + e + '.html').read(); i = t.find('<table class="odds-table">')
    if i < 0: continue
    tb = t[i:t.find('</table>', i)]
    books = {k: html.unescape(v).strip() for k, v in re.findall(r'data-b="(\d+)">(?:<a[^>]*>|<span[^>]*>)([^<]+)', tb)}
    title = html.unescape(re.search(r'<title>(.*?)</title>', t, re.S).group(1)).split(' Odds')[0].strip()
    mu = {}
    for r in re.findall(r'<tr[^>]*>(.*?)</tr>', tb, re.S):
        nm = re.search(r'href="/fighters/([^"]+)"><span[^>]*>([^<]+)</span>', r)
        if not nm: continue
        for bk, side, m, o in re.findall(r'data-li="\[(\d+),(\d),(\d+)\]"><span[^>]*>([+-]\d+)</span>', r):
            s = mu.setdefault(m, {}).setdefault(side, {'name': html.unescape(nm.group(2)).strip(), 'slug': nm.group(1), 'o': {}})
            s['o'][books.get(bk, 'Book ' + bk)] = int(o)
    for m, sd in mu.items():
        if set(sd) != {'1', '2'}: continue
        both = sorted(set(sd['1']['o']) & set(sd['2']['o']))
        if not both: continue
        nv = sorted(imp(sd['1']['o'][k]) / (imp(sd['1']['o'][k]) + imp(sd['2']['o'][k])) for k in both)
        row = dict(mu=int(m), event=title, url='https://www.bestfightodds.com/events/' + e, n=len(both), p1=round(stx.median(nv), 4))
        for s in '12':
            o = sd[s]['o']; bk = max(o, key=lambda k: (dec(o[k]), -list(o).index(k)))
            row['f' + s] = dict(name=sd[s]['name'], slug=sd[s]['slug'], med=amer(stx.median(dec(v) for v in o.values())),
                                best=o[bk], book=bk, nb=len(o))
        bouts.append(row)
log(f'parsed {len(bouts)} bouts with lines')

# 3. opening lines (cached; fetched from the first fighter's public BFO page for new matchups)
OP = B + 'open.json'; opens = json.load(open(OP)) if os.path.exists(OP) else {}
for b in bouts:
    k = str(b['mu'])
    if k not in opens:
        fp = B + 'fighters/' + b['f1']['slug'] + '.html'
        if get('https://www.bestfightodds.com/fighters/' + b['f1']['slug'], fp):
            t = open(fp).read(); p = t.find(f'data-li="[{k},1]"')
            if p > 0:
                r1 = t[t.rfind('<tr class="main-row">', 0, p):p]; e2 = t.find('</tr>', p); r2 = t[e2:t.find('</tr>', e2 + 5)]
                o1 = re.search(r'class="moneyline"[^>]*><span[^>]*>([+-]\d+)</span>', r1); o2 = re.search(r'class="moneyline"[^>]*><span[^>]*>([+-]\d+)</span>', r2)
                if o1 and o2: opens[k] = [int(o1.group(1)), int(o2.group(1))]
        time.sleep(0.3)
    if k in opens: b['f1']['open'], b['f2']['open'] = opens[k]
json.dump(opens, open(OP, 'w'))
log(f'opening lines for {sum(1 for b in bouts if "open" in b["f1"])}/{len(bouts)} bouts')

# 4. write + change check
REP = dict(index_events=len(evs), fetched=len(ok), bouts=len(bouts), failed=[e for e in evs if e not in ok])
json.dump(REP, open(C + 'odds_report.json', 'w'), indent=1)
OJ = C + 'odds.json'; old = json.load(open(OJ)) if os.path.exists(OJ) else {}
if evs and not bouts and old.get('bouts'):
    print('CRITICAL BestFightOdds pages fetched but no odds parsed (layout change?) - kept the last good odds'); sys.exit(2)
new = dict(asof=dt.datetime.now(CST).strftime('%b %-d, %Y %-I:%M %p') + ' CST', bouts=sorted(bouts, key=lambda x: x['mu']))
changed = old.get('bouts') != new['bouts']
if changed or not old or '--force' in ARG:
    json.dump(new, open(OJ, 'w'), ensure_ascii=False, indent=0)
log('odds changed' if changed else 'odds unchanged since ' + str(old.get('asof')))
print('ODDS_CHANGED=' + ('1' if changed else '0'))
