"""Write ufc-stats-app.html (single-file app, data embedded so it works offline) and data.json (the same data, which the
page re-checks on load so a stale cached copy refreshes itself). Run after build_app_data.py."""
import json,os
from compact import compact
HERE=os.path.dirname(os.path.abspath(__file__))
obj=compact(False)
data=json.dumps(obj,ensure_ascii=False,separators=(',',':'))
open(HERE+'/data.json','w').write(data)
HTML=open(HERE+'/web/app.html').read()
open(HERE+'/ufc-stats-app.html','w').write(HTML.replace('__DATA__',data.replace('</','<\\/')))
print('wrote',len(HTML)+len(data))
