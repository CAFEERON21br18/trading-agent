// dashboard/static/js/audit_page.js — Page « Audit » (Phase 4, partie D) : consultation de message_audit
// par l'API existante, en lecture seule (GET /api/audit/messages, /messages/<id>, /stats).
// Timeline dépliable (le détail se charge à l'ouverture), filtres date / LLM / erreur ; d'un côté le
// message et la réponse, de l'autre le contexte injecté, la vérification des chiffres et la chaîne de
// repli. Aucune écriture, aucun export. Toute donnée insérée en HTML passe par escHtml (base.html).

(() => {
  const $ = id => document.getElementById(id);
  const PAR_PAGE = 20;
  const FILTRES = [["du", "aud-du"], ["au", "aud-au"], ["llm", "aud-llm"], ["erreur", "aud-erreur"]];
  const complets = {};  // id -> enregistrement complet déjà chargé
  let page = 1, pages = 1;

  const date = iso => iso ? new Date(iso).toLocaleString("fr-FR",
    { day: "2-digit", month: "2-digit", year: "2-digit", hour: "2-digit", minute: "2-digit", second: "2-digit" }) : "—";
  const pastille = (texte, classe) => `<span class="pill ${classe}">${escHtml(texte)}</span>`;
  const json = v => escHtml(v === null || v === undefined ? "—" : JSON.stringify(v, null, 2));
  const tronquer = (t, n) => !t ? "—" : t.length > n ? t.slice(0, n - 1) + "…" : t;
  const bloc = (titre, contenu) => `<div class="mb-3"><div class="aud-titre">${escHtml(titre)}</div>${contenu}</div>`;
  const repli = (titre, contenu) =>
    `<details class="mb-3"><summary class="aud-titre cursor-pointer">${escHtml(titre)}</summary>${contenu}</details>`;

  async function lire(url) {
    const r = await fetch(url, { cache: "no-store" });
    const j = await r.json();
    if (!r.ok) throw new Error(j.error || `HTTP ${r.status}`);
    return j;
  }

  async function chargerStats() {
    try {
      const s = await lire("/api/audit/stats");
      const llm = Object.entries(s.par_llm).map(([k, v]) => `${k} ${v}`).join(", ");
      $("aud-stats").textContent = `${s.total} message(s) conservé(s) (${llm}) · ${s.total_7_jours} sur 7 jours · ` +
        `conservation ${s.conservation_jours} jours (purge par le cycle cleanup)`;
    } catch (e) {
      $("aud-stats").textContent = `Statistiques indisponibles : ${e.message}`;
    }
  }

  function badges(m) {
    const b = [pastille(m.source, "pill-neutral"),
               pastille(m.llm_utilise || "?", m.llm_utilise === "rule_based" ? "pill-hold" : "pill-paper")];
    if (m.erreur) b.push(pastille("erreur", "pill-sell"));
    if (m.contournement) b.push(pastille("contournement", "pill-sell"));
    if (m.fallback.some(f => f.ok === false)) b.push(pastille("repli", "pill-hold"));
    if (m.actions) b.push(pastille("actions", "pill-buy"));
    return b.join(" ");
  }

  function ligne(m) {
    return `<details class="aud-item" data-id="${escHtml(m.id)}"><summary>` +
      `<div class="flex flex-wrap items-center gap-1 text-xs"><span class="text-slate-400">#${escHtml(m.id)} · ` +
      `${escHtml(date(m.timestamp))} · ${escHtml(m.latence_ms ?? "?")} ms</span> ${badges(m)}</div>` +
      `<div class="text-sm text-slate-100 mt-1 aud-texte">${escHtml(tronquer(m.message_utilisateur, 160))}</div>` +
      `<div class="text-xs text-slate-400 mt-1 aud-texte">${escHtml(tronquer(m.extrait_reponse, 140))}</div>` +
      `</summary><div class="aud-corps p-3 text-xs text-slate-500">Chargement…</div></details>`;
  }

  function verification(v) {  // objet JSON rendu par l'API (null si non mesurée)
    if (!v) return `<div class="text-slate-500">Non mesurée (message antérieur à la vérification, ou sans réponse du LLM).</div>`;
    const taux = v.taux_non_soutenus === null || v.taux_non_soutenus === undefined ? "—"
      : `${Math.round(v.taux_non_soutenus * 1000) / 10} %`;
    const liste = (v.non_soutenus || []).map(n => escHtml(n)).join(", ");
    return `<div>${escHtml(v.nb_chiffres)} chiffre(s) dans la réponse : <span class="aud-ok">${escHtml(v.soutenus)} ` +
      `retrouvé(s) dans le prompt</span>, <span class="${(v.non_soutenus || []).length ? "aud-ko" : ""}">` +
      `${escHtml((v.non_soutenus || []).length)} absent(s)</span> (taux ${escHtml(taux)}) ; ` +
      `${escHtml(v.petits_entiers ?? 0)} petit(s) entier(s) ignoré(s).</div>` +
      (liste ? `<div class="aud-code mt-1">Absents du prompt : ${liste}</div>` : "");
  }

  function chaine(etapes) {
    if (!etapes || !etapes.length) return `<div class="text-slate-500">—</div>`;
    return etapes.map(e => {
      if (e.etape === "configuration") {
        return `<div class="text-slate-400 mb-1">Configuration : Gemini ${escHtml(e.gemini_modele || "?")} ` +
          `(clé ${escHtml(e.gemini_cle || "absente")}), Groq ${escHtml(e.groq_modele || "?")} (clé ${escHtml(e.groq_cle || "absente")})</div>`;
      }
      const signe = e.ok === true ? `<span class="aud-ok">✓</span>` : e.ok === false ? `<span class="aud-ko">✗</span>` : "·";
      const infos = [e.modele, e.statut, e.type_erreur, e.raison, e.duree_ms !== undefined ? `${e.duree_ms} ms` : null]
        .filter(x => x !== null && x !== undefined && x !== "");
      return `<div class="mb-1">${signe} <b>${escHtml(e.fournisseur || e.etape || "?")}</b> ` +
        `<span class="text-slate-400">${escHtml(infos.join(" · "))}</span>` +
        (e.erreur ? `<div class="aud-code mt-1">${escHtml(e.erreur)}</div>` : "") + "</div>";
    }).join("");
  }

  function actions(r) {
    const a = r.actions_declenchees || {};
    const ecritures = (a.ecritures || []).map(e => `${e.categorie} : ${e.operation} ${e.cible}`);
    const lignes = [`Appels LLM : ${(a.appels_llm || {}).total ?? 0}`,
                    `decider() lancés : ${(a.decider_lances || []).join(", ") || "aucun"}`,
                    `Écritures : ${ecritures.join(" ; ") || "aucune"}`,
                    `Passé par le Decision Engine : ${r.passe_par_decision_engine ?? "sans objet"}, ` +
                    `par le Budget Manager : ${r.passe_par_budget_manager ?? "sans objet"}`];
    return lignes.map(l => `<div>${escHtml(l)}</div>`).join("") +
      ((r.decisions_trading_generees || []).length ? `<pre class="aud-code mt-1">${json(r.decisions_trading_generees)}</pre>` : "");
  }

  function corps(r) {
    const contexte = r.contexte_injecte ? Object.keys(r.contexte_injecte).join(", ") : "vide";
    const gauche = bloc("Message", `<div class="aud-texte text-slate-100">${escHtml(r.message_utilisateur || "—")}</div>`) +
      bloc("Réponse", `<div class="aud-texte text-slate-200">${escHtml(r.reponse_brute || "—")}</div>`) +
      (r.erreur ? bloc("Erreur", `<div class="aud-texte aud-ko">${escHtml(r.erreur)}</div>`) : "") +
      bloc("Actions déclenchées", actions(r));
    const droite = repli(`Contexte injecté (${contexte})`, `<pre class="aud-code">${json(r.contexte_injecte)}</pre>`) +
      bloc("Vérification des chiffres", verification(r.verification_chiffres)) +
      bloc("Chaîne de repli", chaine(r.chaine_de_fallback)) +
      repli("Prompt envoyé (contient le portefeuille réel)", `<pre class="aud-code">${escHtml(r.prompt_envoye || "—")}</pre>`) +
      repli("Origine de la requête", `<pre class="aud-code">${json(r.origine_client)}</pre>`);
    return `<div class="grid md:grid-cols-2 gap-4 text-slate-300"><div>${gauche}</div><div>${droite}</div></div>`;
  }

  async function ouvrir(el) {
    const id = el.dataset.id, zone = el.querySelector(".aud-corps");
    try {
      complets[id] = complets[id] || await lire(`/api/audit/messages/${encodeURIComponent(id)}`);
      zone.className = "aud-corps p-3 text-xs";
      zone.innerHTML = corps(complets[id]);
    } catch (e) {
      zone.innerHTML = `<div class="aud-ko">Détail indisponible : ${escHtml(e.message)}</div>`;
    }
  }

  async function charger() {
    const p = new URLSearchParams({ page, par_page: PAR_PAGE });
    FILTRES.forEach(([cle, id]) => { if ($(id).value) p.set(cle, $(id).value); });
    const zoneErreur = $("aud-erreur-chargement");
    try {
      const j = await lire(`/api/audit/messages?${p}`);
      pages = Math.max(1, j.pages);
      zoneErreur.classList.add("hidden");
      $("aud-liste").innerHTML = j.messages.length ? j.messages.map(ligne).join("")
        : `<div class="card text-xs text-slate-400">Aucun message pour ces filtres.</div>`;
      $("aud-liste").querySelectorAll(".aud-item").forEach(el =>
        el.addEventListener("toggle", () => { if (el.open) ouvrir(el); }));
      $("aud-page").textContent = `page ${j.page} / ${pages} · ${j.total} message(s)`;
    } catch (e) {
      zoneErreur.classList.remove("hidden");
      zoneErreur.textContent = `Audit indisponible : ${e.message}`;
      $("aud-liste").innerHTML = "";
    }
    $("aud-recents").disabled = page <= 1;
    $("aud-anciens").disabled = page >= pages;
  }

  FILTRES.forEach(([, id]) => $(id).addEventListener("change", () => { page = 1; charger(); }));
  $("aud-effacer").addEventListener("click", () => { FILTRES.forEach(([, id]) => { $(id).value = ""; }); page = 1; charger(); });
  $("aud-recents").addEventListener("click", () => { if (page > 1) { page--; charger(); } });
  $("aud-anciens").addEventListener("click", () => { if (page < pages) { page++; charger(); } });
  chargerStats();
  charger();
})();
