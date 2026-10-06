# TODO — hors périmètre

Points relevés pendant la Phase 4 (audit du chat stratégique, 01/10/2026).
Non traités : chacun fera l'objet d'un travail séparé.

## ⚠️ PRIORITÉ HAUTE — Décisions du cycle tactical persistées nulle part

- `scripts/cycle_tactical.py:63-74` : `decider()` tourne toutes les 15 min
  (queue ≤ 5 tickers + 8 tickers de la watchlist hors positions ouvertes).
  Les décisions restent en mémoire le temps d'`executer_ouvertures`, puis
  sont perdues : HOLD, NO_TRADE, et BUY/SELL refusés par le Budget Manager
  ne laissent aucune trace.
- Seule trace existante : la table `signals`, écrite par la routine
  quotidienne (un lot vers 07h40), uniquement pour les BUY/SELL validés
  par le Risk Manager.
- **Prérequis du registre de signaux.** Conséquence immédiate : le chat ne
  peut pas réutiliser une décision de cycle ; depuis E2 il calcule sa propre
  décision à la volée (`decider(..., origine="chat")`). Relevé le 03/10/2026,
  volontairement non traité dans E2.

## 1. Rotation des logs cassée (Windows)

- Les cycles et le dashboard écrivent tous dans `logs/alphasignal.log` et
  `logs/errors.log` via `RotatingFileHandler` (`utils/logger.py`). La
  rotation échoue : `PermissionError: [WinError 32]`, le fichier est
  ouvert par un autre processus.
- Le fichier n'est jamais renommé, donc chaque nouvelle ligne de log tente
  une rotation, échoue et déverse une trace « --- Logging error --- » sur
  stderr, redirigée dans `logs/task_*.log`.
- Au 01/10/2026 : `alphasignal.log` n'est plus écrit depuis le 25/09,
  `errors.log` depuis le 26/09, `task_tactical.log` atteint 529 Mo.

## 2. Classement des erreurs LLM par sous-chaîne

- Groq (`utils/llm.py::_try_groq`) : `"429" in err or "rate" in err` →
  `rate_limit_groq`, avec retry dans 60 s.
- L'erreur brute est maintenant visible dans `message_audit.chaine_de_fallback`.
  Le 01/10 (enregistrement #2), elle montre que le 429 venait du **quota
  quotidien de tokens** (TPD : 200 000/jour, 199 997 utilisés), pas d'une
  limite par minute. Le délai de 60 s est donc faux, et c'est le budget
  quotidien que les cycles consomment.
- Gemini suit le même schéma (`utils/gemini.py`, `ask_gemini` et
  `ask_gemini_status` : « 429 », « rate », « quota »). En plus,
  `ask_gemini_status` remplace le message d'origine par un texte fixe pour
  toutes les catégories connues : l'audit ne voit l'erreur brute de Gemini
  que pour les erreurs « inconnu ».

## 3. Bandeau d'erreur générique du chat

- `agents/chat/_llm.py`, `MESSAGES_ERREUR_UI["both_failed"]` affiche
  « Gemini en quota et fallback Groq KO » quelle que soit la cause réelle
  (clé invalide, 503, réseau, quota Groq…).
- Les erreurs réelles des deux fournisseurs sont désormais enregistrées dans
  `message_audit.chaine_de_fallback`, mais pas montrées à l'utilisateur.

## 4. Conseils réels non répondus chargés en entier à chaque message

- `agents/chat/context_builder.py::build_context` charge
  `lire_conseils_actifs()` à chaque message du chat : 1 248 conseils non
  répondus au 01/10/2026, soit environ 504 000 caractères.
- Seul leur nombre est utilisé (`agents/chat/_formatters.py`,
  `len(advice)`). La liste n'est jamais injectée dans le prompt.
- Depuis la Phase 4, `message_audit` n'en stocke qu'un extrait (20 conseils
  et le total), mais le chargement complet a toujours lieu.

## 5. `memory/metacognition_log.md` : ne jamais l'utiliser comme source

- **Aucun code ne le lit** : seul `agents/skills/_log.py` y écrit. Ni le
  pipeline (ses signaux comportementaux viennent de la base), ni
  `memory_reader`, ni le module `learner`, ni la page Memory du dashboard.
- **Ne jamais l'utiliser comme source du registre de signaux** : texte libre,
  aucune origine enregistrée (cycle, chat, conseiller réel), et la période
  22/06 → 02/09/2026 n'est pas vérifiable (messages du chat effacés, aucun
  journal sur ce PC).
