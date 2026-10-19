# Brouillon : note de rupture « prix d'entrée et p0 » pour le registre (19/10/2026)

**Mise à jour du 19/10/2026 : intégré au registre (v1.8, §9, commit 4895e51), avec les décisions de
Lucia.** Ce brouillon reste comme trace ; c'est le §9 du registre qui fait foi.

**Statut d'origine : brouillon à valider.** Ce texte n'est pas dans `docs/REGISTRE_CRITERES.md`. S'il est
validé, il y entrerait comme v1.8, par un commit daté, **avant toute lecture qui utilise un prix**.
La seule lecture prévue d'ici là est Q3.a, le 03/11/2026, qui n'en utilise pas. Le brouillon a été
écrit sans regarder aucun rendement. Le détail des mesures est dans `docs/DIAG_PRIX_ENTREE.md`.

---

## Texte proposé (v1.8, note de fait et règle de traitement)

### 1. Constat (mesuré le 19/10/2026, en lecture seule)

- **p0 figé.** Le prix enregistré dans chaque décision (§0.2, « dernière clôture utilisée ») vient de
  barres journalières collectées une fois par jour, vers 06h30 UTC. Pour les décisions BUY/SELL
  depuis R2, l'âge du prix observé est de 25,7 h en médiane :
  - tactical (97 % des décisions), actions et ETF : 30,8 h ;
  - tactical, cryptos : 12,3 h ;
  - cycle quotidien : 10,5 h.

  La fenêtre de rendement commence donc avant la décision. La note « Prix de départ décalé » du §4
  ne couvrait que les cryptos.
- **Boucles paper.** La règle anti-doublon ne regarde que les positions ouvertes. Une position
  ouverte à un prix figé, puis fermée au premier passage du critique, est rouverte au même prix au
  passage suivant du tactical, jusqu'à la collecte du lendemain. Il y a 16 boucles (3 ouvertures
  ou plus au même prix exact), qui font 313 des 421 positions. Depuis R2 : AMZN du 09/10 16:46 au
  10/10 07:15 (56 ouvertures), AAPL le 13/10 de 14:46 à 15:16 (3 ouvertures). Heures de Lisbonne.

### 2. Ce qui est contaminé, et depuis quand

| Élément | Nature | Depuis |
|---|---|---|
| p0 de toutes les décisions (Q1, Q2, Q3.b) | départ décalé, de 10 à 31 h en médiane selon le cycle et la classe | 06/10/2026 (R2) |
| Statistiques tirées des positions paper fermées : winrate par actif, gains et pertes consécutifs, mode du Budget Manager, porte paper à 9, `performance_tracker.md`, `lessons_learned.md`, `market_patterns.md`, contexte du pipeline | dominées par les boucles | 07/05/2026 (1re boucle) ; dans la fenêtre du registre, le 09/10/2026 16:46 |
| `contexte.winrate_actif` inscrit dans les décisions | valeur tirée des positions bouclées | idem, pour les actifs bouclés (AMZN depuis le 09/10, AAPL depuis le 13/10 ; SOL, ETH, BTC, MSFT, NVDA, VRT depuis leurs boucles d'avant R2) |
| §7 Jev et §8 fantôme | p0 du cycle quotidien, juste après la collecte (écart de la nuit seulement). Sortie du fantôme à la 5e barre, sans boucle. Champs `mode_bm`, `plafond_bm`, `taille_hypothetique` dépendants du mode du Budget Manager | 09/10/2026 |
| Q3.a | pas de prix ; contexte du pipeline seulement | 09/10/2026 |

### 3. Traitement dans les lectures

1. **Le critère primaire ne change pas** pour les données déjà enregistrées (règle de l'en-tête :
   une modification ne s'applique qu'aux données postérieures à son commit). Q1, Q2 et Q3.b se lisent
   avec p0 tel que défini au §0.2.
2. **Lecture de sensibilité, descriptive, jamais un critère** (comme J+1 et J+10, §0.3) : la même
   métrique, recalculée avec un p0′ postérieur à la décision.
   - Cryptos : la clôture de la barre 1 h qui contient la décision. Les barres « 4h » de `prices`
     sont en fait des barres 1 h, disponibles pour les 5 cryptos.
   - Actions, ETF et futures : la clôture de la séance du jour de la décision si la décision a eu
     lieu pendant cette séance, sinon la clôture de la séance suivante.

   Si le critère primaire et la sensibilité donnent des décisions différentes, la question est
   déclarée « non décidable » (§0.3) et rien ne change.
3. **Décisions prises sous un contexte bouclé**, signalées et comptées à part, sans être exclues de
   la lecture primaire. Ce sont les décisions dont l'actif avait au moins une position bouclée avant
   la décision, et les décisions prises pendant une boucle. Leur nombre est publié avec la lecture.
4. **Après la correction du prix d'entrée** (option à choisir, voir `docs/DIAG_PRIX_ENTREE.md` §4) :
   - un nouveau champ, prix d'exécution paper et son heure, est enregistré à côté de p0 ;
   - à partir du commit de correction, les questions de rendement utilisent ce prix comme p0 pour
     les nouvelles données ;
   - les données d'avant et d'après ne sont pas mélangées dans une même moyenne : deux lectures
     séparées, ou la lecture sur les seules données postérieures si elles atteignent le n minimal
     avant l'échéance.
5. **Statistiques paper** (winrate, pertes consécutives, mémoire) : aucune n'est un critère du
   registre. Elles ne peuvent servir d'argument dans aucune lecture tant que les positions bouclées
   n'en sont pas exclues.

### 4. Ce que cette note ne dit pas

- Elle ne dit pas si le décalage biaise les rendements dans un sens : seul un calcul de rendement le
  dirait, et il est interdit avant les lectures.
- Elle ne dit rien de l'issue des positions bouclées.

---

## Points à trancher par Lucia avant le commit au registre

- Garder la sensibilité p0′ (point 2), ou se contenter de la note de fait ?
- Faut-il signaler les décisions sous contexte bouclé (point 3), ou les exclure de la lecture primaire ?
  L'exclusion changerait un critère déjà enregistré : elle ne vaudrait que pour les données postérieures.
- Quelle option de correction, et à quelle date ? La date fixe la frontière du point 4.
