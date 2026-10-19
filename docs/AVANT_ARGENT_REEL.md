# Avant l'argent réel : conditions objectives (19/10/2026)

**Ce document ne décide rien.** Il liste les conditions à remplir avant qu'une décision de
l'agent soit appliquée au portefeuille réel. Même alors, c'est toi qui passerais l'ordre à
la main sur Revolut. Il n'y a aucun code d'exécution d'ordre, et ce document n'en prévoit
pas. Aujourd'hui, l'agent conseille sur le réel et n'agit jamais (CLAUDE.md, « Portefeuille RÉEL »).

## Codes utilisés

Définitions données par Lucia le 19/10/2026, reprises telles quelles :

- W2 : frais, spread, change et fiscalité portugaise forment un seuil d'environ 6 à 10 points par an à battre. Les positions réelles sont en dollars, le montant débité en euros n'est pas stocké, et les coûts du §0.2 (crypto 1,0 %, reste 0,2 % aller-retour) sont des hypothèses, pas des frais Revolut mesurés.
- W4 : plafonner la poche pilotée par l'agent à 10-20 % du capital investissable (à décider par Lucia).
- C3 : le capital paper est constant, le P&L réalisé n'y est jamais ajouté, et l'arrêt d'urgence est inerte (portfolio.py:97-103 ; constat du 19/10 : il compare config.CAPITAL fixe au seuil de 700 €).
- D6 : intuition.py:478-480 force un BUY après n'importe quel veto si l'ajustement est d'au moins 2, même sur un signal baissier (TODO §20).
- D7 : le veto Extreme Greed est contournable par l'intuition au cycle quotidien et inactif dans le tactical (TODO §21).
- D8 : le tactical n'évalue que les 8 premiers actifs sans position (TODO §22).

**Emplacements vérifiés le 19/10/2026 dans le code actuel :**
- C3 : `agents/paper_trader/portfolio.py:97-103` (`capital_total = config.CAPITAL`, `cash = capital_total − invested`).
- D6 : le code est maintenant à `agents/intuition.py:100-102`, depuis le découpage du fichier.
  La règle couvre `HOLD` comme `NO_TRADE`.
- D7 : `agents/decision_engine.py:88-96` ; le tactical appelle `analyser_actif_complet(t)` sans
  `sentiment_global` (`scripts/cycle_tactical.py:67`).
- D8 : `scripts/cycle_tactical.py:158-159`.

## 1. Vue d'ensemble

| # | Condition | État au 19/10/2026 | Date prévue |
|---|---|---|---|
| 1 | Lectures du registre faites (Q1, Q3, §7 Jev) | en cours | 03/11/2026 (Q3.a) ; 11/01/2027 (Jev) ; ≈ 16/03/2027 (Q1) |
| 2 | `signal_results` alimentée | pas fait | aucune |
| 3 | Frais Revolut réels mesurés, seuil annuel W2 connu | pas fait (coûts du §0.2 = hypothèses ; débit en euros non stocké) | aucune |
| 4 | Défauts D6-D8 corrigés, avec critère | pas fait : TODO §20, §21, §22 ouverts, gelés jusqu'à un critère | aucune |
| 5 | §29 (1 € = 1 $) corrigé | pas fait, gelé volontairement | après les fenêtres de mesure |
| 6 | Plafond de la poche pilotée (W4, 10 à 20 %) | pas fait (valeur à décider, notion absente du code) | aucune |
| 7 | Arrêt d'urgence fonctionnel, capital paper qui intègre le P&L réalisé (C3) | **pas fonctionnel** | aucune |
| 8 | Test de bout en bout « proposition seulement », N semaines | pas commencé | aucune |
| 9 | Prix d'entrée paper au cours du moment | pas fait (cause confirmée le 19/10) | aucune |
| 10 | Données des sous-agents disponibles | pas fait (quotas) | aucune |

Les conditions 9 et 10 ne sont pas dans ta liste. Je les ajoute parce que, sans elles, les
conditions 1 et 8 mesurent un système différent de celui qui toucherait le réel.

## 2. Détail

