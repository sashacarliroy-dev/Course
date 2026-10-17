#!/usr/bin/env python3
"""Met à jour les leçons d'un cours dans index.html (site Rosace).

Usage : python3 outils/maj_site.py <finance|trading> <page.html construite par build.py>
La page construite contient « const DATA = {...}; ». Depuis que les 40 leçons sont
dans index.html, on n'ajoute que les leçons qui manquent : celles déjà présentes
ne sont jamais écrasées ni supprimées.
"""
import json, re, sys, pathlib

cours, source = sys.argv[1], sys.argv[2]
assert cours in ("finance", "trading"), "cours inconnu : " + cours
html = pathlib.Path(source).read_text(encoding="utf-8")
m = re.search(r"const DATA = (\{.*?\});\n", html, re.S)
if not m:
    sys.exit("DATA introuvable dans " + source)
source_data = json.loads(m.group(1))

site = pathlib.Path(__file__).resolve().parent.parent / "index.html"
page = site.read_text(encoding="utf-8")
motif = re.compile(r'(<script type="application/json" id="data-%s">)(.*?)(</script>)' % cours, re.S)
actuel = motif.search(page)
if not actuel:
    sys.exit("Bloc data-%s introuvable dans index.html" % cours)
data = json.loads(actuel.group(2).replace("<\\/", "</"))
ajoutees = [n for n in source_data["lecons"] if n not in data["lecons"]]
for n in ajoutees:
    data["lecons"][n] = source_data["lecons"][n]
data["lecons"] = dict(sorted(data["lecons"].items(), key=lambda kv: int(kv[0])))
bloc = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")
page = motif.sub(lambda x: x.group(1) + bloc + x.group(3), page, count=1)
site.write_text(page, encoding="utf-8")
print("%s : %d leçons dans le site, %d ajoutée(s)" % (cours, len(data["lecons"]), len(ajoutees)))
