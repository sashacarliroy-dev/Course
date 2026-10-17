#!/usr/bin/env python3
"""Met à jour les leçons d'un cours dans index.html (site Rosace).

Usage : python3 outils/maj_site.py <finance|trading> <page.html construite par build.py>
La page construite contient « const DATA = {...}; » : on recopie ce JSON
dans le bloc <script id="data-<cours>"> de index.html.
"""
import json, re, sys, pathlib

cours, source = sys.argv[1], sys.argv[2]
assert cours in ("finance", "trading"), "cours inconnu : " + cours
html = pathlib.Path(source).read_text(encoding="utf-8")
m = re.search(r"const DATA = (\{.*?\});\n", html, re.S)
if not m:
    sys.exit("DATA introuvable dans " + source)
data = json.loads(m.group(1))
bloc = json.dumps(data, ensure_ascii=False).replace("</", "<\\/")

site = pathlib.Path(__file__).resolve().parent.parent / "index.html"
page = site.read_text(encoding="utf-8")
motif = re.compile(r'(<script type="application/json" id="data-%s">)(.*?)(</script>)' % cours, re.S)
if not motif.search(page):
    sys.exit("Bloc data-%s introuvable dans index.html" % cours)
page = motif.sub(lambda x: x.group(1) + bloc + x.group(3), page, count=1)
site.write_text(page, encoding="utf-8")
print("%s : %d leçons publiées (dernière : %s)" % (cours, len(data["lecons"]), max(map(int, data["lecons"]))))
