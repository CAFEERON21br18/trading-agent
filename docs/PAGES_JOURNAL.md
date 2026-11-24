# Pages du dashboard professionnel — journal de session

Branche `pages-dashboard`, créée depuis `main` (340f608) dans le worktree `..\trading-agent-pages`.
Consigne du 24/11/2026, mode autonome : pages « Vue d'ensemble » (`/pro`) et « Mes trades »
(`/pro/trades`), qui lisent le grand livre (`data/ledger.db`).

Référence de départ, réseau coupé : `Ran 521 tests` / `OK (skipped=10)`.

Lu avant de commencer : la section « Grand livre et mesures » de `CLAUDE.md`,
`docs/SOCLE_JOURNAL.md`, les trois paquets du socle, `dashboard/app.py`,
`dashboard/api/garde_ecriture.py`, `dashboard/templates/base.html`, `tests/test_dashboard_ecriture.py`
et le §9.4 de `docs/REGISTRE_CRITERES.md` (lu, non modifié).

## Lot 1 — mouvements d'argent dans le grand livre

Fichiers : `ledger/schema.py`, `ledger/ecriture.py`, `ledger/lecture.py`, `ledger/_valeurs.py`,
`importeurs/revolut_csv.py`, `importeurs/revolut_lecture.py`, `mesures/mouvements.py`, deux fichiers
de test et `tests/socle_ancien_schema.py`.

- **Table `mouvements`**, en écriture seule (mêmes déclencheurs UPDATE et DELETE que les sept
  autres) : compte, horodatage, type (`depot`, `retrait`, `dividende`), montant, devise,
  instrument facultatif, source, `ref_source`, unicité sur `(source, ref_source)`. Le montant est
  toujours positif : contrôlé par `enregistrer_mouvement` et par une contrainte de la table.
- **Base existante** : la table est créée par `CREATE TABLE IF NOT EXISTS` à la première
  ouverture en écriture (`ledger.ouvrir`). Testé sur un grand livre à l'ancien schéma
  (`tests/socle_ancien_schema.py`, copie mot pour mot de `ledger/schema.py` à 340f608), avec des
  lignes dans les sept tables : schéma, index, déclencheurs et lignes identiques avant et après ;
  seuls la table, son index et ses deux déclencheurs s'ajoutent.
- **`ledger/ecriture.py`** : `enregistrer_mouvement`, idempotent comme `enregistrer_trade`
  (`None` si la référence est déjà là). Pour rester sous 200 lignes, les quatre contrôles de
  valeurs (`EcritureInvalide`, `_positif`, `_iso`, `_maintenant`) sont sortis dans
  `ledger/_valeurs.py`, sans changement.
