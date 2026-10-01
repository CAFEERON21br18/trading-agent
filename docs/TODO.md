# TODO — hors périmètre

Points relevés pendant la Phase 4 (audit du chat stratégique, 01/10/2026).
Non traités : chacun fera l'objet d'un travail séparé.

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
