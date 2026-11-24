"""
tests/pro_page_fixtures.py — Client Flask du dashboard branché sur un grand livre et une base
de l'agent temporaires, pour les tests des pages /pro et /pro/trades.

Les chemins du dashboard professionnel sont remplacés le temps du test : rien n'est lu ni écrit
dans data/. Le jour de lecture est figé (AUJOURD_HUI). Données inventées, aucun réseau.
"""

import html as html_std
import os
import re
from unittest import mock

for _cle in ("EMAIL_SENDER", "EMAIL_APP_PASSWORD", "EMAIL_RECIPIENT"):
    os.environ.setdefault(_cle, "test")  # config.py exige ces variables (pas de .env)

from dashboard.app import app
from dashboard.pro import comptes, routes
from tests.pro_fixtures import AUJOURD_HUI, BasePro
from utils import database

EN_TETE = {"X-AlphaSignal": "1"}


def texte_de(html: str) -> str:
    """Texte visible d'un morceau de HTML : balises retirées, entités décodées, blancs réduits
    (l'espace insécable des montants est gardé)."""
    sans_balises = html_std.unescape(re.sub(r"<[^>]+>", " ", html))
    return re.sub(r"[ \t\r\n]+", " ", sans_balises).strip()


class BasePage(BasePro):
    """BasePro, plus un client Flask qui lit le grand livre et la base du test."""

    def setUp(self):
        super().setUp()
        for cible, nom, valeur in ((comptes, "LEDGER", self.chemin_ledger), (database, "DB_PATH", self.base),
                                   (routes, "aujourd_hui", lambda: AUJOURD_HUI)):
            correctif = mock.patch.object(cible, nom, valeur)
            correctif.start()
            self.addCleanup(correctif.stop)
        self.client = app.test_client()

    def sans_grand_livre(self):
        """Pointe le dashboard vers un grand livre qui n'existe pas."""
        absent = os.path.join(self.dossier.name, "absent", "ledger.db")
        correctif = mock.patch.object(comptes, "LEDGER", absent)
        correctif.start()
        self.addCleanup(correctif.stop)
        return absent

    def page(self, url: str) -> str:
        reponse = self.client.get(url)
        self.assertEqual(reponse.status_code, 200, url)
        return reponse.get_data(as_text=True)

    def section(self, html: str, identifiant: str) -> str:
        """Texte de la section qui porte cet id."""
        debut = html.index(">", html.index(f'id="{identifiant}"')) + 1
        return texte_de(html[debut:html.index("</section>", debut)])
