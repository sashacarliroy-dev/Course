// Fonction Supabase « prof » : relaie les questions de l'assistant du site vers Gemini (Google)
// et renvoie la réponse au fil de l'eau, au format attendu par index.html.
// La clé reste côté serveur : secret GEMINI_API_KEY (Supabase > Edge Functions > Secrets).

const MODELE = Deno.env.get("GEMINI_MODEL") || "gemini-2.5-flash";
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
  const cle = Deno.env.get("GEMINI_API_KEY");
  if (!cle) return json({ erreur: "La clé de l'IA n'est pas encore enregistrée sur Supabase." }, 500);

  let systeme = "", messages: { role: string; content: string }[] = [];
  try { ({ systeme, messages } = await req.json()); } catch { return json({ erreur: "Requête illisible." }, 400); }
  if (typeof systeme !== "string" || !Array.isArray(messages) || !messages.length) return json({ erreur: "Requête incomplète." }, 400);
  // Garde-fous : on limite la taille pour protéger le quota gratuit
  systeme = systeme.slice(0, 60000);
  messages = messages.slice(-12).map((m) => ({ role: m.role === "assistant" ? "model" : "user", content: String(m.content || "").slice(0, 4000) }));

  const r = await fetch(`https://generativelanguage.googleapis.com/v1beta/models/${MODELE}:streamGenerateContent?alt=sse`, {
    method: "POST",
    headers: { "content-type": "application/json", "x-goog-api-key": cle },
    body: JSON.stringify({
      systemInstruction: { parts: [{ text: systeme }] },
      contents: messages.map((m) => ({ role: m.role, parts: [{ text: m.content }] })),
      generationConfig: { maxOutputTokens: 1500, temperature: 0.6, thinkingConfig: { thinkingBudget: 0 } },
    }),
  });
  if (!r.ok || !r.body) {
    const detail = await r.text().catch(() => "");
    console.error("Gemini", r.status, detail.slice(0, 500));
    return json({ erreur: r.status === 429 ? "Trop de questions d'un coup : réessaie dans une minute." : "L'IA ne répond pas pour le moment." }, r.status === 429 ? 429 : 502);
  }

  // Conversion du flux Gemini en événements « content_block_delta » / « message_delta »
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
            let j; try { j = JSON.parse(ligne.slice(5)); } catch { continue; }
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
});
