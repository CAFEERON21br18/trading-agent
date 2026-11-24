"""
tests/test_pro_vue.py — Page « Vue d'ensemble » du dashboard professionnel (GET /pro).

1. sans grand livre : la page l'explique et ne crée rien ; compte sans trade : dit par panneau ;
2. un panneau par compte avec ses cinq chiffres, le nombre de trades et le badge « non
   décidable · n / 100 » ; « — » pour une mesure non calculable, jamais 0 ;
3. panneau paper : mention « bruts de frais » toujours visible, filtre de période ;
   panneau réel : apports nets et dividendes ;
4. bascule EUR / USD et période retenues dans l'URL ; valeur inconnue : retour au défaut ;
5. une courbe SVG par compte, aucune adresse externe ajoutée par le gabarit ;
6. tableau des derniers trades clos des deux comptes, « — » en R sans stop connu ;
7. taux manquant : « taux indisponible » ; gains et pertes signés, pas la couleur seule ;
8. lecture seule : GET seulement, grand livre et base de l'agent inchangés ; texte échappé ;
   lecture en échec : la page le dit sans chiffre.

Lancement : .venv\\Scripts\\python.exe -m unittest tests.test_pro_vue -v
Client de test Flask, bases temporaires, données inventées ; aucun réseau, rien dans data/.
"""

import os
import re
import sys
import unittest
from unittest import mock

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

from tests.journaux_isoles import isoler_journaux
isoler_journaux()  # avant tout import du code testé : rien dans logs/ (production)

from dashboard.pro import formats, vue_ensemble
from tests.pro_fixtures import empreinte, quand
from tests.pro_page_fixtures import EN_TETE, BasePage, texte_de

E = formats.ESPACE


class TestSansDonnees(BasePage):
    def test_sans_grand_livre_la_page_l_explique(self):
        absent = self.sans_grand_livre()
        html = self.page("/pro")
        self.assertIn("Le grand livre n'existe pas encore", texte_de(html))
        self.assertIn("Aucun trade dans ce compte", self.section(html, "compte-reel"))
        self.assertIn("Il se remplit par le bouton « Synchroniser »", self.section(html, "compte-paper"))
        self.assertIn('href="/pro/trades?devise=EUR#import"', html)  # l'import est proposé
        self.assertIn("Résultats bruts de frais : le paper trader n'en compte aucun",
                      self.section(html, "compte-paper"))  # toujours visible
        self.assertNotIn("<svg", html)
        self.assertFalse(os.path.exists(os.path.dirname(absent)))  # rien n'a été créé

    def test_grand_livre_vide_et_lecture_en_echec(self):
        html = self.page("/pro")  # grand livre présent, aucun compte
        self.assertNotIn("n'existe pas encore", texte_de(html))
        self.assertIn("import du relevé CSV Revolut", self.section(html, "compte-reel"))
        with mock.patch.object(vue_ensemble, "vue", side_effect=RuntimeError("secret")):
            html = self.page("/pro")
        self.assertIn("Le grand livre n'a pas pu être lu", texte_de(html))
        self.assertNotIn("secret", html)
        self.assertNotIn('id="compte-reel"', html)


