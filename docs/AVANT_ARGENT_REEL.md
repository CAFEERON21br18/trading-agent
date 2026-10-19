# Avant l'argent réel : conditions objectives (19/10/2026)

**Ce document ne décide rien.** Il liste les conditions à remplir avant qu'une décision de
l'agent soit appliquée au portefeuille réel. Même alors, c'est toi qui passerais l'ordre à
la main sur Revolut. Il n'y a aucun code d'exécution d'ordre, et ce document n'en prévoit
pas. Aujourd'hui, l'agent conseille sur le réel et n'agit jamais (CLAUDE.md, « Portefeuille RÉEL »).

**Repères W2, W4, C3, D6-D8.** Je les reprends de ta demande. Leur définition n'est ni dans
le dépôt ni dans la mémoire de l'agent, et le « journal du council » n'est pas sur la tour.
J'applique à W2, W4 et C3 le sens donné par ta phrase. D6-D8 restent à préciser.

## 1. Vue d'ensemble

| # | Condition | État au 19/10/2026 | Date prévue |
|---|---|---|---|
| 1 | Lectures du registre faites (Q1, Q3, §7 Jev) | en cours | 03/11/2026 (Q3.a) ; 11/01/2027 (Jev) ; ≈ 16/03/2027 (Q1) |
| 2 | `signal_results` alimentée | pas fait | aucune |
| 3 | Frais Revolut réels mesurés (W2) | pas fait | aucune |
| 4 | Défauts D6-D8 corrigés, avec critère | inconnu (définitions introuvables) | — |
| 5 | §29 (1 € = 1 $) corrigé | pas fait, gelé volontairement | après les fenêtres de mesure |
| 6 | Plafond de la poche pilotée (W4) | pas fait (notion absente du code) | aucune |
| 7 | Arrêt d'urgence fonctionnel (C3) | **pas fonctionnel** | aucune |
| 8 | Test de bout en bout « proposition seulement », N semaines | pas commencé | aucune |
| 9 | Prix d'entrée paper au cours du moment | pas fait (relevé le 19/10) | aucune |
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

### 3. Frais Revolut réels mesurés (W2)
- **État :**
  - le registre et le fantôme Jev déduisent des coûts **estimés** (0,2 % aller-retour hors
    crypto, 1,0 % en crypto, `REGISTRE_CRITERES.md` §0.2) ;
  - le paper trader n'en déduit **aucun** : aucun frais, aucun spread dans `agents/paper_trader/`.
- **Condition :** des frais et un spread effectifs par classe d'actif (crypto, actions US,
  ETF, matières), mesurés sur tes propres relevés Revolut. Si ces frais sont plus élevés que
  les estimations, les valeurs sont relevées par un commit du registre **avant** la lecture
  concernée (§0.2).
- **Vérifier :** une table des pourcentages par classe, avec le nombre d'ordres mesurés et
  leur période. Seuls les pourcentages entrent dans le dépôt (règle 9), jamais les relevés.

### 4. Défauts D6-D8 corrigés, avec critère
- **État :** inconnu, faute de définition.
- **Condition :** pour chaque défaut, une entrée au TODO, un commit de correction, un test et,
  si le défaut touche une série mesurée, un critère au registre écrit avant la correction.
- **Vérifier :** les trois références (TODO, commit, test) pour chaque défaut.

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
- **État :** la notion n'existe pas dans le code. La règle des 50 % du capital investi ne
  s'applique qu'au paper.
- **Condition :** un montant maximal, fixé d'avance, de la part du portefeuille réel où une
  proposition de l'agent peut être appliquée. Il serait écrit dans `.env`, et le code ne
  pourrait pas le dépasser.
- **Vérifier :** un test qui refuse une proposition au-delà du plafond ; le plafond et le
  montant engagé affichés sur la page Réel.

### 7. Arrêt d'urgence fonctionnel (C3)
- **État : pas fonctionnel.** `verifier_capital_minimum` (`agents/analysts/risk_manager/manager.py`),
  `agents/orchestrator.py` et `main.py` comparent `config.CAPITAL` à `CAPITAL_STOP_THRESHOLD`
  (700). Or `config.CAPITAL` est le capital de **référence** lu dans `.env` (1 000 par défaut),
  pas la valeur courante du portefeuille. Il ne baisse jamais avec les pertes, donc l'arrêt ne
  peut pas se déclencher. Rien de tel n'existe pour le réel.
- **Condition :** l'arrêt compare la valeur courante (paper, puis poche pilotée) au seuil.
  Sous le seuil : plus aucune proposition, un email, et un interrupteur manuel qui coupe tout.
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
- **État :**
  - 315 des 418 positions paper fermées ont duré moins d'une heure (en octobre, 68 fermées,
    durée médiane 0,1 h) ;
  - le prix d'entrée est la dernière barre de `prices`, collectée une fois par jour. À
    l'ouverture, elle a 46 h en médiane (69 ouvertures depuis le 06/10). La surveillance compare
    au cours du moment ;
  - cause probable, à vérifier (`docs/HORIZONS.md`, §4).
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
