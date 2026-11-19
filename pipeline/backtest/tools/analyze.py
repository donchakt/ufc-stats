"""Minimal subset of the analyst's analyze.py needed by the app pipeline (name normalisation only)."""
import unicodedata
def norm(s): return ''.join(c for c in unicodedata.normalize('NFKD',s or '') if not unicodedata.combining(c)).replace('\u2019',"'").replace(' (c)','').lower().strip()
