"""Fabrique l'audio (voix naturelle, gratuite et libre : Piper) de chaque leçon, une piste par partie (titre <h2>).
Usage : python outils/audio.py <cours> <dossier_modele>  -> écrit audio/<cours>/<lecon>/<k>.mp3 et audio/<cours>.json
Ne refait pas les pistes déjà présentes."""
import html, json, os, re, subprocess, sys, wave, tempfile

cours, modele = sys.argv[1], sys.argv[2]
page = open("index.html", encoding="utf-8").read()
d = json.loads(re.search(r'id="data-%s">(.*?)</script>' % cours, page, re.S).group(1))

def texte(h):
    h = re.sub(r"<sup>(.*?)</sup>", r" puissance \1 ", h)
    h = re.sub(r"</(p|li|h2|h3|h4|tr|div|blockquote)>", ". ", h)
    h = re.sub(r"<td[^>]*>", " ", h)
    t = html.unescape(re.sub(r"<[^>]+>", " ", h))
    t = t.replace("^", " puissance ").replace("×", " fois ").replace("÷", " divisé par ").replace("≈", " environ ")
    t = t.replace("€", " euros ").replace("%", " pour cent ").replace("→", ", ").replace("≥", " supérieur ou égal à ").replace("≤", " inférieur ou égal à ")
    t = re.sub(r"(\d) (\d{3})", r"\1\2", t)
    t = re.sub(r"\s*\.\s*(\.\s*)+", ". ", t)
    return re.sub(r"\s+", " ", t).strip(" .") + "."

def parties(titre, h):
    morceaux = re.split(r"(?=<h2[ >])", h)
    out = []
    for i, m in enumerate(morceaux):
        t = texte(m)
        if i == 0: t = titre + ". " + t if len(t) > 2 else titre + "."
        if len(t) > 2: out.append(t)
    return out

lecons = {**{str(k): v for k, v in d["lecons"].items()}, **{str(100 + int(k)): v for k, v in d.get("recaps", {}).items()}}
manifeste = {}
for n, l in sorted(lecons.items(), key=lambda x: int(x[0])):
    titre = l.get("titre") or ("Récap du module " + str(int(n) - 100))
    ps = parties(titre, l["html"])
    dossier = f"audio/{cours}/{n}"; os.makedirs(dossier, exist_ok=True)
    for k, t in enumerate(ps):
        mp3 = f"{dossier}/{k}.mp3"
        if os.path.exists(mp3): continue
        with tempfile.NamedTemporaryFile(suffix=".wav") as w:
            subprocess.run(["piper", "--model", modele, "--output_file", w.name, "--length_scale", "1.0", "--sentence_silence", "0.25"], input=t.encode(), check=True, capture_output=True)
            subprocess.run(["ffmpeg", "-y", "-loglevel", "error", "-i", w.name, "-ac", "1", "-ar", "22050", "-b:a", "32k", mp3], check=True)
    manifeste[n] = len(ps)
    print(cours, n, len(ps), "parties", flush=True)
json.dump(manifeste, open(f"audio/{cours}.json", "w"))
