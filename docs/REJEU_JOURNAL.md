# Rejeu sur plusieurs années — journal de session

Branche `rejeu`, créée depuis `main` (f83fe75) dans le worktree `..\trading-agent-rejeu`.
Consigne du 24/11/2026, mode autonome. Référence de départ, réseau coupé :
`Ran 623 tests` / `OK (skipped=10)`.

Règle de choix quand la consigne ne dit rien : l'option la plus prudente, celle qui désavantage
la stratégie. Chaque choix est noté ici, AVANT le premier lancement du rejeu.

## Lot 1 — le critère, commité seul

- Commit `d195259` : section 10 ajoutée à la fin de `docs/REGISTRE_CRITERES.md` (19 lignes
  ajoutées, aucune ligne modifiée ni retirée). C'est le seul fichier du commit ; aucun code de
  rejeu n'existait.
- La liste des versions du registre (§6) n'est pas complétée : la consigne demande de ne rien
  modifier d'autre dans ce fichier.

## Lot 2 — données

Fichiers : `rejeu/parametres.py` (tous les paramètres), `rejeu/donnees.py`,
`scripts/rejeu_donnees.py`, deux fichiers de test et `tests/rejeu_fixtures.py` ; `.gitignore`
(`data/rejeu/`), garde des journaux et règle de topologie pour le paquet `rejeu`.

- **Univers** : les 23 titres de `data/watchlist.json.exemple` (la liste suivie par git, pas celle
  de la tour).
