"""
agents/chat/_historique.py — Mémoire des derniers échanges du chat (désactivée par défaut).

Appelé par context_builder seulement si config.CHAT_HISTORIQUE vaut 1 (défaut 0) :
- chat_history est lu en lecture seule : les 3 derniers échanges (question et
  réponse) de moins de CHAT_HISTORIQUE_MAX_MIN minutes (120 par défaut) ;
- message coupé à 600 caractères, bloc à 2 500 (les échanges les plus anciens
  sont retirés d'abord) ;
- la question courante n'est jamais réinjectée : une question sans réponse est
  ignorée, et le dernier échange l'est aussi si sa question est identique ;
- une réponse en échec du LLM (context_used « llm_indispo:… ») est remplacée
  par « (réponse indisponible : service IA en échec) ».

Le bloc « == ÉCHANGES PRÉCÉDENTS … == », placé juste avant la question, est exclu
des références par _verif_chiffres.references_du_prompt : ce n'est jamais une
source de chiffres. Chaque ligne y est indentée : aucune ne commence par « == »,
l'exclusion s'étend donc toujours jusqu'à « == QUESTION DE L'UTILISATEUR == ».
Sélection et rendu sont purs (ni config ni base) ; seuls lire() et
lignes_chat_history() touchent config et la base (lecture seule).
"""

from datetime import datetime, timedelta, timezone

NB_ECHANGES = 3
MAX_MESSAGE, MAX_BLOC = 600, 2500
MAX_QUESTION_REPRISE = 80   # reprise des tickers : questions courtes seulement
MAX_TICKERS_REPRIS = 3
LIMITE_LIGNES = 40          # lignes de chat_history lues (largement plus que 3 échanges)
REPONSE_EN_ECHEC = "(réponse indisponible : service IA en échec)"
TITRE_BLOC = ("== ÉCHANGES PRÉCÉDENTS (contexte de conversation — "
              "ce n'est PAS une source de chiffres) ==")
ROLES = {"user": "Utilisateur", "assistant": "AlphaSignal"}


def _maintenant() -> datetime:
    return datetime.now(timezone.utc)


def _horodatage(ts) -> datetime | None:
    """timestamp de chat_history : CURRENT_TIMESTAMP de SQLite, en UTC, « AAAA-MM-JJ HH:MM:SS »."""
    try:
        d = datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        return d if d.tzinfo else d.replace(tzinfo=timezone.utc)
    except (TypeError, ValueError):
        return None


def _couper(texte, n: int) -> str:
    texte = str(texte or "").strip()
    return texte if len(texte) <= n else texte[:n - 1].rstrip() + "…"


def bloc_prompt(historique: list | None) -> list[str]:
    """Lignes du bloc pour le prompt ; [] sans historique (prompt inchangé)."""
    if not historique:
        return []
    lignes = [TITRE_BLOC]
    for m in historique:
        lignes.append(f"  [il y a {m['il_y_a_min']} min] {ROLES.get(m['role'], m['role'])} :")
        lignes += [f"    {l.strip()}" for l in m["texte"].splitlines() if l.strip()] or ["    (vide)"]
    return lignes + [""]


def ligne_tickers_herites(contexte: dict) -> list[str]:
    """[« Tickers repris du message précédent : … »] si les tickers ont été repris, sinon []."""
    if not contexte.get("tickers_herites"):
        return []
    return [f"Tickers repris du message précédent : {', '.join(contexte.get('tickers_mentionnes') or [])}"]


def selectionner(lignes: list[dict], question: str, maintenant: datetime, max_min: int) -> list[dict]:
    """lignes : chat_history par id croissant ({role, message, context_used, timestamp}) →
    [{role, texte, il_y_a_min}] des derniers échanges récents, du plus ancien au plus récent."""
    echanges, en_attente = [], None
    for l in lignes:
        if l.get("role") == "user":
            en_attente = l  # une question sans réponse est remplacée par la suivante, jamais reprise
        elif l.get("role") == "assistant" and en_attente is not None:
            echanges.append((en_attente, l))
            en_attente = None
    if echanges and str(echanges[-1][0].get("message") or "").strip() == (question or "").strip():
        echanges.pop()  # la question courante déjà écrite (double envoi) n'est pas réinjectée
    recents = []
    for q, r in echanges:
        quand = _horodatage(q.get("timestamp"))
        if quand is None or maintenant - quand >= timedelta(minutes=max_min):
            continue
        age = max(0, int((maintenant - quand).total_seconds() // 60))
        echec = str(r.get("context_used") or "").startswith("llm_indispo")
        recents.append([{"role": "user", "texte": _couper(q.get("message"), MAX_MESSAGE), "il_y_a_min": age},
                        {"role": "assistant", "il_y_a_min": age,
                         "texte": REPONSE_EN_ECHEC if echec else _couper(r.get("message"), MAX_MESSAGE)}])
    recents = recents[-NB_ECHANGES:]
    while len(recents) > 1 and len("\n".join(bloc_prompt([m for e in recents for m in e]))) > MAX_BLOC:
        recents.pop(0)  # bloc trop long : l'échange le plus ancien part d'abord
    return [m for e in recents for m in e]


def tickers_a_reprendre(question: str, tickers_question: list, historique: list, extraire) -> list[str]:
    """Tickers du dernier message utilisateur (3 au plus) pour une question courte qui n'en cite aucun."""
    if tickers_question or not historique or len((question or "").strip()) >= MAX_QUESTION_REPRISE:
        return []
    dernier = next((m["texte"] for m in reversed(historique) if m["role"] == "user"), "")
    return list(extraire(dernier))[:MAX_TICKERS_REPRIS]


def lignes_chat_history(limite: int = LIMITE_LIGNES) -> list[dict]:
    """Dernières lignes de chat_history (id croissant), base ouverte en lecture seule (mode=ro)."""
    import sqlite3
    from utils import database
    conn = sqlite3.connect(f"file:{database.DB_PATH}?mode=ro", uri=True)
    conn.row_factory = sqlite3.Row
    try:
        rows = conn.execute("SELECT id, role, message, context_used, timestamp FROM chat_history "
                            "ORDER BY id DESC LIMIT ?", (limite,)).fetchall()
        return [dict(r) for r in reversed(rows)]
    finally:
        conn.close()


def lire(question: str) -> list[dict]:
    """Historique sélectionné pour cette question (CHAT_HISTORIQUE_MAX_MIN de config)."""
    import config
    return selectionner(lignes_chat_history(), question, _maintenant(), config.CHAT_HISTORIQUE_MAX_MIN)
