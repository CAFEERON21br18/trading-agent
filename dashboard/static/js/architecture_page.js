// dashboard/static/js/architecture_page.js — Page « Architecture » : données /api/topology,
// filtres, incohérences et panneau de détail. Le dessin est dans architecture_graphe.js.
// Toute donnée insérée en HTML passe par escHtml (base.html).

(() => {
  const $ = id => document.getElementById(id);
  let carte = null, graphe = null, incActive = null;
  const typesVisibles = new Set(Object.keys(ArchGraphe.LIENS));

  const nomModule = c => c.replace(/\.py$/, "").replace(/\/__init__$/, "").replaceAll("/", ".");
  const libelle = id => (carte.noeuds.find(n => n.id === id) || { libelle: id }).libelle;
  const TAGS = { "code-mort": "pill-sell", "orphelin": "pill-hold" };
  const pastilles = tags => tags.map(t => `<span class="pill ${TAGS[t] || "pill-neutral"}">${escHtml(t)}</span>`).join(" ");

  function afficherMeta() {
    const g = carte.graphe, court = s => (s || "?").slice(0, 7);
    const fraicheur = g.a_jour ? "à jour" : `en retard : graphe du commit ${court(g.commit)}, dépôt à ${court(g.head)}`;
    const reserve = (carte.reserve_gemini.appelants || []).join(", ") || "inconnue";
    $("arch-meta").innerHTML =
      `Graphe Graphify ${escHtml(g.graphify || "?")} — <span class="${g.a_jour ? "text-emerald-400" : "text-amber-400"}">` +
      `${escHtml(fraicheur)}</span><br>Gemini réservé à : ${escHtml(reserve)} ` +
      `<span class="text-slate-600">(${escHtml(carte.reserve_gemini.source)})</span><br>` +
      `État en direct : <span class="text-slate-500">${carte.etat_source ? escHtml(carte.etat_source) : "pas encore branché (registre, sur la tour)"}</span>` +
      (carte.non_classes.length ? `<br><span class="text-amber-400">Modules non classés : ${escHtml(carte.non_classes.join(", "))}</span>` : "");
  }

  function afficherFiltres() {
    const zone = $("arch-filtres"), legende = $("arch-legende");
    zone.innerHTML = Object.entries(ArchGraphe.LIENS).map(([t, s]) =>
      `<button class="arch-chip" data-type="${escHtml(t)}" style="border-color:${s.couleur}">${escHtml(s.libelle)}</button>`).join("");
    zone.querySelectorAll("button").forEach(b => b.addEventListener("click", () => {
      const t = b.dataset.type;
      typesVisibles.has(t) ? typesVisibles.delete(t) : typesVisibles.add(t);
      b.classList.toggle("off", !typesVisibles.has(t));
      graphe.filtrer([...typesVisibles]);
    }));
    legende.innerHTML = [
      ["#ef4444", "bord rouge : code mort"], ["#f97316", "bord orange : orphelin"],
      ["#f97316", "pastille : modules orphelins/morts dans le composant"], ["#94a3b8", "🗄 table · 📄 fichier mémoire"],
    ].map(([c, t]) => `<span><span style="color:${c}">■</span> ${escHtml(t)}</span>`).join("");
  }

  function afficherIncoherences() {
    if (window.innerWidth < 768) $("arch-incoherences").open = false;  // mobile : la carte d'abord
    $("arch-nb-inc").textContent = carte.incoherences.length;
    $("arch-liste-inc").innerHTML = carte.incoherences.map((i, k) => `
      <div class="arch-inc" data-k="${k}" role="button" tabindex="0">
        <div class="font-semibold text-slate-200">${escHtml(i.titre)}
          ${i.todo ? `<span class="pill pill-neutral ml-1">TODO ${escHtml(i.todo)}</span>` : ""}</div>
        <div class="text-slate-400 mt-1">${escHtml(i.detail)}</div>
      </div>`).join("");
    $("arch-liste-inc").querySelectorAll(".arch-inc").forEach(el => {
      const activer = () => {
        const k = Number(el.dataset.k), meme = incActive === k;
        incActive = meme ? null : k;
        document.querySelectorAll(".arch-inc").forEach(x => x.classList.toggle("actif", Number(x.dataset.k) === incActive));
        graphe.surligner(meme ? null : carte.incoherences[k].noeuds);
        fermerPanneau();
        if (!meme) $("arch-graphe").scrollIntoView({ behavior: "smooth", block: "start" });
      };
      el.addEventListener("click", activer);
      el.addEventListener("keydown", e => { if (e.key === "Enter") activer(); });
    });
  }

  function blocLiens(titre, liens, cote) {
    if (!liens.length) return "";
    return `<div><div class="font-semibold text-slate-300 mb-1">${escHtml(titre)} (${liens.length})</div>` +
      liens.map(l => {
        const s = ArchGraphe.LIENS[l.type];
        const extra = l.appelant ? ` · ${escHtml(l.appelant)}${l.role ? " (" + escHtml(l.role) + ")" : ""}` : "";
        return `<details class="mb-1"><summary><span style="color:${s.couleur}">●</span> ` +
          `${escHtml(libelle(l[cote]))} <span class="text-slate-500">${escHtml(s.libelle)}${extra}</span></summary>` +
          l.preuves.map(p => `<div class="arch-preuve pl-4">${escHtml(p)}</div>`).join("") + "</details>";
      }).join("") + "</div>";
  }

  function ouvrirPanneau(id) {
    const n = carte.noeuds.find(x => x.id === id);
    if (!n) return fermerPanneau();
    $("arch-p-titre").textContent = n.libelle;
    $("arch-p-sous").textContent = [carte.groupes.find(g => g.id === n.groupe)?.libelle, n.frequence].filter(Boolean).join(" · ");
    const sortants = carte.liens.filter(l => l.source === id), entrants = carte.liens.filter(l => l.cible === id);
    const incs = carte.incoherences.filter(i => i.noeuds.includes(id));
    $("arch-p-corps").innerHTML =
      (n.tags.length ? `<div>${pastilles(n.tags)}</div>` : "") +
      (n.annotation ? `<div class="text-amber-300">ℹ️ ${escHtml(n.annotation)}</div>` : "") +
      `<div class="text-slate-500">État en direct : ${n.etat ? escHtml(JSON.stringify(n.etat)) : "non branché (registre, sur la tour)"}</div>` +
      (n.modules.length ? `<div><div class="font-semibold text-slate-300 mb-1">Modules (${n.modules.length})</div>` +
        n.modules.map(m => `<div title="${escHtml(m.chemin)}">${escHtml(nomModule(m.chemin))} ${pastilles(m.tags)}</div>`).join("") + "</div>" : "") +
      (incs.length ? `<div><div class="font-semibold text-slate-300 mb-1">Incohérences</div>` +
        incs.map(i => `<div class="text-amber-400">⚠️ ${escHtml(i.titre)}</div>`).join("") + "</div>" : "") +
      blocLiens("Dépend de / alimente", sortants, "cible") + blocLiens("Utilisé par / lu depuis", entrants, "source");
    $("arch-panneau").classList.remove("hidden");
  }

  function fermerPanneau() { $("arch-panneau").classList.add("hidden"); }

  function dessiner() {
    graphe = ArchGraphe.dessiner($("arch-graphe"), carte, {
      onSelection: id => {
        incActive = null;
        document.querySelectorAll(".arch-inc").forEach(x => x.classList.remove("actif"));
        id ? ouvrirPanneau(id) : fermerPanneau();
      },
    });
    graphe.filtrer([...typesVisibles]);
    $("arch-tous-liens").classList.toggle("actif", graphe.estTousLiens());
  }

  async function charger() {
    try {
      const r = await fetch("/api/topology");
      const j = await r.json();
      if (!r.ok) throw Object.assign(new Error(j.erreur || `HTTP ${r.status}`), { aide: j.aide });
      carte = j;
    } catch (e) {
      $("arch-graphe").innerHTML = "";
      const el = $("arch-erreur");
      el.classList.remove("hidden");
      el.innerHTML = `<div class="text-red-300 text-sm font-semibold">Carte indisponible</div>` +
        `<div class="text-xs text-slate-300 mt-1">${escHtml(e.message)}</div>` +
        (e.aide ? `<div class="text-xs mt-2">À lancer à la racine du dépôt :</div>` +
          e.aide.map(a => `<div class="arch-preuve">${escHtml(a)}</div>`).join("") : "");
      return;
    }
    afficherMeta(); afficherFiltres(); afficherIncoherences(); dessiner();
  }

  document.querySelectorAll("[data-zoom]").forEach(b =>
    b.addEventListener("click", () => graphe && graphe.zoomer(Number(b.dataset.zoom))));
  $("arch-tous-liens").addEventListener("click", () =>
    graphe && $("arch-tous-liens").classList.toggle("actif", graphe.tousLiens(!graphe.estTousLiens())));
  $("arch-p-fermer").addEventListener("click", () => { fermerPanneau(); graphe && graphe.selectionner(null); });
  let largeur = window.innerWidth;
  window.addEventListener("resize", () => {
    if (!carte || Math.abs(window.innerWidth - largeur) < 40) return;  // ignore la barre d'adresse mobile
    largeur = window.innerWidth; fermerPanneau(); dessiner();
  });
  charger();
})();