- **Barres** : yfinance, un jour, depuis le 01/01/2017, `auto_adjust=True` (ouverture, haut, bas
  et clôture ajustés des divisions d'actions et des dividendes). La barre du jour en cours n'est
  jamais gardée.
- **Cache** : un CSV par titre dans `data/rejeu/barres/` (hors git). Un titre en cache n'est pas
  retéléchargé : toutes les relances rejouent les mêmes barres. L'empreinte SHA-256 du cache est
  écrite dans le rapport.
- **Téléchargement du 24/11/2026** : 23 titres, dernière barre le 23/11/2026, empreinte
  `d617f215f49761ce…`.

Contrôles, règles fixées avant le téléchargement :

- lignes sans prix : retirées et comptées ;
- un titre est **inutilisable**, donc écarté et nommé, s'il a un prix nul ou négatif, une date en
  double, un trou de plus de 5 jours de bourse (lundi au vendredi) entre deux barres, ou moins
  de 250 barres. Aucune barre n'est corrigée ni interpolée.

Résultat des contrôles :

| Titres | Première barre | Barres | Contrôles |
|---|---|---|---|
| BTC-USD | 01/01/2017 | 3 614 | rien à signaler |
| ETH-USD | 09/11/2017 | 3 302 | rien à signaler |
| CRO-USD | 14/12/2018 | 2 902 | rien à signaler |
| HBAR-USD | 17/09/2019 | 2 625 | rien à signaler |
| SOL-USD | 10/04/2020 | 2 419 | rien à signaler |
| 14 actions et ETF (AAPL, TSLA, NVDA, MSFT, AMZN, AMAT, AMD, MU, LITE, VST, SPY, QQQ, VOO) | 03/01/2017 | 2 487 | rien à signaler |
| VRT | 02/08/2018 | 2 089 | rien à signaler |
| CEG | 19/01/2022 | 1 217 | rien à signaler |
| GC=F, NQ=F | 03/01/2017 | 2 489 et 2 490 | rien à signaler |
| **CL=F** | 03/01/2017 | 2 489 | **écarté : 2 barres à prix nul ou négatif** (le pétrole d'avril 2020) |

Le rejeu porte donc sur **22 titres**. CL=F est écarté pour la stratégie comme pour la référence.
Un titre entre dans le rejeu à sa première barre : ETH-USD, CRO-USD, HBAR-USD, SOL-USD, VRT et CEG
commencent après le 01/01/2018.

Choix non couverts par la consigne :

- **Sorties hors git.** `data/rejeu/` est ajouté à `.gitignore` ; `reports/` l'était déjà en entier.
  Le rapport `reports/rejeu/RAPPORT.md` ne sera donc pas dans le dépôt : le verdict et ses chiffres
  seront recopiés dans ce journal.
- **Réglages de l'agent.** Le rejeu épingle les valeurs par défaut écrites dans `config.py`
  (« ceux du code ») : risque de 2 % par trade, 50 % du capital investissable, **5 positions
  simultanées**, seuils de confiance 8, 9 et 4, seuils de décision ±2,0. Le `.env` de la tour
  porte 20 positions simultanées : ce n'est pas ce que le rejeu teste. Un test compare ces
  valeurs aux défauts de `config.py`.
- **Seuil d'arrêt d'urgence.** Dans le code, 700 € pour un capital de 1 000 €. Appliqué tel quel,
  il interdirait tout trade avec 100 € de capital (100 € ≤ 700 €). Il est gardé en proportion
  (70 % du capital) pour les configurations à 100 € et 10 000 €, qui ne sont que des mesures de
  sensibilité ; pour 1 000 €, la configuration qui décide, c'est exactement la valeur du code.
- **Devise.** Comme le paper trader (TODO §29), le rejeu compte 1 € = 1 $ : capital en euros,
  cours en dollars pris pour des euros, aucun effet de change.
- **Frais « CFD » des contrats à terme** (GC=F, NQ=F) : la consigne ne cite que les actions, les
  ETF et les cryptos. Ils reçoivent l'écart le plus élevé (0,50 % par côté).

Tests : `Ran 633 tests` / `OK (skipped=10)` (623 + 6 + 4).

## Lot 3 — moteur

Fichiers : `rejeu/analyse.py`, `rejeu/enveloppe.py`, `rejeu/moteur.py`, `rejeu/sorties.py`,
`rejeu/frais.py`, `rejeu/reference.py`, `rejeu/resultat.py`, quatre fichiers de test.
Aucun fichier de `agents/`, `utils/`, `config.py` ni des cycles n'est modifié.

**Ce que le rejeu appelle dans l'agent, sans le réécrire :**

- le score technique : `agents.asset_analyzer._technique` (tendance et score du Market Analyst,
  indicateurs de `utils.indicators`), sur les 500 dernières barres jusqu'à J, comme en production ;
- la collecte : `analyser_actif_complet` ; la décision : `agents.decision_engine.decider` ;
- le risque : `valider_signal` (stop à 1,5 ATR ou sous le support, objectifs, R:R, taille) ;
- le circuit d'ouverture du paper trader, en entier : `executer_ouvertures` (anti-boucle de 24 h,
  Budget Manager et ses modes, Risk Manager sur le prix d'exécution, porte d'entrée `peut_ouvrir`,
  création de la position) ;
- la réévaluation des positions ouvertes : `reevaluer_position` (signal technique inverse fort) ;
- la fermeture : `agents.paper_trader.executor.fermer_position`.

L'agent travaille sur une base SQLite jetable par configuration (`data/rejeu/agent_*.db`, recréée
à chaque lancement) : ses lectures (positions ouvertes, dernières fermetures pour les modes du
Budget Manager) sont les siennes.

**Entrées neutralisées** (liste reprise dans le rapport) : analyste fondamental, analyste de
sentiment, contexte global (Fear & Greed), mémoire, intuition, régime de marché, contrôle de
liquidité de la note de setup, audit métacognitif et pipeline LLM, trailing stop (jamais activé
sans action manuelle), prix frais d'une minute, e-mails, registre des décisions.

**Déroulé d'un jour J :** (1) à l'ouverture, les fermetures décidées la veille puis les
ouvertures, au prix d'ouverture de J ; (2) stop et objectif testés sur le haut et le bas de la
barre de J ; (3) à la clôture, analyse avec les seules barres jusqu'à J, décision, réévaluation ;
(4) valeur du compte. Test « aucun regard vers le futur » : l'analyse de J est identique, que la
série s'arrête à J ou continue avec un futur sans rapport ; un témoin montre qu'une seule barre
de trop change le résultat ; le moteur entier donne les mêmes ordres jusqu'à J.

