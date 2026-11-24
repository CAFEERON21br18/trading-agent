"""Import du relevé CSV Revolut vers le grand livre.

FORMAT GÉNÉRIQUE, à ajuster sur les en-têtes du vrai relevé : il suffit de
changer COLONNES. L'import est tout ou rien : une ligne illisible et rien
n'est écrit. Réimporter le même fichier n'ajoute aucun doublon.
"""
import csv
import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

from ledger import ecriture

SOURCE = "revolut_csv"
COLONNES = {
    "date": "Date", "symbole": "Ticker", "type": "Type",
    "quantite": "Quantity", "prix": "Price per share",
    "total": "Total Amount", "devise": "Currency", "taux": "FX Rate",
}
SYMBOLES = {"$": "USD", "€": "EUR", "£": "GBP"}
FORMATS_DATE = ("%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M", "%d/%m/%Y", "%Y-%m-%d %H:%M:%S")
TOLERANCE_FRAIS = Decimal("0.01")


@dataclass(frozen=True)
class LigneTrade:
    numero: int
    horodatage: datetime
    symbole: str
    sens: str
    quantite: Decimal
    prix: Decimal
    devise: str
    frais: Decimal
    taux: Decimal | None
    ref_source: str


@dataclass
class Rapport:
    importes: int = 0
    deja_presents: int = 0
    ignores: dict[str, int] = field(default_factory=dict)
    erreurs: list[tuple[int, str]] = field(default_factory=list)


def nombre(texte: str) -> Decimal:
    """Lit un montant comme 'USD 1,234.56', '$12.30' ou '12,30'."""
    brut = re.sub(r"[^\d,.\-]", "", texte or "")
    if "," in brut and "." in brut:
        brut = brut.replace(",", "")
    elif "," in brut:
        if re.fullmatch(r"-?\d{1,3}(,\d{3})+", brut):
            raise ValueError(f"montant ambigu (milliers ou décimales ?) : {texte!r}")
        brut = brut.replace(",", ".")
    try:
        return Decimal(brut)
    except InvalidOperation as exc:
        raise ValueError(f"montant illisible : {texte!r}") from exc


def _date(texte: str) -> datetime:
    texte = (texte or "").strip()
    try:
        d = datetime.fromisoformat(texte)
    except ValueError:
        for fmt in FORMATS_DATE:
            try:
                d = datetime.strptime(texte, fmt)
                break
            except ValueError:
                continue
        else:
            raise ValueError(f"date illisible : {texte!r}") from None
    return d if d.tzinfo else d.replace(tzinfo=timezone.utc)


def _devise(ligne: dict, colonnes: dict) -> str:
    devise = (ligne.get(colonnes["devise"]) or "").strip().upper()
    if not devise:
        prix = ligne.get(colonnes["prix"]) or ""
        code = re.search(r"[A-Z]{3}", prix)
        devise = code.group() if code else next(
            (v for s, v in SYMBOLES.items() if s in prix), "")
    if len(devise) != 3:
        raise ValueError("devise absente")
    return devise


def lire(flux, colonnes: dict = COLONNES) -> tuple[list[LigneTrade], Rapport]:
    """Lit le CSV sans rien écrire. Renvoie les trades et le rapport de lecture."""
    rapport = Rapport()
    lecteur = csv.DictReader(flux)
    manquantes = [c for cle, c in colonnes.items()
                  if cle not in ("total", "taux", "devise")
                  and c not in (lecteur.fieldnames or [])]
    if manquantes:
        rapport.erreurs.append((1, f"colonnes absentes : {manquantes}"))
        return [], rapport
    trades, vus = [], {}
    for numero, ligne in enumerate(lecteur, start=2):
        type_ = (ligne.get(colonnes["type"]) or "").strip().upper()
        sens = "achat" if "BUY" in type_ else "vente" if "SELL" in type_ else None
        if sens is None:
            rapport.ignores[type_ or "(vide)"] = rapport.ignores.get(type_ or "(vide)", 0) + 1
            continue
        try:
            trades.append(_trade(numero, ligne, sens, colonnes, vus))
        except ValueError as exc:
            rapport.erreurs.append((numero, str(exc)))
    return trades, rapport


def _trade(numero, ligne, sens, colonnes, vus) -> LigneTrade:
    quantite = nombre(ligne[colonnes["quantite"]])
    prix = nombre(ligne[colonnes["prix"]])
    if quantite <= 0 or prix <= 0:
        raise ValueError("quantité et prix doivent être positifs")
    symbole = (ligne[colonnes["symbole"]] or "").strip().upper()
    if not symbole:
        raise ValueError("symbole absent")
    frais = Decimal("0")
    total_txt = (ligne.get(colonnes["total"]) or "").strip()
    if total_txt:
        total, notionnel = abs(nombre(total_txt)), quantite * prix
        ecart = total - notionnel if sens == "achat" else notionnel - total
        if ecart > TOLERANCE_FRAIS:
            frais = ecart
    taux_txt = (ligne.get(colonnes["taux"]) or "").strip()
    taux = nombre(taux_txt) if taux_txt else None
    cle = "|".join((ligne.get(c) or "").strip() for c in colonnes.values())
    empreinte = hashlib.sha256(cle.encode()).hexdigest()[:16]
    vus[empreinte] = vus.get(empreinte, 0) + 1
    return LigneTrade(
        numero=numero, horodatage=_date(ligne[colonnes["date"]]), symbole=symbole,
        sens=sens, quantite=quantite, prix=prix, devise=_devise(ligne, colonnes),
        frais=frais, taux=taux if taux and taux > 0 else None,
        ref_source=f"{empreinte}-{vus[empreinte]}")


def importer(conn, chemin: str, compte_nom: str = "Revolut",
             devise_compte: str = "EUR", colonnes: dict = COLONNES) -> Rapport:
    """Importe le relevé dans le grand livre. Rien n'est écrit s'il y a une erreur."""
    with open(chemin, newline="", encoding="utf-8-sig") as flux:
        trades, rapport = lire(flux, colonnes)
    if rapport.erreurs:
        return rapport
    try:
        compte_id = ecriture.compte(conn, compte_nom, "reel", devise_compte)
        for t in trades:
            instrument_id = ecriture.instrument(conn, t.symbole, t.devise)
            cree = ecriture.enregistrer_trade(
                conn, compte_id=compte_id, instrument_id=instrument_id,
                horodatage=t.horodatage, sens=t.sens, quantite=t.quantite,
                prix=t.prix, devise=t.devise, source=SOURCE,
                ref_source=t.ref_source, taux_change=t.taux,
                couts=[("commission", t.frais)] if t.frais > 0 else ())
            if cree is None:
                rapport.deja_presents += 1
            else:
                rapport.importes += 1
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    return rapport