### 1. Lectures du registre faites, et leur résultat
- **État :**
  - Q3.a (verdicts du pipeline) : lecture le 03/11/2026, échéance le 01/12/2026 ;
  - Q2 (mode Prudent) : échéance le 26/01/2027 ;
  - §7 Jev : première observation le 09/10/2026. Le contrôle du régime porte sur les
    10 premiers jours de bourse (jusqu'au 22/10/2026), et la lecture unique a lieu le 11/01/2027 ;
  - Q1, seuil BUY : n = 125, vers le 16/03/2027 (échéance le 24/08/2027). Q3.b est lue avec Q1 ;
  - Q1, zone d'apprentissage : vers le 15/06/2027 (échéance le 22/02/2028).

  Dates comptées depuis R2 (06/10/2026), d'après `docs/REGISTRE_CRITERES.md` §0.4 et §7.2.
- **Condition :** chaque lecture est faite selon sa règle, une seule fois, et son résultat est
  consigné par un commit daté du registre (§6, Versions). Un résultat « non concluant »
  ne vaut pas feu vert.
- **Vérifier :** la ligne de version du registre pour chaque question ; les sorties de
  `scripts/q3a_compteur.py` et `scripts/jev_bilan.py` à la date prévue.

### 2. `signal_results` alimentée
- **État :** 0 ligne. `journalist.cloturer_signal`, seule fonction qui écrit la table, n'est
  appelée que par `agents/trade_journalist/demo_performance.py`. Aucun code de production ne
  relie la fermeture d'une position à son signal, donc la table restera vide.
  Conséquence : le verdict « base rates » du pipeline est aveugle (TODO §25).
- **Condition :** chaque position paper fermée après une date fixée a sa ligne dans `signal_results`.
- **Vérifier :** un test de bout en bout (ouverture, fermeture, ligne écrite), puis un
  comptage : positions fermées depuis la date = lignes de `signal_results` sur la même période.

### 3. Frais Revolut réels mesurés, seuil annuel connu (W2)
- **État : pas fait.**
  - Le registre et le fantôme Jev déduisent des coûts **hypothétiques** (0,2 % aller-retour hors
    crypto, 1,0 % en crypto, `REGISTRE_CRITERES.md` §0.2).
  - Le paper trader n'en déduit **aucun** : aucun frais, aucun spread dans `agents/paper_trader/`.
  - Le change n'est pas mesurable : les positions réelles sont en dollars, et le montant débité
    en euros n'est pas stocké (D1).
  - La fiscalité n'est prise en compte nulle part.
- **Condition :**
  - des frais, un spread et un coût de change effectifs par classe d'actif (crypto, actions US,
    ETF, matières), mesurés sur tes propres relevés Revolut ;
  - le seuil annuel W2 (environ 6 à 10 points, fiscalité portugaise comprise) recalculé à partir
    de ces mesures ;
  - si ces frais sont plus élevés que les hypothèses, les valeurs du §0.2 sont relevées par un
    commit du registre **avant** la lecture concernée.
- **Vérifier :**
  - une table des pourcentages par classe, avec le nombre d'ordres mesurés et leur période ;
  - le montant débité en euros enregistré pour chaque nouvelle position réelle ;
  - seuls les pourcentages entrent dans le dépôt (règle 9), jamais les relevés.

### 4. Défauts D6-D8 corrigés, avec critère
- **État : pas fait.** Les trois sont ouverts et gelés : chaque entrée du TODO demande un critère
  pré-enregistré au registre avant toute correction, et aucun n'y figure.
  - D6, TODO §20 : intuition qui force un BUY après un veto (`agents/intuition.py:100-102`).
  - D7, TODO §21 : veto Extreme Greed contournable au quotidien, inactif dans le tactical.
  - D8, TODO §22 : tactical limité aux 8 premiers actifs sans position. Ce défaut déséquilibre
    aussi les groupes de Q3.a.
- **Condition :** pour chaque défaut, un critère au registre écrit avant la correction, un
  commit de correction et un test.
- **Vérifier :** les trois références (critère, commit, test) pour chaque défaut.

### 5. §29 corrigé (1 € = 1 $ sur les actifs cotés en dollars)
- **État :** relevé le 13/10/2026. Le TODO §29 interdit de corriger avant la fin des fenêtres
  de mesure (rupture de série). Les rendements du registre sont des rapports de prix, donc
  l'unité ne les change pas. Le gel protège surtout les montants paper et le P&L du fantôme.
- **Condition :** taille de position en euros = budget en euros / (prix en dollars × taux EUR/USD),
  et des montants affichés dans leur vraie devise.
- **Vérifier :** un test avec un taux fixé ; la page Portfolio montre la même valeur que le calcul à la main.
- **À trancher :** corriger après le 11/01/2027 (fin de la fenêtre Jev), ou attendre la fin des
  fenêtres de Q1 (2027-2028) ?

### 6. Plafond de la poche pilotée (W4)
- **État : pas fait.** La valeur reste à décider par toi, entre 10 et 20 % du capital
  investissable. La notion n'existe pas dans le code, et la règle des 50 % du capital investi ne
  s'applique qu'au paper.