**Constat sur le code, avant tout lancement.** Le Market Analyst ne rend ACHAT ou VENTE qu'à
partir d'une confiance de 6 ; le score composite vaut alors 0,35 × 6 = 2,1, au-dessus du seuil de
2,0. Avec le seul analyste technique, il n'y a donc **jamais de trade d'apprentissage** : toute
décision est « normale », et la porte du paper trader exige une confiance de 8 (9 après trois
pertes d'affilée). Seuls les signaux techniques de confiance 8 à 10 ouvrent une position. Et le
Budget Manager plafonne chaque trade à 10 % du cash investissable : **50 € au plus pour un capital
de 1 000 €**, 5 € pour 100 € (sous son minimum viable de 15 € : aucun trade possible à 100 €).

Choix non couverts par la consigne, option prudente retenue :

- **Barre de l'entrée.** Stop et objectif sont testés dès la barre du jour d'entrée (la position
  est ouverte à l'ouverture, le haut et le bas viennent après).
- **Ouverture au-delà de l'objectif** : sortie au prix de l'objectif, pas mieux. L'écart
  favorable n'est pas compté.
- **Objectif** : `target_1` (R:R de 2). Le moniteur de l'agent sort dès que le prix atteint le
  premier objectif ; `target_2` n'est donc jamais attendu.
- **Anti-boucle.** L'horloge du rejeu place l'ouverture à 8 h, la séance à 12 h, la clôture à 22 h
  (UTC). Un titre sorti par son stop ou son objectif le jour J ne peut pas être repris à
  l'ouverture de J+1 (moins de 24 h) ; il peut l'être après un week-end.
- **Jour d'exécution.** L'ordre décidé à la clôture de J part à l'ouverture de la barre suivante
  DU TITRE : une action décidée le vendredi s'exécute le lundi ; une crypto, le samedi.
- **Décision sans LLM.** `decider` est appelé par son chemin sans LLM (`origine="chat"`) : ni audit
  métacognitif, ni pipeline. En production, le pipeline peut réduire la taille d'un trade : ici,
  jamais.
- **Résultats vus par l'agent : bruts.** Les modes du Budget Manager et la porte défensive lisent
  le résultat des positions sans frais, comme en production. Les frais sont comptés à côté.
- **Ventes à découvert.** L'agent décide SELL comme BUY : le rejeu garde les deux, dans tous les
  profils. Un compte d'actions au comptant ne permet pas la vente à découvert : le profil
  « Revolut » est un barème de frais, pas un compte. Limite à écrire dans le rapport.
- **Valeur du compte** : capital, résultat net réalisé, résultat latent au dernier cours de
  clôture, financement couru (profil « CFD »). Le capital de l'agent, lui, reste constant, comme
  en production (`config.CAPITAL` ne suit pas le résultat).
- **Référence annuelle** : la valeur entière du compte, à parts égales entre les titres qui cotent
  dans les 7 premiers jours de l'année ; achat à l'ouverture de la première barre, vente à la
  clôture de la dernière ; valeur réinvestie l'année suivante. Un titre coté en cours d'année
  attend l'année suivante.
- **Référence de période** : le capital en autant de parts égales que de titres (22) ; chaque part
  investie à l'ouverture de la première barre du titre depuis le 01/01/2018 (les cinq titres cotés
  plus tard entrent à leur première barre, leur part attend en espèces), gardée jusqu'à la
  clôture du 31/12/2025. Choix qui avantage la référence : SOL-USD, par exemple, y entre dès sa
  cotation.
- **Condition 2 du critère** (« acheter et garder ») : la consigne définit deux références. La
  stratégie devra faire mieux que **les deux** ; les deux chiffres seront donnés.
- **Parts de la référence** : la référence investit tout le capital (pas de réserve de 50 %), ne
  paie que ce que sa part permet, frais compris ; une part trop petite pour payer les frais reste
  en espèces.
- **Année d'un trade** : celle de sa clôture. Une position encore ouverte au 31/12/2025 compte
  dans la valeur du compte, pas dans les trades de la période.
- **Analyses calculées une fois** : le signal technique ne dépend ni du capital ni des frais ; il
  est calculé une fois par titre et par jour, puis relu par les six configurations. Répartition
  sur plusieurs processus, sans effet sur le résultat (testé).

Tests : `Ran 656 tests` / `OK (skipped=10)` (633 + 5 + 9 + 5 + 4). Les tests du moteur fabriquent
le signal technique et vérifient à la main, sur le vrai code de l'agent : taille (50 € sur
1 000 €), stop (entrée − 1,5 ATR), objectif (entrée + 2 distances), frais, valeur du compte jour
par jour, signal inverse, seuil de confiance, cinq positions au plus, anti-boucle.

