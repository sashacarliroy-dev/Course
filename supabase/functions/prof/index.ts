// Fonction Supabase « prof » : relaie les questions de l'assistant du site vers Gemini (Google)
// et renvoie la réponse au fil de l'eau, au format attendu par index.html.
// La clé reste côté serveur : secret GEMINI_API_KEY (Supabase > Edge Functions > Secrets).

// Plusieurs modèles gratuits essayés à la suite : quand le quota gratuit de l'un est épuisé (erreur 429), on passe au suivant.
// Dernier recours facultatif : Groq (gratuit, secret GROQ_API_KEY), si la clé est enregistrée.
const MODELES = [...new Set([
  (Deno.env.get("GEMINI_MODEL") || "").trim(),
  "gemini-2.5-flash-lite", "gemini-flash-lite-latest", "gemini-2.0-flash", "gemini-2.0-flash-lite", "gemini-2.5-flash", "gemini-flash-latest",
].filter(Boolean))];
const MODELE_GROQ = Deno.env.get("GROQ_MODEL") || "llama-3.3-70b-versatile";
const CORS = {
  "Access-Control-Allow-Origin": "*",
  "Access-Control-Allow-Headers": "authorization, apikey, content-type, x-client-info",
  "Access-Control-Allow-Methods": "POST, OPTIONS",
};
const json = (corps: unknown, status = 200) =>
  new Response(JSON.stringify(corps), { status, headers: { ...CORS, "content-type": "application/json" } });

Deno.serve(async (req) => {
  if (req.method === "OPTIONS") return new Response("ok", { headers: CORS });
  if (req.method !== "POST") return json({ erreur: "Méthode non autorisée." }, 405);
  // trim : un espace ou un retour à la ligne collé avec la clé suffit à la faire refuser
  const cle = (Deno.env.get("GEMINI_API_KEY") || "").trim();
  if (!cle) return json({ erreur: "La clé de l'IA n'est pas encore enregistrée sur Supabase." }, 500);

  let systeme = "", messages: { role: string; content: string }[] = [];
  try { ({ systeme, messages } = await req.json()); } catch { return json({ erreur: "Requête illisible." }, 400); }
  if (typeof systeme !== "string" || !Array.isArray(messages) || !messages.length) return json({ erreur: "Requête incomplète." }, 400);
  // Garde-fous : on limite la taille pour protéger le quota gratuit
  systeme = systeme.slice(0, 60000);
  messages = messages.slice(-12).map((m) => ({ role: m.role === "assistant" ? "model" : "user", content: String(m.content || "").slice(0, 4000) }));

  const corpsPour = (modele: string) => JSON.stringify({
    systemInstruction: { parts: [{ text: systeme }] },
    contents: messages.map((m) => ({ role: m.role, parts: [{ text: m.content }] })),
    generationConfig: { maxOutputTokens: 1500, temperature: 0.6, ...(/2\.0/.test(modele) ? {} : { thinkingConfig: { thinkingBudget: 0 } }) },
  });
  // Google propose plusieurs formats de clé (AIza…, AQ.…) : on essaie les façons de la transmettre une par une
  const appelGemini = async (modele: string) => {
    const url = `https://generativelanguage.googleapis.com/v1beta/models/${modele}:streamGenerateContent?alt=sse`;
    const essais: [string, Record<string, string>][] = [
      [url, { "x-goog-api-key": cle }],
      [url + "&key=" + encodeURIComponent(cle), {}],
      [url, { authorization: "Bearer " + cle }],
    ];
    let rep = new Response(null, { status: 500 });
    for (const [u, h] of essais) {
      rep = await fetch(u, { method: "POST", headers: { "content-type": "application/json", ...h }, body: corpsPour(modele) });
      if (rep.ok || ![400, 401, 403].includes(rep.status)) break;
      const detail = await rep.clone().text().catch(() => "");
      if (!/API key|API_KEY|credential|authenticat/i.test(detail)) break;
      console.error("Clé refusée sous cette forme, essai suivant", rep.status, detail.slice(0, 200));
    }
    return rep;
  };
  let r = new Response(null, { status: 500 });
  for (const modele of MODELES) {
    r = await appelGemini(modele);
    if (r.ok && r.body) break;
    const detail = await r.text().catch(() => "");
    console.error("Gemini", modele, r.status, detail.slice(0, 300));
    // Quota épuisé, modèle inconnu ou surchargé : on tente le modèle suivant
    if (![429, 404, 500, 503].includes(r.status) && !(r.status === 400 && /model|not found|not supported/i.test(detail))) break;
  }
  if (!r.ok || !r.body) {
    const groq = (Deno.env.get("GROQ_API_KEY") || "").trim();
    if (groq) {
      const g = await fetch("https://api.groq.com/openai/v1/chat/completions", {
        method: "POST", headers: { "content-type": "application/json", authorization: "Bearer " + groq },
        body: JSON.stringify({ model: MODELE_GROQ, stream: true, max_tokens: 1500, temperature: 0.6,
          messages: [{ role: "system", content: systeme.slice(0, 24000) }, ...messages.map((m) => ({ role: m.role === "model" ? "assistant" : "user", content: m.content }))] }),
      });
      if (g.ok && g.body) return fluxDepuis(g, "groq");
      console.error("Groq", g.status, (await g.text().catch(() => "")).slice(0, 300));
    }
    return json({ erreur: r.status === 429 ? "Beaucoup de questions en ce moment : réessaie dans une minute." : "L'IA ne répond pas pour le moment." }, r.status === 429 ? 429 : 502);
  }
  return fluxDepuis(r, "gemini");
});

