// dashboard/static/js/architecture_graphe.js — Dessin D3 de la carte de l'agent (Phase 3).
// Disposition déterministe : colonnes par groupe sur bureau, bandes empilées sur mobile.
// Zoom : molette + Ctrl (ou pincement trackpad), deux doigts sur mobile ; un doigt fait défiler la page.

const ArchGraphe = (() => {
  const LIENS = {
    import:           { couleur: "#64748b", tirets: null,  libelle: "Import" },
    import_dynamique: { couleur: "#38bdf8", tirets: "5 3", libelle: "Import dynamique" },
    ecrit:            { couleur: "#f59e0b", tirets: null,  libelle: "Écrit" },
    lit:              { couleur: "#2dd4bf", tirets: null,  libelle: "Lit" },
    llm:              { couleur: "#a78bfa", tirets: null,  libelle: "LLM (routeur)" },
    llm_direct:       { couleur: "#f87171", tirets: "4 3", libelle: "Gemini hors routeur" },
  };
  const GROUPES = { cycles: "#10b981", exploration: "#0ea5e9", analyse: "#8b5cf6",
                    execution: "#f59e0b", ressources: "#64748b" };
  const ICONES = { table: "🗄 ", fichier: "📄 " };
  // Emplacement de l'état en direct (registre, branché sur la tour) : couleur du point
  const ETATS = { ok: "#10b981", alerte: "#f59e0b", erreur: "#ef4444" };
  const H = 34;

  function disposer(carte, largeur) {
    const mobile = largeur < 768, pos = {};
    const groupes = carte.groupes.map(g => ({ ...g, noeuds: carte.noeuds.filter(n => n.groupe === g.id) }));
    const voisins = {};
    carte.liens.forEach(l => {
      (voisins[l.source] ||= []).push(l.cible);
      (voisins[l.cible] ||= []).push(l.source);
    });
    const centre = id => { const v = (voisins[id] || []).filter(x => pos[x]);
      return v.length ? d3.mean(v, x => mobile ? pos[x].x + pos[x].y * 0.01 : pos[x].y) : Infinity; };
    const titres = [];
    let hauteur = 0;
    if (mobile) {
      const w = (largeur - 30) / 2;
      let y = 8;
      groupes.forEach((g, i) => {
        if (i > 0) g.noeuds.sort((a, b) => centre(a.id) - centre(b.id));
        titres.push({ libelle: g.libelle, x: 10, y: y + 12, couleur: GROUPES[g.id] });
        g.noeuds.forEach((n, k) => {
          pos[n.id] = { x: 10 + (k % 2) * (w + 10) + w / 2, y: y + 24 + Math.floor(k / 2) * (H + 8) + H / 2, w };
        });
        y += 30 + Math.ceil(g.noeuds.length / 2) * (H + 8);
      });
      hauteur = y + 8;
    } else {
      const colW = largeur / groupes.length, w = Math.min(176, colW - 18);
      const placer = g => g.noeuds.forEach((n, k) => {
        pos[n.id] = { x: g.x, y: 44 + k * (H + 12) + H / 2, w };
      });
      groupes.forEach((g, i) => { g.x = colW * i + colW / 2; placer(g); });
      for (let passe = 0; passe < 3; passe++) {
        groupes.slice(1).forEach(g => { g.noeuds.sort((a, b) => centre(a.id) - centre(b.id)); placer(g); });
      }
      groupes.forEach(g => titres.push({ libelle: g.libelle, x: g.x, y: 20, couleur: GROUPES[g.id], centre: true }));
      hauteur = 60 + d3.max(groupes, g => g.noeuds.length) * (H + 12);
    }
    return { pos, titres, hauteur, mobile };
  }

  // Point de sortie sur le bord du rectangle, dans la direction (dx, dy)
  function bord(p, dx, dy) {
    const t = Math.min(p.w / 2 / (Math.abs(dx) || 1e-9), H / 2 / (Math.abs(dy) || 1e-9));
    return [p.x + dx * t, p.y + dy * t];
  }

  function chemin(l, pos, rang) {
    const a = pos[l.source], b = pos[l.cible];
    const dx = b.x - a.x, dy = b.y - a.y, d = Math.hypot(dx, dy) || 1;
    const [x1, y1] = bord(a, dx / d, dy / d), [x2, y2] = bord(b, -dx / d, -dy / d);
    const courbe = 0.12 + rang * 0.1;  // liens parallèles écartés
    const cx = (x1 + x2) / 2 - dy / d * d * courbe, cy = (y1 + y2) / 2 + dx / d * d * courbe;
    return `M${x1},${y1} Q${cx},${cy} ${x2},${y2}`;
  }

  function tronquer(texte, w) {
    const max = Math.max(4, Math.floor((w - 14) / 6.3));
    return texte.length > max ? texte.slice(0, max - 1) + "…" : texte;
  }

  function dessiner(conteneur, carte, { onSelection }) {
    const largeur = conteneur.clientWidth;
    const { pos, titres, hauteur, mobile } = disposer(carte, largeur);
    conteneur.innerHTML = "";
    const svg = d3.select(conteneur).append("svg").attr("width", largeur).attr("height", hauteur)
      .attr("viewBox", `0 0 ${largeur} ${hauteur}`);
    const defs = svg.append("defs");
    Object.entries(LIENS).forEach(([t, s]) => defs.append("marker").attr("id", `fl-${t}`)
      .attr("viewBox", "0 0 10 10").attr("refX", 9).attr("refY", 5).attr("markerWidth", 6)
      .attr("markerHeight", 6).attr("orient", "auto-start-reverse")
      .append("path").attr("d", "M0,0 L10,5 L0,10 z").attr("fill", s.couleur));
    const scene = svg.append("g");
    scene.selectAll("text.titre").data(titres).join("text").attr("class", "titre")
      .attr("x", d => d.x).attr("y", d => d.y).attr("text-anchor", d => d.centre ? "middle" : "start")
      .attr("fill", d => d.couleur).attr("font-size", 11).attr("font-weight", 600).text(d => d.libelle);

    const paires = {};
    const liens = carte.liens.filter(l => pos[l.source] && pos[l.cible]).map(l => {
      const cle = [l.source, l.cible].sort().join("|");
      return { ...l, rang: (paires[cle] = (paires[cle] ?? -1) + 1) };
    });
    const traits = scene.append("g").attr("fill", "none").selectAll("path").data(liens).join("path")
      .attr("d", l => chemin(l, pos, l.rang)).attr("stroke", l => LIENS[l.type].couleur)
      .attr("stroke-dasharray", l => LIENS[l.type].tirets).attr("stroke-width", 1.3)
      .attr("marker-end", l => `url(#fl-${l.type})`);

    const noeuds = scene.append("g").selectAll("g").data(carte.noeuds.filter(n => pos[n.id])).join("g")
      .attr("class", "arch-noeud").attr("transform", n => `translate(${pos[n.id].x},${pos[n.id].y})`)
      .attr("tabindex", 0).attr("role", "button").attr("aria-label", n => n.libelle);
    noeuds.append("rect").attr("x", n => -pos[n.id].w / 2).attr("y", -H / 2)
      .attr("width", n => pos[n.id].w).attr("height", H).attr("rx", n => n.type === "composant" ? 8 : 3)
      .attr("fill", n => n.type === "composant" ? "#0f172a" : "#1e293b")
      .attr("stroke", n => n.tags.includes("code-mort") ? "#ef4444" : n.tags.includes("orphelin") ? "#f97316" : GROUPES[n.groupe])
      .attr("stroke-dasharray", n => n.tags.length ? "4 2" : null).attr("stroke-width", 1.5);
    noeuds.append("text").attr("text-anchor", "middle").attr("y", n => n.frequence ? -2 : 4)
      .attr("fill", "#e2e8f0").attr("font-size", 11)
      .text(n => tronquer((ICONES[n.type] || "") + n.libelle, pos[n.id].w));
    noeuds.filter(n => n.frequence).append("text").attr("text-anchor", "middle").attr("y", 11)
      .attr("fill", "#94a3b8").attr("font-size", 9).text(n => n.frequence);
    // Badge : modules orphelins ou morts dans un composant par ailleurs vivant
    noeuds.each(function (n) {
      const partiels = n.tags.length ? 0 : n.modules.filter(m => m.tags.length).length;
      if (!partiels) return;
      const mort = n.modules.some(m => m.tags.includes("code-mort"));
      const g = d3.select(this).append("g").attr("transform", `translate(${pos[n.id].w / 2 - 2},${-H / 2 + 2})`);
      g.append("circle").attr("r", 7).attr("fill", mort ? "#ef4444" : "#f97316");
      g.append("text").attr("text-anchor", "middle").attr("y", 3.5).attr("font-size", 9)
        .attr("fill", "#0f172a").attr("font-weight", 700).text(partiels);
    });
    noeuds.filter(n => n.etat).append("circle").attr("cx", n => -pos[n.id].w / 2 + 7).attr("r", 4)
      .attr("fill", n => ETATS[n.etat.statut] || "#94a3b8");

    // État d'affichage : types visibles, sélection, surlignage, tous les liens
    const vue = { types: new Set(Object.keys(LIENS)), selection: null, surligne: null, tous: !mobile };
    function appliquer() {
      const actifs = vue.surligne || (vue.selection ? new Set([vue.selection]) : null);
      const lienActif = l => vue.surligne ? actifs.has(l.source) && actifs.has(l.cible)
                                         : vue.selection ? l.source === vue.selection || l.cible === vue.selection : true;
      const voisins = new Set(actifs || []);
      if (vue.selection && !vue.surligne) liens.forEach(l => { if (lienActif(l)) { voisins.add(l.source); voisins.add(l.cible); } });
      traits.attr("display", l => vue.types.has(l.type) && (vue.tous || actifs) && lienActif(l) ? null : "none")
        .attr("stroke-opacity", actifs ? 0.95 : 0.35);
      noeuds.attr("opacity", n => !actifs || voisins.has(n.id) ? 1 : 0.25);
      noeuds.select("rect").attr("stroke-width", n => n.id === vue.selection ? 3 : 1.5);
    }
    noeuds.on("click", (e, n) => { e.stopPropagation(); vue.surligne = null; vue.selection = n.id; appliquer(); onSelection(n.id); })
      .on("keydown", (e, n) => { if (e.key === "Enter" || e.key === " ") { e.preventDefault(); vue.selection = n.id; appliquer(); onSelection(n.id); } });
    svg.on("click", () => { vue.selection = null; vue.surligne = null; appliquer(); onSelection(null); });

    const zoom = d3.zoom().scaleExtent([0.4, 3]).filter(e =>
      e.type === "wheel" ? e.ctrlKey || e.metaKey : e.type.startsWith("touch") ? e.touches.length >= 2 : !e.button)
      .on("zoom", e => scene.attr("transform", e.transform));
    svg.call(zoom).style("touch-action", "pan-y").on("dblclick.zoom", null);
    appliquer();

    return {
      types: LIENS,
      filtrer(types) { vue.types = new Set(types); appliquer(); },
      tousLiens(oui) { vue.tous = oui; appliquer(); return vue.tous; },
      estTousLiens() { return vue.tous; },
      selectionner(id) { vue.surligne = null; vue.selection = id; appliquer(); },
      surligner(ids) { vue.selection = null; vue.surligne = ids ? new Set(ids) : null; appliquer(); },
      zoomer(k) { k ? svg.transition().call(zoom.scaleBy, k) : svg.transition().call(zoom.transform, d3.zoomIdentity); },
    };
  }

  return { dessiner, LIENS };
})();