## Lot 4 — lancement et sorties (écrit AVANT le premier lancement)

Fichiers : `mesures/bootstrap.py` (espérance nette, intervalle par bootstrap), `mesures/courbe.py`
(rendement annualisé), `rejeu/grand_livre.py`, `rejeu/mesure.py`, `rejeu/verdict.py`,
`rejeu/etude.py`, `rejeu/rapport.py`, `rejeu/rapport_limites.py`, `rejeu/texte.py`,
`rejeu/lancement.py`, `scripts/rejeu.py`, deux fichiers de test.

- **Grand livre du rejeu** : `data/rejeu/ledger_rejeu.db`, même schéma, écrit par les seules
  fonctions de `ledger/ecriture.py`. 18 comptes de type `demo` : pour chacune des six
  configurations, le rejeu, la référence rachetée chaque année et la référence gardée sur la
  période. Chaque ordre exécuté est un trade avec ses frais (commission, spread, financement) ;
  l'ordre d'entrée porte le stop initial. La valeur du compte à chaque clôture est dans
  `valeur_quotidienne`. `data/ledger.db` n'est jamais ouvert.
- **Mesures** (paquet `mesures`) : résultat net, espérance nette et son intervalle à 95 %
  (bootstrap par percentiles, 10 000 tirages, graine 20261124), taux de réussite, profit factor,
  part des frais, drawdown maximal, rendement et rendement annualisé, écart à la référence ; par
  configuration, par année et sur 2018–2025. L'année 2026, partielle, est à part.
- **Verdict** : `rejeu/verdict.py` applique le critère du registre §10. Le rapport et la page
  relisent tout dans le grand livre du rejeu : ils donnent les mêmes chiffres.
- **Rien n'est effacé.** Un nouveau lancement déplace le grand livre, le résumé et le rapport
  précédents dans un dossier `archives/`, horodatés.
