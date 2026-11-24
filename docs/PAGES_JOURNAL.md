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

## Lot 3 — page « Vue d'ensemble » (`/pro`)

Fichiers : `dashboard/pro/routes.py` (blueprint « pro »), `vue_ensemble.py`, `chiffres.py`,
`comptes.py`, `formats.py`, `courbe_svg.py`, `dashboard/templates/pro_vue.html`, l'entrée « Pro »
de la navigation (`base.html`, 15 entrées), l'enregistrement du blueprint dans `dashboard/app.py`,
deux fichiers de test et `tests/pro_page_fixtures.py`.

- La page est rendue par le serveur : aucune lecture ne passe par du JavaScript. Elle ouvre le
  grand livre et la base de l'agent en lecture seule (testé : empreintes des deux fichiers
  identiques avant et après, `POST /pro` refusé).
- En-tête : titre et bascule EUR / USD, retenue dans l'URL (`?devise=`), comme la période du
  compte paper (`?periode=`). Une valeur inconnue revient au défaut (EUR, tout).
- Un panneau par compte, côte à côte au-delà de 1024 px, empilés en dessous. Cinq chiffres :
  résultat net réalisé, résultat latent, total des frais avec leur part du résultat brut,
  espérance en R, taux de réussite ; sous chacun, le nombre de trades et le badge
  « non décidable · n / 100 » sous 100.
- Panneau paper : la mention « Résultats bruts de frais : le paper trader n'en compte aucun »
  et le filtre de période sont affichés même sans trade. Panneau réel : apports nets et
  dividendes.
- Une courbe par compte, sur deux graphiques séparés, et le tableau des 20 derniers trades clos
  des deux comptes (chaque ligne nomme son compte ; aucune somme).
- Gains et pertes : signe « + » ou « − » toujours écrit ; la couleur le répète. Testé sur la
  page : tout texte coloré en vert commence par « + », en rouge par « − ».
- Sans grand livre, ou pour un compte sans trade, la page le dit et nomme ce qui le remplit.
- Tout texte venu du grand livre est échappé par le gabarit (testé avec un titre contenant du
  HTML). Les journaux ne reçoivent que le type d'une erreur, jamais une valeur lue.

Choix non couverts par la consigne, option prudente retenue :

- **Courbe en SVG écrit par le serveur.** Chart.js est bien dans le dashboard, mais seulement
  par un CDN (`base.html`). La consigne dit « aucun appel à un CDN » : la courbe est donc du SVG
  généré en Python, sans script. **Reste vrai, et non corrigé :** les nouveaux gabarits étendent
  `base.html`, comme demandé, et `base.html` charge Tailwind et Chart.js depuis deux CDN. Les
  pages `/pro` n'ajoutent aucun appel externe, mais elles héritent de ces deux-là, dont leur
  mise en page (classes Tailwind) dépend comme celle des 14 autres pages. Les retirer de
  `base.html` changerait tout le dashboard : noté au TODO, pas fait ici.
- **Bouton « Synchroniser » et lien vers « Mes trades »** : ajoutés à la page avec leurs lots
  (5 et 4), pour que chaque commit soit cohérent.
- **Badge du résultat latent.** Le résultat latent n'est pas une mesure sur des trades clos :
  son détail compte les positions ouvertes (« 1 position sur 2 avec un prix ») et il ne porte
  pas le badge « non décidable ». Apports nets et dividendes non plus (sommes de faits).
- **Frais absents.** Un compte sans aucun frais enregistré (le compte paper) affiche « — » pour
  le total et pour la part, pas « 0,00 € » ni « 0 % » : aucun frais compté n'est pas zéro frais.
- **Lecture en échec.** La page s'affiche avec « Le grand livre n'a pas pu être lu » et aucun
  chiffre, plutôt qu'une erreur 500.
- **Navigation.** Une entrée « Pro » en deuxième position ; « Mes trades » s'ouvrira depuis
  cette page, sans seizième colonne dans une barre déjà serrée sur téléphone.

Tests : `Ran 572 tests` / `OK (skipped=10)` (556 + 6 + 10).

## Lot 4 — page « Mes trades » (`/pro/trades`)

Fichiers : `dashboard/pro/mes_trades.py`, `import_releve.py`, `jetons.py`, `routes_ecriture.py`,
la route `GET /pro/trades` dans `routes.py`, `dashboard/templates/pro_trades.html`, le lien
« Mes trades » de la page `/pro`, deux fichiers de test.

- **Import en deux temps.** (a) `POST /pro/import/apercu` : le fichier arrive dans le corps de la
  requête, il est lu en mémoire et comparé au grand livre ouvert en lecture seule. L'aperçu
  donne les trades à ajouter, ceux déjà présents, les mouvements à ajouter, les lignes ignorées
  par type et les erreurs avec leur numéro de ligne. (b) `POST /pro/import/confirmer` écrit, par
  `importeurs/revolut_csv.py`, donc par les seules fonctions de `ledger/ecriture.py`.
- **Jeton.** Entre les deux, le contenu n'existe que dans la mémoire du processus, sous un jeton
  tiré au hasard, à usage unique, qui expire au bout de 10 minutes. S'il y a une erreur, aucun
  jeton n'est émis : la confirmation est impossible, et le bouton reste caché.
- **Jamais sur le disque.** Le fichier n'est pas envoyé par un formulaire : Werkzeug écrit un
  gros fichier de formulaire dans un fichier temporaire. Il est envoyé tel quel dans le corps
  (`fetch` avec le fichier comme corps) et lu par `request.stream` ; un envoi multipart est
  refusé (415). Testé : le dossier du test et le grand livre sont identiques avant et après
  l'aperçu ; le code de la route n'utilise ni `request.files`, ni `request.form`, ni `open`.
