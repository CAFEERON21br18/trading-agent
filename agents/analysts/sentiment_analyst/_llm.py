"""
agents/analysts/sentiment_analyst/_llm.py — Synthèses naturelles via Gemini.
Transforme les news brutes + le contexte géopolitique chiffré en narratif
exploitable (1 paragraphe court). Fallback gracieux : "" si Gemini KO.
"""

from utils.gemini import ask_gemini, gemini_disponible


SYSTEM_PROMPT_NEWS = """Tu es un analyste sentiment senior pour AlphaSignal.
À partir des titres de news fournis, tu produis une SYNTHÈSE de 2 à 4 phrases EN FRANÇAIS qui :
- Dégage le narratif dominant (haussier / baissier / mixte / brouillé)
- Cite les 1-2 facteurs concrets les plus importants (earnings, rumeur M&A, régulation, etc.)
- Mentionne les risques ou catalyseurs à surveiller dans les jours à venir
- Reste FACTUELLE : pas d'invention, uniquement ce que les titres indiquent

INTERDICTIONS :
- Ne JAMAIS recommander d'acheter ou vendre
- Ne JAMAIS inventer un chiffre absent des titres
- Ne JAMAIS dépasser 4 phrases
"""


SYSTEM_PROMPT_GEO = """Tu es un analyste géopolitique pour AlphaSignal.
À partir des catégories d'événements et titres de news fournis, tu produis un
NARRATIF de 3 à 5 phrases EN FRANÇAIS qui :
- Décrit ce qui se passe au niveau macro (avec noms de pays/régions si pertinent)
- Identifie les secteurs/actifs probablement impactés (positivement ou négativement)
- Cite la nature du choc (escalade, désescalade, incertitude, surprise monétaire)
- Reste FACTUEL : tout vient des titres, rien d'inventé

INTERDICTIONS :
- Ne donne JAMAIS d'ordre d'achat/vente direct
- Ne prédis pas un mouvement de prix précis
- Maximum 5 phrases
"""


SYSTEM_PROMPT_GLOBAL = """Tu es l'analyste sentiment de AlphaSignal.
Tu synthétises l'état global du marché en 4 à 6 phrases EN FRANÇAIS à partir
des chiffres fournis (Fear & Greed, dominance BTC, corrélations, géopolitique).
Tu cherches à :
- Caractériser le régime (risk-on / risk-off / incertain)
- Lier les chiffres entre eux (ex: F&G bas + corrélation BTC/SPY haute = risk-off généralisé)
- Pointer la position contrarian si F&G est à un extrême
- Conclure sur 1-2 angles à surveiller cette semaine

INTERDICTIONS :
- Pas de prévision de prix
- Pas de conseil d'achat/vente direct
- Maximum 6 phrases, style direct
"""


def synthese_news_actif(ticker: str, news_list: list[dict]) -> str:
    """Synthèse en langage naturel des news d'un actif."""
    if not news_list or not gemini_disponible():
        return ""
    titres = "\n".join(
        f"- [{n.get('impact', '?')}] {n.get('titre', '')[:200]}"
        f" ({n.get('source', '')}, {n.get('publie_le', '')[:10]})"
        for n in news_list[:10]
    )
    prompt = (f"Actif : {ticker}\n\n"
              f"Titres de news récents :\n{titres}\n\n"
              f"Donne ta synthèse (2-4 phrases) :")
    return ask_gemini(prompt, system=SYSTEM_PROMPT_NEWS, temperature=0.5,
                      max_output_tokens=400)


def narratif_geopolitique(contexte_geo: dict) -> str:
    """Narratif sur le contexte géopolitique courant."""
    if not contexte_geo or not contexte_geo.get("actif"):
        return ""
    if not gemini_disponible():
        return ""
    cats = contexte_geo.get("categories", {})
    cats_str = ", ".join(f"{c} (×{n})" for c, n in cats.items())
    evts = contexte_geo.get("evenements", [])[:8]
    evts_str = "\n".join(f"- [{e['categorie']}] {e['titre'][:180]}" for e in evts)
    actifs = ", ".join(contexte_geo.get("actifs_a_surveiller", [])[:10])
    prompt = (f"Catégories actives : {cats_str}\n"
              f"Actifs identifiés à surveiller : {actifs}\n\n"
              f"Échantillon de titres :\n{evts_str}\n\n"
              f"Donne le narratif (3-5 phrases) :")
    return ask_gemini(prompt, system=SYSTEM_PROMPT_GEO, temperature=0.5,
                      max_output_tokens=500)


def narratif_global(fg: dict, dominance: float | None,
                     correlations: dict, sentiment: str,
                     contrarian: bool, contexte_geo: dict | None = None) -> str:
    """Narratif global du marché — synthèse des indicateurs sentiment."""
    if not gemini_disponible():
        return ""
    corr_lignes = []
    for paire, val in correlations.items():
        if val is not None:
            corr_lignes.append(f"  {paire} : {val:+.2f}")
    geo_str = ""
    if contexte_geo and contexte_geo.get("actif"):
        cats = contexte_geo.get("categories", {})
        geo_str = "Géopolitique active : " + ", ".join(f"{c}×{n}" for c, n in cats.items())
    prompt = (
        f"Fear & Greed crypto : {fg.get('valeur', 'N/A')} ({fg.get('label', '?')})\n"
        f"Dominance BTC : {dominance:.1f}%\n" if dominance else "Dominance BTC : N/A\n"
    ) + (
        f"Corrélations (60 j) :\n" + "\n".join(corr_lignes) + "\n"
        f"Sentiment évalué : {sentiment}\n"
        f"Signal contrarian détecté : {'oui' if contrarian else 'non'}\n"
        f"{geo_str}\n\n"
        f"Donne le narratif global (4-6 phrases) :"
    )
    return ask_gemini(prompt, system=SYSTEM_PROMPT_GLOBAL, temperature=0.5,
                      max_output_tokens=600)
