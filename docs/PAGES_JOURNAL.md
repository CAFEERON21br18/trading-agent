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
  (200 lignes). Ajouts : `importer_flux` (relevé déjà ouvert, donc lisible depuis la mémoire) et
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