- Entrées venant du chat, connues (rapport E3 du 03/10/2026) :
  ligne 18778 (01/10 22:07 UTC, AMAT, **confirmée** par `message_audit`),
  ligne 3982 (02/09 00:19 UTC, AAPL, **probable**). Non marquées
  volontairement : une modification sur place entrerait en concurrence avec
  les cycles qui écrivent dans le fichier. Depuis E2, le chat n'y écrit plus.

## 6. Piste quota LLM : l'audit métacognitif des cycles

- `agents/decision_engine_meta.py::audit_metacognitif` fait un appel Gemini
  direct pour chaque décision sauf HOLD (BUY, SELL et NO_TRADE ; cycles et
  conseiller réel). Son résultat (`resultat["metacognition"]`) n'est lu par
  **aucun code** et n'est sérialisé nulle part : il ne change ni l'action ni
  la taille. (Correction du 05/10 : `decision_formatter` lit le verdict
  métacognitif du *pipeline*, `pipeline_raisonnement["metacognition"]`, pas
  celui-ci.)
- **Mesurer d'abord** combien d'appels par jour il représente (et leur part
  du quota Gemini de 20 requêtes/jour) avant de décider quoi que ce soit.
- Mesuré le 05/10 : ≈ 565 appels/jour, tous en échec hors de la fenêtre de
  08h00. **Désactivé par défaut depuis Q1** (`METACOG_AUDIT_ENABLED=false`).

## 7. `POST` et `PUT /api/plans` ne sont pas plafonnés

- E4 plafonne uniquement le mode plan du chat (`agents/chat/plan_builder.py`,
  règle dans `agents/chat/_plan_budget.py`).
- `POST /api/plans` (création) et `PUT /api/plans/<id>` (`modifier_plan` :
  budget en €, pourcentage, statut…) n'appliquent aucun plafond. Aucune
  interface ne s'en sert pour le budget aujourd'hui (le formulaire d'édition
  de la page Plans ne touche ni budget, ni pourcentage, ni statut), mais ils
  sont joignables sans authentification depuis le tailnet.

## 8. JUSTESSE — P&L latent inconnu présenté comme 0 au LLM du chat

- Le chat construit son contexte avec `etat_portefeuille(with_live_prices=False)`
  (`agents/chat/context_builder.py`) : aucune position n'a de prix, donc
  `prix_actuel` et `unrealized_pnl_euros` valent `null` pour toutes.
- `agents/paper_trader/portfolio.py:95` fait
  `sum(p.get("unrealized_pnl_euros") or 0 …)` : l'inconnu devient **0**, et
  `total_value` = capital + 0.
- Le prompt annonce alors « P&L latent : +0.00€ » (constaté dans
  `message_audit` n°13, 03/10 : 11 positions, 11 `prix_actuel` à null) : un
  chiffre inconnu est présenté comme un zéro factuel.

## 9. Conseils réels tronqués, stockés tels quels

- `agents/real_advisor.py::_enrichir_llm` remplace la justification d'un
  conseil par le texte du LLM, appelé avec `max_tokens=200`
  (`real_advisor.py:76-80`), sans vérifier que la phrase est complète.
- Exemples dans `real_advice_log` (03/10 vers 07h05) : n°2518 « VRT est en
  ligne avec », n°2515 « Maintenez la position MU, ». Ces textes sont
  affichés tels quels dans « Conseils en attente » (page Réel).

## 10. Anciens skills : code mort, à supprimer (commit de nettoyage séparé)

- `agents/skills/pipeline.py` n'est importé par aucun module (remplacé par
  `pipeline_grouped.py`). Il est le seul à importer `bayesien.py`,
  `base_rates.py`, `metacognition.py`, `pre_mortem.py` et `second_ordre.py`,
  qui appellent `ask_gemini` en direct, hors de la réserve Gemini (Q4).
- Relevé le 06/10/2026 pendant Q4 : 0 appel en production. Ne pas les
  rebrancher tels quels ; vérifier les imports avant suppression.
- Le Sentiment Analyst (`sentiment_analyst/_llm.py`) garde lui aussi
  `ask_gemini` en direct : laissé volontairement, il n'est appelé que par
  le bloc `__main__` d'`analyst.py` (lancement manuel).