- **Condition :** le plafond décidé (un pourcentage entre 10 et 20 % du capital investissable),
  écrit dans `.env`. Le code ne pourrait pas le dépasser.
- **Vérifier :** un test qui refuse une proposition au-delà du plafond ; le plafond et le
  montant engagé affichés sur la page Réel.

### 7. Arrêt d'urgence fonctionnel, capital paper qui intègre le P&L réalisé (C3)
- **État : pas fonctionnel.**
  - Le capital paper est constant : `agents/paper_trader/portfolio.py:97-103` part de
    `config.CAPITAL` et n'y ajoute jamais le P&L réalisé (cash = capital − investi).
  - `verifier_capital_minimum` (`agents/analysts/risk_manager/manager.py`), `agents/orchestrator.py`
    et `main.py` comparent `config.CAPITAL` à `CAPITAL_STOP_THRESHOLD` (700). Or `config.CAPITAL`
    est le capital de **référence** lu dans `.env` (1 000 par défaut), pas la valeur courante du
    portefeuille. Il ne baisse jamais avec les pertes, donc l'arrêt ne peut pas se déclencher.
  - Rien de tel n'existe pour le réel.
  - Même corrigé, le capital paper intégrerait aujourd'hui les artefacts des boucles (condition 9).
- **Condition :** un capital paper qui intègre le P&L réalisé, et un arrêt qui compare la valeur
  courante (paper, puis poche pilotée) au seuil. Sous le seuil : plus aucune proposition, un
  email, et un interrupteur manuel qui coupe tout.
- **Vérifier :** un test où la valeur courante passe sous le seuil (aucune proposition, une
  alerte) ; un essai réel de l'interrupteur, noté avec sa date.

### 8. Test de bout en bout en mode « proposition seulement », N semaines
- **État :** pas commencé. Deux briques existent :
  - le conseiller réel (toutes les 4 h) donne des conseils sur tes positions, mais pas une
    décision de l'agent avec une taille ;
  - le fantôme Jev montre la forme d'un test isolé : tables séparées, règles écrites d'avance.
- **Condition :** pendant N semaines (je propose au moins 8, à toi de fixer N), chaque
  proposition est inscrite : actif, action, taille en euros, prix et heure. Tu notes si tu
  l'aurais passée et à quel prix réel. Aucun ordre automatique.
- **Mesures, sans rendement :**
  - propositions par semaine ;
  - part des propositions avec données manquantes ;
  - délai entre la proposition et ton exécution possible ;
  - écart entre le prix proposé et le prix réel, qui donne au passage une mesure pour W2.
- **Vérifier :** la table des propositions (N semaines sans trou, zéro ordre passé par le code).

### 9. Prix d'entrée paper au cours du moment
- **État : pas fait, cause confirmée** (`docs/DIAG_PRIX_ENTREE.md`).
  - Le prix d'entrée est la dernière clôture 1d de `prices`, collectée une fois par jour vers
    06h30 UTC. Depuis R2, ce prix a 25,9 h en médiane à l'ouverture.
  - La surveillance compare au cours du moment toutes les 5 min, et rien n'empêche de rouvrir
    l'actif au même prix figé au passage suivant du tactical.
  - 16 boucles regroupent 313 des 421 positions, et 59 des 70 ouvertures depuis R2. 70 % des
    fermetures ont lieu en moins de 5 min.
- **Condition :** le prix d'entrée est un cours horodaté au moment de la décision.
- **Vérifier :** un test sur la source du prix d'entrée ; sur 4 semaines, la durée des
  positions n'est plus concentrée sous une heure.

### 10. Données des sous-agents disponibles
- **État :** du 07/10 au 19/10 (`docs/CONSOMMATION_API.md`) :
  - le sentiment est à confiance 0 dans 82 à 87 % des décisions (quota NewsAPI) ;
  - le fondamental est à 0 pour 60 % des décisions crypto et pour 100 % des 7 actions hors
    `ACTIONS_US` ;
  - une décision repose donc souvent sur 2 sous-agents sur 4.
- **Condition :** sur 4 semaines, une part minimale (à fixer) de décisions où les 4
  sous-agents ont répondu avec des données.
- **Vérifier :** un comptage au registre (`contributions.*.confiance`) par semaine.

## 3. Ce que ce document ne dit pas

- Il ne dit pas si l'agent est bon : aucun rendement, aucun taux de réussite n'y figure.
- Remplir toutes les conditions ne vaut pas feu vert automatique : la décision reste la tienne.
- L'ordre de priorité est à décider. Les conditions 7, 9 et 2 sont des défauts de code
  vérifiables en quelques jours. Les conditions 1 et 8 prennent des mois.