- **Garde du socle** : non ouverte. `scripts/rejeu.py` n'importe que le paquet `rejeu` ; c'est
  `rejeu` (hors de l'agent) qui lit et écrit son grand livre.

Choix non couverts par la consigne, option prudente retenue :

- **Rendement annualisé** : composé, sur des années de 365,25 jours, à partir du capital la veille
  du 01/01/2018. **Ratio de la condition 2** : rendement annualisé divisé par la valeur absolue
  du drawdown maximal de la valeur quotidienne du compte.
- **Intervalle de l'espérance** : percentiles 2,5 et 97,5 des moyennes de 10 000 rééchantillons.
- **Égalité** : à la condition 2, un ratio égal à celui d'une référence n'est pas « supérieur ».
- **Année sans trade** : son espérance n'est pas positive (elle ne compte pas parmi les 4).
- **Deux commits pour ce lot** : le code est commité avant le premier lancement, pour que le
  rapport cite le commit exact qui a tourné ; les résultats sont ajoutés à ce journal ensuite.

Tests avant le lancement : `Ran 669 tests` / `OK (skipped=10)` (656 + 8 + 5).

## Premier lancement (24/11/2026, 21 h 10 à 21 h 31) : interrompu par un bogue d'écriture

Commit `147f1eb`. Les analyses et les six simulations se sont terminées ; le lancement s'est arrêté
à l'étape suivante, l'écriture dans le grand livre du rejeu :

    ledger._valeurs.EcritureInvalide: valeur doit être strictement positif : Decimal('-0.85498031601326915')

**Cause.** `ledger.enregistrer_valeur` refusait une valeur de compte nulle ou négative. Or la valeur
d'un compte du rejeu est passée sous zéro. Aucune des douze références n'est dans ce cas (vérifié en
les recalculant seules) : c'est un compte de stratégie.

**Ce que j'ai vu de ce lancement.** Rien n'a été écrit dans le grand livre (la transaction a été
annulée), aucun rapport n'a été produit, et je n'ai lu aucun trade ni aucune mesure. Je sais
seulement, par ce message d'erreur, qu'un compte de stratégie a perdu tout son capital à un moment
de la série. Je l'écris ici parce que la correction a été faite en le sachant.

**Correction.** Elle ne touche ni une règle du rejeu ni un paramètre :

- `ledger.enregistrer_valeur` accepte toute valeur finie, de signe quelconque : la valeur d'un
  compte peut être nulle ou négative, et elle est enregistrée telle quelle. `rejeu/parametres.py`,
  le moteur, les frais, les sorties et la référence ne changent pas d'une ligne.
- Le compte n'est PAS arrêté quand il passe sous zéro : l'agent raisonne sur un capital constant
  (`config.CAPITAL` ne suit pas le résultat) et continuerait d'ouvrir des positions ; le rejeu fait
  de même. Arrêter le compte à zéro, ou réduire la taille des positions avec le capital, aurait
  été une règle nouvelle, choisie après avoir vu un résultat : écarté.
- Mesures : un compte qui finit à zéro ou moins a un rendement annualisé de −100 % ; son drawdown
  maximal peut dépasser −100 %.
- `rejeu/lancement.py` archive maintenant les sorties précédentes AVANT de simuler, bases jetables
  de l'agent comprises : les positions du premier lancement sont gardées dans
  `data/rejeu/archives/` (elles auraient été effacées par la relance).

Tests ajoutés : valeur de compte nulle ou négative acceptée par le grand livre, bilan d'un compte
passé sous zéro, archivage des bases jetables. Tout est relancé depuis le début.

## Deuxième lancement (25/11/2026, 18 h 03 UTC) : résultats complets

Commit `c375459`, 12 processus. Durée : 1 492 s (analyses 943 s, six simulations 549 s, écriture
0,4 s). 22 titres, barres jusqu'au 23/11/2026, empreinte `d617f215f49761ce`. Code de l'agent
identique au commit du critère ; aucune erreur journalisée par l'agent ; mêmes trades d'un profil
de frais à l'autre. Grand livre, résumé et rapport écrits (`reports/rejeu/RAPPORT.md`, hors git).

### Verdict : « sans avantage »

Configuration qui décide : 1 000 €, « Revolut », 2018–2025, **580 trades clos**.

1. **Condition 1 : fausse.** Espérance nette −1,79 € par trade ; intervalle à 95 % : de −2,07 € à
   −1,51 €.
2. **Condition 2 : fausse.** Rendement annualisé / drawdown maximal : stratégie −0,961 ; référence
   rachetée chaque année +1,108 ; référence gardée sur la période +0,465.
3. **Condition 3 : fausse.** Espérance nette positive dans 0 des 8 années ; résultat total sans la
   meilleure année (2018) : −950,62 €.

Sur la période : résultat brut +120,50 €, frais 1 160,00 € (580 trades × 2 ordres × 1 €), résultat
net −1 039,50 €. Les positions font 50 € au plus : 2 € de frais par aller-retour en prennent 4 %.
Le compte passe sous zéro en 2025 (rendement annualisé −100 %, drawdown maximal −104,1 %).

| Année | Trades clos | Résultat net | Espérance nette | Intervalle à 95 % | Réussite | Rendement | Référence annuelle |
|---|---|---|---|---|---|---|---|
| 2018 | 59 | −88,88 € | −1,51 € | −2,35 € à −0,61 € | 27,1 % | −9,0 % | −10,5 % |
| 2019 | 57 | −97,14 € | −1,70 € | −2,43 € à −0,95 € | 22,8 % | −10,6 % | +49,7 % |
| 2020 | 62 | −103,83 € | −1,67 € | −2,49 € à −0,87 € | 35,5 % | −13,0 % | +120,4 % |
| 2021 | 107 | −122,16 € | −1,14 € | −1,85 € à −0,34 € | 27,1 % | −17,2 % | +655,5 % |
| 2022 | 77 | −149,89 € | −1,95 € | −2,79 € à −1,02 € | 24,7 % | −24,6 % | −45,9 % |
| 2023 | 72 | −129,00 € | −1,79 € | −2,41 € à −1,15 € | 25,0 % | −31,4 % | +121,6 % |
| 2024 | 90 | −199,32 € | −2,21 € | −2,82 € à −1,58 € | 24,4 % | −64,5 % | +68,5 % |
| 2025 | 56 | −149,29 € | −2,67 € | −3,50 € à −1,75 € | 12,5 % | −137,4 % | +40,5 % |
| 2026 (partielle, à part) | 52 | −110,61 € | −2,13 € | −2,98 € à −1,22 € | 26,9 % | — | +3,5 % |
| **2018–2025** | 580 | −1 039,50 € | −1,79 € | −2,07 € à −1,51 € | 25,2 % | −104,0 % | +6 230,4 % |

Sensibilité (2018–2025), à titre indicatif seulement :

| Capital · frais | Trades clos | Résultat net | Frais payés | Espérance nette | Intervalle à 95 % | Réussite | Rendement / drawdown | Réf. annuelle | Réf. période |
|---|---|---|---|---|---|---|---|---|---|
| 1 000 € · Revolut (décide) | 580 | −1 039,50 € | 1 160,00 € | −1,79 € | −2,07 € à −1,51 € | 25,2 % | −0,96 | +1,11 | +0,47 |
| 1 000 € · CFD | 580 | −38,75 € | 159,25 € | −0,07 € | −0,35 € à +0,21 € | 37,4 % | −0,04 | +0,90 | +0,45 |
| 10 000 € · Revolut | 582 | +120,44 € | 1 164,00 € | +0,21 € | −2,56 € à +3,02 € | 37,5 % | +0,02 | +1,14 | +0,47 |
| 10 000 € · CFD | 582 | −311,30 € | 1 595,74 € | −0,53 € | −3,31 € à +2,28 € | 37,5 % | −0,03 | +0,90 | +0,45 |
| 100 € · Revolut et CFD | 0 | — | — | — | — | — | — | −0,23 et +0,90 | +0,42 et +0,45 |

Lecture : avant frais, les règles gagnent à peu près ce qu'elles perdent (37 % de trades gagnants
pour un objectif à deux fois le stop : l'équilibre est à 33 %). Aucune configuration n'a un
intervalle entièrement au-dessus de zéro, et aucune n'approche « acheter et garder ». À 100 €, le
Budget Manager refuse tout trade (budget sous son minimum de 15 €). Sorties de la configuration
qui décide, 2026 comprise : 397 par le stop, 231 par l'objectif, 4 par signal inverse ; une
position encore ouverte à la dernière barre.

La référence annuelle doit ses chiffres aux cryptos de la liste (2021 : +655,5 %) : c'est le
biais de sélection écrit dans les limites, il joue pour la référence comme pour la stratégie.

### Deux défauts vus à ce lancement, corrigés avant la relance

Aucun ne touche une règle du rejeu, un paramètre, un trade ou le verdict.

1. **Affichage final du script.** Tout était écrit quand `scripts/rejeu.py` a levé
   `UnicodeEncodeError` en affichant les conditions : la console Windows (cp1252) ne connaît pas
   le signe « − ». Le script passe maintenant sa sortie en UTF-8.
2. **Drawdown d'un compte déjà sous zéro.** Pour 2026, la configuration qui décide part d'une
   valeur négative : le rapport écrivait un drawdown de « 0,0 % ». Un drawdown se mesure depuis un
   sommet positif ; sans lui, il est maintenant « non calculable » (« — »). Seule cette case de
   l'année partielle change.

Comme le critère le demande, tout est relancé ; les sorties de ce lancement sont archivées dans
`data/rejeu/archives/` et `reports/rejeu/archives/` (horodatage du lancement suivant).

## Troisième lancement (25/11/2026, 18 h 30 UTC) : le lancement de référence

Commit `dd95f08`, 12 processus, code de sortie 0. Durée : **776 s, soit 13 minutes** (analyses
287 s, six simulations 488 s, écriture 1 s). Le deuxième lancement avait mis 1 492 s : la machine
faisait autre chose pendant ses analyses.

- **Mêmes résultats.** Le contenu du grand livre du rejeu (comptes, trades, frais, valeurs
  quotidiennes, hors dates de saisie) a la même empreinte qu'au deuxième lancement
  (`fe88fe71d391a3b2`) : 7 388 ordres, 56 520 valeurs quotidiennes. Le rejeu est déterministe.
- **Même rapport**, à une case près, celle qui a été corrigée : le drawdown de 2026 (année
  partielle, compte déjà sous zéro) s'écrit « — » au lieu de « 0,0 % ».
- **Même verdict : « sans avantage »**, avec les chiffres de la section précédente.
- Aucune erreur journalisée par l'agent ; code de l'agent identique au commit du critère.
- Archivés : les sorties du premier lancement (bases jetables, grand livre vide) et celles du
  deuxième (grand livre, résumé, rapport, bases jetables).

## Lot 5 — page et documentation

Fichiers : `dashboard/pro/rejeu_vue.py`, `dashboard/pro/courbe_rejeu.py`, la route `GET /pro/rejeu`
(`dashboard/pro/routes.py`), `dashboard/templates/pro_rejeu.html`, le lien « Rejeu » de la page
`/pro`, un fichier de test ; `CLAUDE.md`, `README.md`, `docs/TODO.md` §45.

- **Lecture seule.** La page ouvre `data/rejeu/ledger_rejeu.db` en lecture seule et ne lance
  rien ; elle relit ses chiffres par `rejeu/etude.py`, comme le rapport. Testé : fichier inchangé,
  `POST` refusé, `data/ledger.db` jamais ouvert.
- **Contenu** : le verdict et ses trois conditions, toujours ceux de la configuration du critère ;
  le choix de la configuration (six liens, retenu dans l'URL) ; une autre configuration est dite
  « mesure de sensibilité » ; ses chiffres de période ; la valeur du compte de la stratégie et
  des deux références sur un même graphique ; le tableau par année.
- **Mentions toujours visibles**, en tête, même si le rejeu n'a jamais été lancé : « hypothèses de
  frais CFD », « biais de sélection », et ce que le rejeu teste.
- **Graphique** : SVG écrit par le serveur, sans texte dans le dessin (comme la courbe corrigée de
  la page « Vue d'ensemble ») ; les trois courbes se distinguent par leur trait (plein, tirets,
  pointillé), nommé dans la légende ; un point par semaine.
- **Garde du socle** : `tests/test_socle_hors_production.py` n'a PAS eu à être ouverte. La page est
  dans `dashboard/pro/`, déjà autorisé ; `scripts/rejeu*.py` n'importent que le paquet `rejeu`. Une
  garde nouvelle (`tests/test_rejeu_isolement.py`) vérifie le sens inverse : aucun module de
  l'agent n'importe `rejeu`.
- **Calcul gardé en mémoire** tant que le fichier du grand livre ne change pas (le bootstrap de
  10 000 tirages n'est pas refait à chaque affichage).

Vérifié dans un navigateur, sur un dashboard de démonstration (port 8099) qui lisait une copie du
grand livre du deuxième lancement : page complète sur grand écran ; à 390 px et 320 px de large,
aucun débordement horizontal, aucun chevauchement entre la légende et les graduations. Un défaut
vu et corrigé à cette occasion : à 390 px, deux libellés de la légende sortaient de leur carte
(ils ne pouvaient pas passer à la ligne). Le dashboard de production n'a pas été touché.

Choix non couverts par la consigne :

- **Pas d'entrée de navigation de plus** : « Rejeu » s'ouvre depuis la page Pro, comme « Mes
  trades ».
- **L'axe du graphique est linéaire et part de zéro.** Les références finissent 15 à 65 fois plus
  haut que le capital : la courbe de la stratégie y paraît plate. C'est l'écart réel ; un axe
  logarithmique ne saurait pas montrer un compte passé sous zéro.

Tests : `Ran 678 tests` / `OK (skipped=10)` (671 + 7).


## Fin de session (25/11/2026)

**Verdict : « sans avantage ».** Configuration qui décide (1 000 €, « Revolut », 2018–2025),
580 trades clos :

1. Condition 1, fausse : espérance nette −1,79 € par trade, intervalle à 95 % de −2,07 € à −1,51 €.
2. Condition 2, fausse : rendement annualisé / drawdown maximal de −0,961, contre +1,108 pour la
   référence rachetée chaque année et +0,465 pour la référence gardée sur la période.
3. Condition 3, fausse : espérance nette positive dans 0 des 8 années ; résultat total sans la
   meilleure année : −950,62 €.

**Durée d'un lancement** : 776 s (13 minutes) pour le lancement de référence, sur 12 processus ;
1 492 s pour le deuxième, machine occupée.

**Suite de tests** : `Ran 678 tests` / `OK (skipped=10)`, réseau coupé. Départ : 623. Les 55 tests
ajoutés : 10 au lot 2, 23 au lot 3, 13 au lot 4, 2 pour les correctifs, 7 au lot 5. Avec un graphe
régénéré dans le worktree (coût LLM nul, puis retiré), les 18 tests de topologie passent.

**Contrôles avant la poussée.**

- Aucun fichier `.env`, base SQLite, CSV, ni rien de `data/rejeu/` ou de `reports/rejeu/` n'est
  suivi par git.
- Règle 9 : le diff `main..HEAD` et les messages de commit comparés aux tables du portefeuille
  réel et au compte réel du grand livre de production, en lecture seule, sans afficher de
  valeur : aucune correspondance. Le rejeu ne lit que des cours publics.
- Aucune ligne d'attribution automatique ; aucun fichier de plus de 200 lignes.
- `agents/`, `utils/`, `alerts/`, `config.py`, les cycles et les scripts de tâches : aucune
  modification. `docs/REGISTRE_CRITERES.md` : 19 lignes ajoutées, aucune modifiée.
- Depuis le commit du premier lancement (`147f1eb`), dans `rejeu/` : seuls `grand_livre.py` et
  `lancement.py` (archivage) et `mesure.py` (drawdown d'un compte sous zéro) ont changé.
  `rejeu/parametres.py` n'a pas changé depuis le lot 2 ; le moteur, les frais, les sorties, la
  référence et l'enveloppe n'ont pas changé depuis avant le premier lancement.
- Le rejeu a tourné dans le worktree : la copie de production n'a pas de `data/rejeu/`, et ni
  `data/database.db`, ni `data/registre.db`, ni `data/ledger.db` n'ont été ouverts.
- Ni Jev ni aucun LLM n'a été appelé ; aucun e-mail envoyé. Seul appel réseau : le téléchargement
  des barres quotidiennes chez Yahoo, le 24/11/2026.

**Écarts à la consigne, et choix faits sans consigne.**

1. **Trois lancements au lieu d'un.** Le premier s'est arrêté à l'écriture (valeur de compte
   négative refusée) ; le deuxième a donné tous les résultats, puis le script a échoué en les
   affichant ; le troisième est propre et identique au deuxième. Aucun paramètre n'a changé.
2. **Neuf commits pour cinq lots** : le code du lot 4 a été commité avant le premier lancement,
   et chaque correctif a été commité seul avant sa relance, pour que chaque rapport cite le commit
   qui a tourné.
3. **`ledger.enregistrer_valeur` accepte une valeur nulle ou négative** : changement dans le socle,
   nécessaire pour enregistrer le compte tel qu'il est.
4. **Le compte n'est pas arrêté quand il passe sous zéro** (l'agent raisonne sur un capital
   constant) : son rendement annualisé vaut alors −100 %.
5. **Condition 2 : les deux références** doivent être dépassées.
6. **Seuil d'arrêt d'urgence en proportion du capital** (70 %) pour 100 € et 10 000 €.
7. **Réglages du code épinglés** (5 positions simultanées), pas ceux du `.env` de la tour.
8. **Ventes à découvert gardées**, dans tous les profils ; **1 € = 1 $**.
9. **Frais « CFD » des contrats à terme** : 0,50 %, comme les cryptos.
10. **CL=F écarté** (prix négatifs en avril 2020), pour la stratégie comme pour la référence.
11. **Le rapport n'est pas dans le dépôt** (`reports/` est hors git) : ses chiffres sont dans ce
    journal.
12. **La garde `test_socle_hors_production.py` n'a pas été ouverte** : rien ne l'exigeait.
13. **Décision par le chemin sans LLM du moteur** (`origine="chat"`) ; contrôle de liquidité de la
    note de setup tenu pour bon.

**Pour relancer sur la tour, après fusion** (PowerShell, depuis la racine du dépôt) :
`.venv\Scripts\python.exe scripts\rejeu_donnees.py` puis `.venv\Scripts\python.exe scripts\rejeu.py`.
Les barres seront retéléchargées sur la tour (le cache du worktree n'est pas dans git) : elles
iront jusqu'à la veille, et Yahoo peut avoir révisé un cours ; le résultat pourra donc différer
de quelques trades. Puis relancer le dashboard et ouvrir `http://localhost:8080/pro/rejeu`.
