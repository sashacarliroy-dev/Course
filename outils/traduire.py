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
    for i in range(6):
        try:
            r = tr.translate(t)
            if r: return r
        except Exception as e:
            print("erreur", e)
        time.sleep(5 * 2 ** i)  # Google limite : on attend de plus en plus longtemps
    return None

def _inutile(t):
    if not re.search(r"[A-Za-zÀ-ÿ]{2}", t): return t
    a = len(t) - len(t.lstrip()); b = len(t.rstrip())
    return t[:a] + g(t[a:b]) + t[b:]

def traduire_html(h):
    # on ne traduit que le texte entre les balises, par paquets de paragraphes
    morceaux = re.split(r"(<[^>]+>)", h)
    return "".join(m if m.startswith("<") else traduire_texte(m) for m in morceaux)

def deja(src_v, part_v):
    return isinstance(part_v, str) and part_v != src_v and part_v.strip() != ""

# 1) on collecte tous les textes à traduire, 2) on les envoie par paquets (~4500 caractères),
# 3) on reconstruit. Bien moins d'appels qu'un appel par phrase.
textes = []
def collecte(t):
    if re.search(r"[A-Za-zÀ-ÿ]{2}", t) and t.strip() not in cache: textes.append(t.strip())

def morceaux(s):
    return re.split(r"(<[^>]+>)", s) if "<" in s else [s]

def walk(s, part, cle, f):
    if isinstance(s, dict):
        return {k: walk(v, part.get(k) if isinstance(part, dict) else None, k, f) for k, v in s.items()}
    if isinstance(s, list):
        return [walk(v, part[i] if isinstance(part, list) and i < len(part) else None, cle, f) for i, v in enumerate(s)]
    if not isinstance(s, str) or cle in GARDER: return s
    if deja(s, part): return part
    return f(s, cle)

def f_collecte(s, cle):
    for m in morceaux(s):
        if not m.startswith("<"): collecte(m)
    return s

def remplace(t):
    if not re.search(r"[A-Za-zÀ-ÿ]{2}", t): return t
    a = len(t) - len(t.lstrip()); b = len(t.rstrip())
    return t[:a] + cache.get(t[a:b], t[a:b]) + t[b:]

def f_remplace(s, cle):
    r = "".join(m if m.startswith("<") else remplace(m) for m in morceaux(s))
    return s + ", " + r if cle == "mots" else r

walk(src, partiel, "", f_collecte)
uniques = list(dict.fromkeys(t.replace("\n", " ") for t in textes))
paquet = []
def envoyer(p):
    if not p: return
    time.sleep(3)
    r = g("\n".join(p))
    res = r.split("\n") if r else []
    if len(res) == len(p):
        for a, b in zip(p, res): cache[a] = b.strip()
    elif len(p) > 1:
        m = len(p) // 2; envoyer(p[:m]); envoyer(p[m:])
taille = 0
for i, t in enumerate(uniques):
    if taille + len(t) > 4500: envoyer(paquet); paquet, taille = [], 0
    paquet.append(t); taille += len(t) + 1
envoyer(paquet)
# textes qui contenaient des retours à la ligne
for t in textes:
    if "\n" in t and t not in cache: cache[t] = cache.get(t.replace("\n", " "), t)

out = walk(src, partiel, "", f_remplace)
os.makedirs("langues", exist_ok=True)
json.dump(out, open(f"langues/{c}-{lg}.json", "w", encoding="utf-8"), ensure_ascii=False)
print(c, lg, "ok", len(uniques), "textes,", sum(1 for t in uniques if t not in cache), "non traduits")
