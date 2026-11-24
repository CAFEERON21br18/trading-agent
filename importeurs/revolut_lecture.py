"""Lecture du relevé CSV Revolut, sans rien écrire (l'écriture est dans revolut_csv.py).

FORMAT GÉNÉRIQUE, à ajuster sur les en-têtes du vrai relevé : il suffit de
changer COLONNES. Trois sortes de lignes : les achats et ventes (BUY, SELL), les
mouvements d'argent (MOUVEMENTS, type exact) et le reste, ignoré et compté par type.
"""
import csv
import hashlib
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, InvalidOperation

COLONNES = {
    "date": "Date", "symbole": "Ticker", "type": "Type",
    "quantite": "Quantity", "prix": "Price per share",
    "total": "Total Amount", "devise": "Currency", "taux": "FX Rate",
}
SYMBOLES = {"$": "USD", "€": "EUR", "£": "GBP"}
FORMATS_DATE = ("%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M", "%d/%m/%Y", "%Y-%m-%d %H:%M:%S")
TOLERANCE_FRAIS = Decimal("0.01")
# Type du relevé (exact, sans variante) -> type du mouvement dans le grand livre
MOUVEMENTS = {"DIVIDEND": "dividende", "CASH TOP-UP": "depot", "CASH WITHDRAWAL": "retrait"}


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


@dataclass(frozen=True)
class LigneMouvement:
    numero: int
    horodatage: datetime
    type: str  # depot, retrait ou dividende
    montant: Decimal  # toujours positif
    devise: str
    symbole: str | None  # titre d'un dividende
    ref_source: str


@dataclass
class Rapport:
    importes: int = 0
    deja_presents: int = 0
    ignores: dict[str, int] = field(default_factory=dict)
    erreurs: list[tuple[int, str]] = field(default_factory=list)
    mouvements_importes: int = 0
    mouvements_deja_presents: int = 0


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


def _devise(ligne: dict, colonnes: dict, repli: str = "prix") -> str:
    """Colonne de devise, sinon le code ou le symbole lu dans le montant de repli."""
    devise = (ligne.get(colonnes["devise"]) or "").strip().upper()
    if not devise:
        montant = ligne.get(colonnes[repli]) or ""
        code = re.search(r"[A-Z]{3}", montant)
        devise = code.group() if code else next(
            (v for s, v in SYMBOLES.items() if s in montant), "")
    if len(devise) != 3:
        raise ValueError("devise absente")
    return devise


def _reference(ligne: dict, colonnes: dict, vus: dict) -> str:
    """Empreinte de la ligne, suivie de son rang parmi les lignes identiques du fichier."""
    cle = "|".join((ligne.get(c) or "").strip() for c in colonnes.values())
    empreinte = hashlib.sha256(cle.encode()).hexdigest()[:16]
    vus[empreinte] = vus.get(empreinte, 0) + 1
    return f"{empreinte}-{vus[empreinte]}"


def lire(flux, colonnes: dict = COLONNES) -> tuple[list[LigneTrade], list[LigneMouvement], Rapport]:
    """Lit le CSV sans rien écrire. Renvoie les trades, les mouvements et le rapport de lecture."""
    rapport = Rapport()
    lecteur = csv.DictReader(flux)
    manquantes = [c for cle, c in colonnes.items()
                  if cle not in ("total", "taux", "devise")
                  and c not in (lecteur.fieldnames or [])]
    if manquantes:
        rapport.erreurs.append((1, f"colonnes absentes : {manquantes}"))
        return [], [], rapport
    trades, mouvements, vus = [], [], {}
    for numero, ligne in enumerate(lecteur, start=2):
        type_ = (ligne.get(colonnes["type"]) or "").strip().upper()
        sens = "achat" if "BUY" in type_ else "vente" if "SELL" in type_ else None
        try:
            if sens is not None:
                trades.append(_trade(numero, ligne, sens, colonnes, vus))
            elif type_ in MOUVEMENTS:
                mouvements.append(_mouvement(numero, ligne, MOUVEMENTS[type_], colonnes, vus))
            else:
                rapport.ignores[type_ or "(vide)"] = rapport.ignores.get(type_ or "(vide)", 0) + 1
        except ValueError as exc:
            rapport.erreurs.append((numero, str(exc)))
    return trades, mouvements, rapport


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
    ref_source = _reference(ligne, colonnes, vus)
    return LigneTrade(
        numero=numero, horodatage=_date(ligne[colonnes["date"]]), symbole=symbole,
        sens=sens, quantite=quantite, prix=prix, devise=_devise(ligne, colonnes),
        frais=frais, taux=taux if taux and taux > 0 else None, ref_source=ref_source)


def _mouvement(numero, ligne, type_, colonnes, vus) -> LigneMouvement:
    """Dépôt, retrait ou dividende. Un retrait arrive négatif : sa valeur absolue est gardée."""
    total_txt = (ligne.get(colonnes["total"]) or "").strip()
    if not total_txt:
        raise ValueError(f"montant absent pour un mouvement ({type_})")
    montant = nombre(total_txt)
    if type_ == "retrait":
        montant = abs(montant)
    if montant <= 0:
        raise ValueError(f"montant nul ou négatif pour un mouvement ({type_})")
    symbole = (ligne.get(colonnes["symbole"]) or "").strip().upper()
    ref_source = _reference(ligne, colonnes, vus)
    return LigneMouvement(
        numero=numero, horodatage=_date(ligne[colonnes["date"]]), type=type_,
        montant=montant, devise=_devise(ligne, colonnes, repli="total"),
        symbole=symbole if type_ == "dividende" and symbole else None,
        ref_source=ref_source)
