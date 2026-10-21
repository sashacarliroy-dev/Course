"""Traduit un cours (leçons, récaps, exercices, formules) avec Google Traduction (gratuit).
Usage : python outils/traduire.py <cours> <en|es>
Garde les passages déjà traduits à la main dans langues/partiel/<cours>-<langue>.json."""
import json, re, sys, time, os
from deep_translator import GoogleTranslator

c, lg = sys.argv[1], sys.argv[2]
html = open("index.html", encoding="utf-8").read()
def bloc(i):
    m = re.search(r'<script type="application/json" id="%s">(.*?)</script>' % i, html, re.S)
    return json.loads(m.group(1)) if m else None
src = bloc("data-" + c)
src["exos"] = bloc("exos-" + c) or {}
src["formules"] = (bloc("formules-data") or {}).get(c, [])
partiel = {}
p = f"langues/partiel/{c}-{lg}.json"
if os.path.exists(p): partiel = json.load(open(p, encoding="utf-8"))

GARDER = {"debut", "type", "minutes", "bonne", "tol", "n", "lecon"}
tr = GoogleTranslator(source="fr", target=lg)
cache = {}

def g(t):
    if t in cache: return cache[t]
    for i in range(5):
        try:
            r = tr.translate(t) or t; cache[t] = r; return r
        except Exception as e:
            time.sleep(2 * (i + 1))
    return t

def traduire_texte(t):
    if not re.search(r"[A-Za-zÀ-ÿ]{2}", t): return t
    a = len(t) - len(t.lstrip()); b = len(t.rstrip())
    return t[:a] + g(t[a:b]) + t[b:]

def traduire_html(h):
    # on ne traduit que le texte entre les balises, par paquets de paragraphes
    morceaux = re.split(r"(<[^>]+>)", h)
    return "".join(m if m.startswith("<") else traduire_texte(m) for m in morceaux)

def deja(src_v, part_v):
    return isinstance(part_v, str) and part_v != src_v and part_v.strip() != ""

def walk(s, part, cle=""):
    if isinstance(s, dict):
        return {k: walk(v, part.get(k) if isinstance(part, dict) else None, k) for k, v in s.items()}
    if isinstance(s, list):
        return [walk(v, part[i] if isinstance(part, list) and i < len(part) else None, cle) for i, v in enumerate(s)]
    if not isinstance(s, str) or cle in GARDER: return s
    if deja(s, part): return part
    if cle == "mots": return s + ", " + g(s)
    return traduire_html(s) if "<" in s else traduire_texte(s)

out = walk(src, partiel)
os.makedirs("langues", exist_ok=True)
json.dump(out, open(f"langues/{c}-{lg}.json", "w", encoding="utf-8"), ensure_ascii=False)
print(c, lg, "ok", len(cache), "appels")
