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
