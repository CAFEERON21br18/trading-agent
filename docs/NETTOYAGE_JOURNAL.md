# Journal du nettoyage — TradingX / AlphaSignal

- Début : 23/11/2026. Branche `nettoyage-public`, partie de `38300ca` (= `origin/nettoyage`).
- Source : `docs/NETTOYAGE_INVENTAIRE.md` ; les numéros (1.1, 2.6, 7.4…) renvoient à ses lignes.
- Règle centrale : aucun retrait ne change une décision de l'agent (score, seuil, taille de
  position, ordre paper, écriture du registre). Un retrait qui le pourrait n'est pas fait : il est
  noté ici.
- Tests : `.venv\Scripts\python.exe -m unittest discover -s tests`, dans le worktree de la branche,
  réseau coupé (`HTTP_PROXY=HTTPS_PROXY=ALL_PROXY=http://127.0.0.1:9`). Le fichier
  `graphify-out/graph.json` (hors git) est absent du worktree : 10 tests de `tests/test_topology.py`
  sont ignorés, comme dans la référence.
- Référence de départ, relancée sur `38300ca` : `Ran 470 tests` / `OK (skipped=10)`.

## Lot 0 — Corrections urgentes

Parti ou corrigé :

- `.env.example` : `RISK_PER_TRADE_PCT=2` au lieu de 50 (8.26).
- `.env.example` : les 11 variables manquantes (8.27), avec la valeur par défaut du code :
  `GEMINI_API_KEY` et `GROQ_API_KEY` (vides), `MAX_CAPITAL_INVESTI_PCT=50`,
  `MAX_POSITIONS_SIMULTANEES=5`, puis en commentaire, comme les autres réglages optionnels du
  fichier : `SEUIL_CONFIANCE_PAPER=8`, `SEUIL_CONFIANCE_PAPER_DEFENSIF=9`,
  `SEUIL_CONFIANCE_LEARNING=4`, `ROTATION_ACTIVE=0`, `CHAT_HISTORIQUE=0`,
  `CHAT_HISTORIQUE_MAX_MIN=120`, `TAILSCALE_EXE_PATH` (chemin par défaut de `utils/tailscale.py:16`).
- `REPORT_TIME` retirée de `.env.example` et de `config.py` (8.28) : la constante n'était
  qu'affichée par `afficher_config()` ; la ligne affiche maintenant le fuseau seul.
- `CLAUDE.md`, règles absolues : règle 10, « Aucune ligne Co-Authored-By ni Claude-Session dans les
  messages de commit de ce dépôt. »
- `requirements.txt` : `matplotlib`, `plotly`, `schedule`, `pytz` retirées (10.1 à 10.4) ; `tzdata`
  ajoutée (10.6).

Resté :

- `MAX_POSITIONS_SIMULTANEES=5` dans le modèle est le défaut du code, comme demandé ; `CLAUDE.md`
  décrit 20, valeur du `.env` de la tour (non lu). L'écart est traité au lot 6 (8.16).
- La phrase « Laisser à 0 jusqu'au 28/10/2026 » de `.env.example` (8.12) attend la lecture de
  `EXCLURE_BOUCLES_STATS` (lots 5 et 6).

Tests : `Ran 470 tests` / `OK (skipped=10)`.