- **Taille.** 2 Mo au plus (2 097 152 octets) : contrôlé sur la longueur annoncée, puis sur ce
  qui est lu. Un fichier vide ou qui n'est pas du texte UTF-8 est refusé avec un message.
- **Positions ouvertes du compte réel** : titre, quantité, prix d'entrée, dernier prix et son
  jour, résultat latent, frais payés à l'achat et leur part du montant ; ligne de total.
- **Trades clos** : résultat brut, frais, résultat net. **Frais** : pour chaque ordre, la
  commission et sa part du montant de l'ordre, ou « frais non détectés ». **Mouvements** : dépôts,
  retraits (signe −), dividendes, dans leur devise.
- **Sécurité.** Les deux routes sont en POST et passent par la garde de toute l'application
  (en-tête `X-AlphaSignal: 1`, sinon 403 ; `tests/test_dashboard_ecriture.py` les couvre comme
  les autres routes modifiantes). Les réponses sont du JSON ; la page insère chaque texte par
  `escHtml`. Testé en exécutant le script de la page avec Node : un type de ligne ou un message
  d'erreur contenant du HTML ressort échappé. Les tableaux, eux, sont rendus par le serveur et
  échappés par le gabarit.

Choix non couverts par la consigne, option prudente retenue :

- **Rien à ajouter.** Si tout le relevé est déjà dans le grand livre, l'aperçu le dit et n'émet
  pas de jeton : confirmer n'écrirait rien.
- **Relevés en attente.** Quatre au plus en mémoire (4 × 2 Mo) ; au-delà, le plus ancien est
  oublié. Un redémarrage du dashboard les oublie tous : il suffit de renvoyer le fichier.
- **Confirmation.** Le relevé est relu en entier avant d'ouvrir le grand livre en écriture ; une
  erreur et le grand livre n'est même pas ouvert. Une seule écriture à la fois (verrou).
- **Devise des lignes.** Résultats (brut, frais, net, latent) dans la devise d'affichage ; prix,
  frais d'un ordre et mouvements dans leur devise d'origine, sans conversion. Sans taux, la
  ligne dit « taux indisponible ».
- **Journaux.** Aucune donnée du relevé n'y va, pas même un compte de lignes : seulement le type
  d'une erreur.
- **`tests/test_dashboard_ecriture.py`** : le nombre de gabarits qui contiennent un `fetch`
  modifiant passe de 4 à 5 (`pro_trades.html`). Cette garde interdit aussi les balises de
  formulaire : la page n'en a pas.

Tests : `Ran 586 tests` / `OK (skipped=10)` (572 + 5 + 9).

## Lot 5 — bouton « Synchroniser »

Fichiers : `dashboard/pro/synchro.py`, la route `POST /pro/synchroniser` (`routes_ecriture.py`), le
bouton et son script dans `pro_vue.html`, un paramètre `valider` dans `importeurs/paper.py` et
`importeurs/taux_change.py`, deux fichiers de test.

- Le bouton est dans l'en-tête de la page `/pro`. Un `POST` lance, dans l'ordre, la
  synchronisation paper puis celle des taux EURUSD, en mode appliquer, et la page affiche le
  rapport des deux (positions lues, positions « boucle », exécutions ajoutées, déjà présentes,
  annulées ; taux ajoutés, déjà présents, jours écartés, devises incertaines).
- **Rien n'est écrit en cas d'erreur.** Les deux écritures sont validées ensemble, dans une
  seule transaction du grand livre. Pour cela, `paper.synchroniser` et `taux_change.importer`
  reçoivent `valider=False` : ils écrivent sans valider, et c'est `synchro.py` qui valide ou
  annule. Leur comportement par défaut ne change pas (les scripts `scripts/ledger_*.py` valident
  comme avant). Tout ce qui peut échouer sans écrire est fait d'abord : lecture des positions
  et répétition à blanc dans un grand livre en mémoire (colonne « boucle » absente, position
  illisible), puis téléchargement des cours.
- Testé : colonne « boucle » absente, position illisible, cours indisponible, erreur pendant
  l'écriture des taux : dans les quatre cas, ni position ni taux n'est inscrit, le grand livre
  est identique octet pour octet, et le message est rendu tel quel. Sans grand livre, un refus
  ne crée pas le fichier.
- La base de l'agent est ouverte en lecture seule (empreinte identique avant et après).
- Aucune tâche planifiée ne lance la synchronisation : les scripts `.ps1` et les cycles ne
  citent ni la route ni le grand livre (testé). C'est une action de Lucia.

Choix non couverts par la consigne, option prudente retenue :

- **« Rien n'est écrit » vaut pour les deux étapes.** Si Yahoo ne répond pas, les positions paper
  ne sont pas inscrites non plus : la consigne dit « si une erreur survient, rien n'est écrit ».
  Conséquence : sans réseau, le bouton ne synchronise rien. Les scripts
  `scripts/ledger_sync_paper.py` et `scripts/ledger_taux.py` restent là pour faire l'un sans
  l'autre.
- **Message d'une erreur imprévue.** Il est rendu à la page avec son type (« RuntimeError : … »).
  Il peut citer une valeur d'une position paper ; il n'est pas écrit dans les journaux, qui ne
  reçoivent que le type.
- **Période des taux** : celle de l'importeur par défaut (7 jours avant le dernier taux stocké,
  ou 365 jours en arrière, jusqu'à hier).
- `tests/test_dashboard_ecriture.py` : 6 gabarits contiennent un `fetch` modifiant (`pro_vue.html`
  s'ajoute).

Tests : `Ran 598 tests` / `OK (skipped=10)` (586 + 10 + 2).