class TestPanneaux(BasePage):
    def setUp(self):
        super().setUp()
        self.compte_reel()
        self.compte_paper()
        self.taux()

    def test_panneau_reel(self):
        html = self.page("/pro")
        reel = self.section(html, "compte-reel")
        for attendu in (f"Résultat net réalisé +62,00{E}€ 2 trades non décidable · 2 / 100",
                        f"Résultat latent +16,00{E}€ 1 position en « prix indisponible », hors du total "
                        "1 position sur 2 avec un prix",
                        f"Total des frais 3,60{E}€ part du résultat brut : 3,1{E}% (2 trades clos) "
                        "4 ordres avec frais sur 6 non décidable · 2 / 100",
                        "Espérance en R — 0 trade avec stop connu non décidable · 0 / 100",
                        f"Taux de réussite 50,0{E}% 2 trades non décidable · 2 / 100",
                        f"Apports nets +900,00{E}€ 2 mouvements", f"Dividendes +1,20{E}€ 1 mouvement"):
            self.assertIn(attendu, reel)
        self.assertNotIn("bruts de frais", reel)
        self.assertNotIn("Période", reel)

    def test_panneau_paper_et_filtre_de_periode(self):
        paper = self.section(self.page("/pro"), "compte-paper")
        for attendu in ("Résultats bruts de frais : le paper trader n'en compte aucun.",
                        "Période : tout depuis le correctif du prix d'entrée",
                        f"Résultat net réalisé +8,00{E}€ 2 trades non décidable · 2 / 100",
                        f"Résultat latent +7,20{E}€ 1 position sur 1 avec un prix",
                        "Total des frais — part du résultat brut : — aucun frais enregistré sur 5 ordres Espérance",
                        f"Espérance en R +0,75{E}R 2 trades avec stop connu", f"Taux de réussite 50,0{E}% 2 trades"):
            self.assertIn(attendu, paper)
        self.assertNotIn("Apports nets", paper)
        html = self.page("/pro?periode=correctif")
        paper = self.section(html, "compte-paper")
        self.assertIn(f"Résultat net réalisé +16,00{E}€ 1 trade non décidable · 1 / 100", paper)
        self.assertIn(f"Espérance en R +2,00{E}R 1 trade avec stop connu", paper)
        self.assertIn('href="/pro?devise=EUR&amp;periode=correctif" aria-current="true"', html)
        self.assertIn(f"Résultat net réalisé +62,00{E}€ 2 trades", self.section(html, "compte-reel"))  # réel : inchangé
        self.assertNotIn("EEE", html)  # trade ouvert avant le correctif

    def test_bascule_de_devise_retenue_dans_l_url(self):
        html = self.page("/pro?devise=USD&periode=correctif")
        self.assertIn(f"Résultat net réalisé +77,50{E}$", self.section(html, "compte-reel"))
        self.assertIn(f"Apports nets +1{E}125,00{E}$", self.section(html, "compte-reel"))
        self.assertIn('href="/pro?devise=USD&amp;periode=correctif" aria-current="true"', html)
        self.assertIn('href="/pro?devise=EUR&amp;periode=correctif"', html)
        self.assertIn('href="/pro?devise=USD&amp;periode=tout"', html)
        defaut = self.page("/pro?devise=XXX&periode=zzz")
        self.assertIn(f"+62,00{E}€", self.section(defaut, "compte-reel"))
        self.assertIn('href="/pro?devise=EUR&amp;periode=tout" aria-current="true"', defaut)

    def test_une_courbe_par_compte_et_tableau_des_derniers_trades(self):
        html = self.page("/pro")
        self.assertEqual((html.count("<svg "), html.count("<polyline")), (2, 2))
        self.assertIn("Résultat net réalisé cumulé — Réel (Revolut)", html)
        self.assertIn("Résultat net réalisé cumulé — Paper (agent)", html)
        tableau = html[html.index('id="titre-derniers"'):]
        lignes = [texte_de(l) for l in re.findall(r"<tr class=.*?</tr>", tableau, re.S)]
        self.assertEqual(lignes, [
            f"BBB long Réel (Revolut) 03/11/2026 · 50,00{E}$ 06/11/2026 · 45,00{E}$ −16,40{E}€ —",
            f"AAA long Réel (Revolut) 02/11/2026 · 100,00{E}$ 05/11/2026 · 110,00{E}$ +78,40{E}€ —",
            f"FFF long Paper (agent) 25/10/2026 · 100,00{E}$ 28/10/2026 · 120,00{E}$ +16,00{E}€ +2,00{E}R",
            f"EEE long Paper (agent) 01/10/2026 · 100,00{E}$ 05/10/2026 · 95,00{E}$ −8,00{E}€ −0,50{E}R"])

    def test_gains_et_pertes_signes_pas_la_couleur_seule(self):
        html = self.page("/pro")
        html = html[html.index("<main"):html.index("</main>")]
        colores = re.findall(r'class="[^"]*(text-emerald-400|text-red-400)[^"]*">\s*([^<]*)<', html)
        colores = [(c, t.strip()) for c, t in colores]
        self.assertGreaterEqual(len(colores), 8)
        for couleur, texte in colores:
            with self.subTest(texte=texte):
                self.assertTrue(texte.startswith("+" if couleur == "text-emerald-400" else "−"), texte)

    def test_lecture_seule_et_navigation(self):
        avant = empreinte(self.chemin_ledger), empreinte(self.base)
        self.page("/pro")
        self.page("/pro?devise=USD")
        self.assertEqual((empreinte(self.chemin_ledger), empreinte(self.base)), avant)
        self.assertEqual(self.client.post("/pro", headers=EN_TETE).status_code, 405)
        self.assertIn('href="/pro"', self.page("/architecture"))
        with open(os.path.join(RACINE, "dashboard", "templates", "pro_vue.html"), encoding="utf-8") as f:
            gabarit = f.read()
        for interdit in ("://", "<script src", "cdn", "|safe", "<link"):
            self.assertNotIn(interdit, gabarit)  # aucune adresse externe ajoutée par la page


class TestTauxEtEchappement(BasePage):
    def test_taux_indisponible_au_lieu_d_un_chiffre(self):
        self.compte_reel()  # aucun taux enregistré
        html = self.page("/pro")
        reel = self.section(html, "compte-reel")
        for attendu in ("Résultat net réalisé taux indisponible", "Résultat latent taux indisponible",
                        "Total des frais taux indisponible", "Dividendes taux indisponible",
                        f"Apports nets +900,00{E}€"):
            self.assertIn(attendu, reel)
        self.assertIsNone(re.search(r"(?<!\d)0,00", reel))  # aucun zéro à la place d'un chiffre manquant
        self.assertIn("taux indisponible", self.section(html, "courbe-reel"))
        self.assertIn(f"+77,50{E}$", self.section(self.page("/pro?devise=USD"), "compte-reel"))

    def test_texte_venu_du_grand_livre_echappe(self):
        import ledger
        c = ledger.compte(self.conn, "Revolut", "reel", "EUR")
        self.ordre(c, "<b>x&y", "achat", "1", "10", quand(11, 2), devise="EUR")
        self.ordre(c, "<b>x&y", "vente", "1", "12", quand(11, 3), devise="EUR")
        self.conn.commit()
        html = self.page("/pro")
        self.assertIn("&lt;B&gt;X&amp;Y", html)
        self.assertNotIn("<B>X", html)


if __name__ == "__main__":
    unittest.main()