// Conversion du flux Gemini (ou Groq) en événements « content_block_delta » / « message_delta »
function fluxDepuis(r: Response, source: "gemini" | "groq") {
  const enc = new TextEncoder(), dec = new TextDecoder();
  const envoyer = (c: ReadableStreamDefaultController, o: unknown) => c.enqueue(enc.encode(`data: ${JSON.stringify(o)}\n\n`));
  const flux = new ReadableStream({
    async start(c) {
      const lecteur = r.body!.getReader(); let tampon = "", fin = "";
      try {
        for (;;) {
          const { value, done } = await lecteur.read(); if (done) break;
          tampon += dec.decode(value, { stream: true });
          let i; while ((i = tampon.indexOf("\n")) >= 0) {
            const ligne = tampon.slice(0, i).trim(); tampon = tampon.slice(i + 1);
            if (!ligne.startsWith("data:")) continue;
            const brut = ligne.slice(5).trim(); if (brut === "[DONE]") continue;
            let j; try { j = JSON.parse(brut); } catch { continue; }
            if (source === "groq") {
              const ch = j.choices && j.choices[0];
              if (ch && ch.delta && ch.delta.content) envoyer(c, { type: "content_block_delta", delta: { text: ch.delta.content } });
              if (ch && ch.finish_reason) fin = ch.finish_reason === "length" ? "MAX_TOKENS" : "STOP";
              continue;
            }
            const cand = j.candidates && j.candidates[0];
            const texte = cand && cand.content && (cand.content.parts || []).map((p: { text?: string }) => p.text || "").join("");
            if (texte) envoyer(c, { type: "content_block_delta", delta: { text: texte } });
            if (cand && cand.finishReason) fin = cand.finishReason;
          }
        }
        envoyer(c, { type: "message_delta", delta: { stop_reason: fin === "MAX_TOKENS" ? "max_tokens" : "end_turn" } });
      } catch (e) {
        envoyer(c, { type: "error", error: { message: "La réponse a été interrompue. Renvoie ta question." } });
        console.error(e);
      }
      c.close();
    },
  });
  return new Response(flux, { headers: { ...CORS, "content-type": "text/event-stream", "cache-control": "no-cache" } });
}
