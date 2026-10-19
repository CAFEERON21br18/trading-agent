// dashboard/static/js/architecture_etat.js — Vue temps réel de la carte (Phase 3) : GET /api/topology/etat
// toutes les 30 s (en pause quand la page est cachée). Couleur du point de chaque composant, liste
// lisible sur téléphone (aucun survol : toucher une ligne ouvre le détail), détail des sources dans le
// panneau. Une réponse en échec ou trop lente garde la dernière vue, signalée : la carte ne casse jamais.
// Toute donnée insérée en HTML passe par escHtml (base.html).

const ArchEtat = (() => {
  const PERIODE_MS = 30000, DELAI_MS = 20000;
  const ETATS = {
    "en erreur": "#ef4444", "inactif": "#f59e0b", "actif": "#10b981",
    "jamais exécuté": "#64748b", "inconnu": "#94a3b8", "pas de source d'état": null,
  };
  let donnees = null, reussite = null, echec = null, minuterie = null, enCours = false;

  function relatif(iso) {
    if (!iso) return "jamais";
    const s = Math.max(0, Math.round((Date.now() - new Date(iso)) / 1000));
    if (s < 60) return "à l'instant";
    if (s < 3600) return `il y a ${Math.round(s / 60)} min`;
    if (s < 86400) return `il y a ${Math.round(s / 3600)} h`;
    return `il y a ${Math.round(s / 86400)} j`;
  }
  const date = iso => iso ? new Date(iso).toLocaleString("fr-FR",
    { day: "2-digit", month: "2-digit", hour: "2-digit", minute: "2-digit" }) : "—";
  // Pas de point pour « pas de source d'état » (null) ; gris pour un état inattendu
  const couleur = id => { const e = etat(id); return !e ? null : e.etat in ETATS ? ETATS[e.etat] : "#94a3b8"; };
  const pastille = e => `<span class="arch-etat" style="border-color:${ETATS[e] || "#475569"}">${escHtml(e)}</span>`;
  const etat = id => (donnees && donnees.composants[id]) || null;

  async function charger(onMaj) {
    if (enCours) return;
    enCours = true;
    const ctrl = new AbortController(), minute = setTimeout(() => ctrl.abort(), DELAI_MS);
    try {
      const r = await fetch("/api/topology/etat", { signal: ctrl.signal, cache: "no-store" });
      const j = await r.json();
      if (!r.ok) throw new Error(j.erreur || `HTTP ${r.status}`);
      donnees = j; reussite = new Date(); echec = null;
    } catch (e) {
      echec = e.name === "AbortError" ? "délai dépassé" : e.message;
    } finally {
      clearTimeout(minute); enCours = false;
    }
    onMaj();
  }

  function demarrer(onMaj) {
    charger(onMaj);
    clearInterval(minuterie);
    minuterie = setInterval(() => { if (!document.hidden) charger(onMaj); }, PERIODE_MS);
    document.addEventListener("visibilitychange", () => { if (!document.hidden) charger(onMaj); });
  }

  function meta() {
    if (!reussite) return echec ? `indisponible (${echec})` : "chargement…";
    const sources = Object.entries(donnees.sources).map(([k, v]) => `${k} ${v}`).join(", ");
    return `mis à jour à ${reussite.toLocaleTimeString("fr-FR")}, toutes les 30 s (sources : ${sources})` +
      (echec ? ` — dernière relecture en échec (${echec}), vue précédente gardée` : "");
  }

  function resume() {
    if (!donnees) return echec ? "indisponible" : "…";
    const n = {};
    Object.values(donnees.composants).forEach(e => { n[e.etat] = (n[e.etat] || 0) + 1; });
    return Object.keys(ETATS).filter(k => n[k] && ETATS[k]).map(k => `${n[k]} ${k}`).join(" · ");
  }

  function html(id) {
    const e = etat(id);
    if (!e) return `<div class="text-slate-500">État en direct : ${escHtml(echec ? "indisponible (" + echec + ")" : "chargement…")}</div>`;
    return `<div><div class="font-semibold text-slate-300 mb-1">État en direct ${pastille(e.etat)}</div>` +
      `<div class="text-slate-300 mb-1">Dernière exécution : ${escHtml(date(e.derniere_execution))} ` +
      `(${escHtml(relatif(e.derniere_execution))})` +
      (e.executions_24h !== null ? ` · ${escHtml(e.executions_24h)} ${escHtml(e.unite)} sur 24 h` : "") + "</div>" +
      (e.details.length ? e.details.map(d => `<div class="arch-preuve">${escHtml(d)}</div>`).join("")
                        : `<div class="text-slate-500">Aucune source : ni tâche, ni journal d'activité, ni table remplie.</div>`) +
      "</div>";
  }

  function liste(carte) {
    if (!donnees) return `<div class="text-slate-500">${escHtml(echec ? "État indisponible : " + echec : "Chargement…")}</div>`;
    return carte.groupes.map(g => {
      const noeuds = carte.noeuds.filter(n => n.groupe === g.id && etat(n.id));
      if (!noeuds.length) return "";
      return `<div class="mb-2"><div class="text-slate-400 font-semibold mb-1">${escHtml(g.libelle)}</div>` +
        noeuds.map(n => {
          const e = etat(n.id);
          const extra = e.executions_24h !== null ? ` · ${e.executions_24h} ${e.unite === "passages" ? "×" : "lignes"}/24 h` : "";
          return `<button class="arch-ligne" data-id="${escHtml(n.id)}">` +
            `<span class="arch-point" style="background:${ETATS[e.etat] || "transparent"}"></span>` +
            `<span class="flex-1 text-left text-slate-200">${escHtml(n.libelle)}</span>` +
            `<span class="text-right text-slate-400">${escHtml(e.etat)}` +
            (e.etat !== "pas de source d'état" ? ` · ${escHtml(relatif(e.derniere_execution))}${escHtml(extra)}` : "") +
            "</span></button>";
        }).join("") + "</div>";
    }).join("");
  }

  return { demarrer, etat, couleur, html, liste, meta, resume, ETATS };
})();
