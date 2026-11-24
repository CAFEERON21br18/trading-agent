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