- **`ledger/lecture.py`** : `mouvements(conn, compte_id)`. Ajouts pour les pages, qui lisent sans
  écrire : `comptes(conn)`, `references_presentes(conn, table, source)` et, dans `schema.py`,
  `ouvrir_lecture(chemin)` (lecture seule, `None` si le fichier manque, rien n'est créé). Sur un
  grand livre ouvert en lecture seule et créé avant la table, `mouvements` rend une liste vide.
- **`importeurs/revolut_csv.py`** : DIVIDEND, CASH TOP-UP et CASH WITHDRAWAL deviennent des
  mouvements ; un retrait est enregistré par sa valeur absolue ; un dividende garde son titre.
  L'import reste tout ou rien et sans doublon (référence = empreinte de la ligne, comme pour les
  trades ; les références des trades déjà importés ne changent pas). Les autres types restent
  ignorés et comptés. La lecture du fichier est sortie dans `importeurs/revolut_lecture.py`
  (règle des 200 lignes). Ajouts : `importer_flux` (relevé déjà ouvert, donc lisible depuis la mémoire) et
  `apercu` (compte ce qu'un import ajouterait, par lecture seule).
- **`mesures`** : `dividendes(mouvements)` et `apports_nets(mouvements)` rendent une `Mesure`
  (nom, valeur, n, période, décidable, raison) ; `mouvements_en_devise` bascule les montants au
  taux du jour du mouvement.

Choix non couverts par la consigne, option prudente retenue :

- **Type exact.** Seuls les trois types cités deviennent des mouvements. Un type voisin
  (« DIVIDEND TAX (CORRECTION) », par exemple) reste ignoré et compté : l'additionner ou le
  retrancher sans avoir vu un vrai relevé aurait été deviner.
- **Montant nul ou négatif.** Un retrait négatif est attendu (valeur absolue). Un dépôt ou un
  dividende négatif, ou un montant nul ou absent, est une erreur de ligne : l'import entier est
  refusé et la ligne est nommée. Raison : le grand livre ne s'efface pas ; inverser le signe ou
  ignorer la ligne en silence aurait faussé les apports.
- **Seuil de 100 trades.** Il ne s'applique pas aux deux nouvelles mesures : ce sont des sommes
  de faits, pas des estimations. Elles sont décidables dès qu'il y a un mouvement ; sans
  mouvement, la valeur est `None` (« non calculable »), jamais 0.
- **Signature de `lire`.** Elle rend maintenant trois valeurs (trades, mouvements, rapport) ; le
  seul appelant hors de l'importeur était un test, adapté.

Tests existants modifiés, parce que la consigne change le comportement : `tests/test_import_csv.py`
(le dépôt et le dividende du relevé d'exemple ne sont plus « ignorés » mais comptés comme
mouvements) et `tests/test_ledger.py` (8 tables au lieu de 7 dans le test des déclencheurs).

Tests : `Ran 535 tests` / `OK (skipped=10)` (521 + 8 + 6).

## Lot 2 — préparation des données (module pur)

Fichiers : `dashboard/pro/donnees.py`, `dashboard/pro/latent.py`, `dashboard/pro/prix.py`,
`tests/pro_fixtures.py`, deux fichiers de test ; `tests/test_socle_hors_production.py` ouvert.

- **Emplacement.** Le paquet `dashboard/pro/` est le nouveau blueprint : ses routes viendront aux
  lots 3 à 5. Ces trois modules n'importent ni Flask ni aucun module de l'agent ; un test le
  vérifie dans un processus séparé.
- **Garde de la règle centrale.** `tests/test_socle_hors_production.py` est ouvert pour
  `dashboard/pro/`, et pour lui seul : `dashboard/app.py` et le reste du dashboard restent fermés
  au socle. Deux gardes ajoutées : `dashboard/pro` n'est importé que par `dashboard/app.py`
  (aucun cycle, ni le moteur de décision, ni le paper trader ne peuvent atteindre le grand livre
  par ce chemin) ; rien du fantôme Jev dans `dashboard/pro` ni dans ses gabarits.
- **Un compte, et un seul.** `charger(conn, compte_id)` refuse l'absence de compte, et chaque
  fonction reçoit la source d'un seul compte : aucune fonction n'additionne deux comptes.
- **Blocs** (une fonction chacun, pour un compte et une devise d'affichage EUR ou USD) : trades
  clos, positions ouvertes, tableau des mesures, dividendes, apports nets, total des frais,
  résultat latent, série du résultat net réalisé cumulé par jour de clôture. S'y ajoute
  `lignes_trades`, pour les tableaux : la bascule y est tentée trade par trade.
- **Taux manquant.** Le bloc rend « taux indisponible » au lieu d'un chiffre. Sans bascule à
  faire (devise d'affichage = devise des montants), le chiffre existe même sans aucun taux.
- **Résultat latent.** Dernier prix de la table `prices` de la base de l'agent, ouverte en
  lecture seule ; prix absent ou de plus de 3 jours : « prix indisponible », position exclue du
  total ; aucune position valorisée : total `None`, jamais 0. La bascule en devise d'affichage
  prend le dernier taux connu au jour de la lecture.

Choix non couverts par la consigne, option prudente retenue :

- **Date du correctif du prix d'entrée.** Le registre (§9.4) ne donne pas un jour mais une règle :
  « l'`entry_date` de la première position paper enregistrée avec la version 2 du mécanisme
  d'entrée ». La valeur a donc été lue dans la base de la tour, en lecture seule, le 24/11/2026 :
  plus ancienne `entry_date` des positions où `mecanisme_entree` = 2, soit le 21/10/2026 à
  13:31:27 UTC ; aucune position d'un autre mécanisme n'a été ouverte après. Elle est dans la
  constante `CORRECTIF_PRIX_ENTREE`, avec sa référence. C'est une date de position paper, pas une
  donnée du portefeuille réel. Le registre n'est pas modifié.
- **Filtre de période.** Il porte sur la date d'ouverture : un trade ouvert avant le correctif et
  clos après est du côté « avant ».
- **Dernier prix.** Barres « 1d » et « 4h » (qui contient les barres horaires des cryptos), la
  plus récente. Les barres hebdomadaires sont écartées : datées du lundi, elles fausseraient
  l'âge. L'âge se compte en jours calendaires entre le jour de la barre et le jour de la
  lecture : le cours du vendredi sert encore le lundi (3 jours), plus le mardi.
- **Devise autre que l'euro et le dollar.** La bascule du socle ne connaît que EUR et USD. Un
  montant en livres, par exemple, donne « devise non convertie : GBP » : jamais de conversion au
  hasard.
- **Total des frais.** Il compte tous les ordres du compte, positions ouvertes comprises. La
  « part des coûts » du socle, elle, porte sur les trades clos : les deux chiffres seront
  libellés séparément sur la page.
- **Dividendes et apports nets** sont basculés séparément : un dividende sans taux ne prive pas
  la page des apports.
- **`mesures.PositionOuverte`** reçoit un champ `couts` (frais d'entrée de la quantité encore
  ouverte), nécessaire au lot 4 ; valeur par défaut 0, calculs existants inchangés.

Tests : `Ran 556 tests` / `OK (skipped=10)` (535 + 11 + 8 + 2).
