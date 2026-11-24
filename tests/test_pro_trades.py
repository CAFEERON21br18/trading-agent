"""
tests/test_pro_trades.py — Page « Mes trades » du dashboard professionnel (GET /pro/trades).

1. sans grand livre ou sans trade : la page l'explique et propose l'import ;
2. positions ouvertes du compte réel : dernier prix, résultat latent, frais payés à l'achat et
   leur part ; position sans prix : « prix indisponible », jamais 0 ;
3. trades clos : résultat brut, frais, résultat net ; frais ordre par ordre, « frais non
   détectés » sinon ; mouvements : dépôts, retraits, dividendes ;
4. le compte paper n'y figure pas ; bascule EUR / USD ; lecture seule ;
5. le script de la page, exécuté par Node (sauté sans Node) : tout texte venu du fichier est
   échappé ; l'aperçu puis la confirmation appellent les deux routes POST avec le jeton.

Lancement : .venv\\Scripts\\python.exe -m unittest tests.test_pro_trades -v
Client de test Flask, bases temporaires, données inventées ; aucun réseau, rien dans data/.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

from tests.journaux_isoles import isoler_journaux
isoler_journaux()  # avant tout import du code testé : rien dans logs/ (production)

from dashboard.pro import formats
from tests.pro_fixtures import empreinte
from tests.pro_page_fixtures import EN_TETE, BasePage, texte_de

E = formats.ESPACE


class TestPage(BasePage):
    def lignes(self, html: str, section: str) -> list[str]:
        debut = html.index(f'id="{section}"')
        return [texte_de(l) for l in re.findall(r"<tr class=.*?</tr>", html[debut:html.index("</section>", debut)], re.S)]

    def test_sans_grand_livre_ou_sans_trade(self):
        html = self.page("/pro/trades")  # grand livre présent, compte réel absent
        self.assertIn("Aucun trade dans le compte réel. Importez un relevé CSV Revolut", texte_de(html))
        self.assertIn('id="import-fichier"', html)
        self.assertNotIn('id="positions"', html)
        absent = self.sans_grand_livre()
        self.assertIn("Le grand livre n'existe pas encore", texte_de(self.page("/pro/trades")))
        self.assertFalse(os.path.exists(os.path.dirname(absent)))

    def test_compte_reel_en_detail(self):
        self.compte_reel()
        self.compte_paper()
        self.taux()
        html = self.page("/pro/trades")
        self.assertEqual(self.lignes(html, "positions"), [
            f"CCC long 2 200,00{E}$ · 04/11/2026 210,00{E}$ · cours du 09/11/2026 (base de l'agent) +16,00{E}€ "
            f"2,00{E}$ · 0,50{E}% du montant",
            f"DDD.PA long 5 20,00{E}€ · 05/11/2026 prix indisponible — frais non détectés",
            "Total du résultat latent — 1 position sur 2 avec un prix · cours du 09/11/2026 ; "
            f"1 position en « prix indisponible », hors du total +16,00{E}€"])
        self.assertEqual(self.lignes(html, "trades-clos"), [
            f"BBB long 4 03/11/2026 · 50,00{E}$ 06/11/2026 · 45,00{E}$ −16,00{E}€ 0,40{E}€ −16,40{E}€",
            f"AAA long 10 02/11/2026 · 100,00{E}$ 05/11/2026 · 110,00{E}$ +80,00{E}€ 1,60{E}€ +78,40{E}€"])
        ordres = self.lignes(html, "frais")
        self.assertEqual(len(ordres), 6)
        self.assertEqual(ordres[-1], f"02/11/2026 AAA achat 10 100,00{E}$ 1{E}000,00{E}$ 1,00{E}$ · 0,10{E}% du montant")
        self.assertIn(f"06/11/2026 BBB vente 4 45,00{E}$ 180,00{E}$ frais non détectés", ordres)
        self.assertEqual(self.lignes(html, "mouvements"), [
            f"07/11/2026 Retrait — −100,00{E}€", f"06/11/2026 Dividende AAA +1,50{E}$",
            f"01/11/2026 Dépôt — +1{E}000,00{E}€"])
        for paper in ("EEE", "FFF", "GGG", "Paper (agent)"):
            self.assertNotIn(paper, html)  # le compte paper n'est pas sur cette page

    def test_cours_du_grand_livre_et_sa_date(self):
        from datetime import date
        self.compte_reel()
        self.taux()
        self.cours_livre("CCC", "212")
        self.cours_livre("DDD.PA", "21", jour=date(2026, 11, 6), devise="EUR")
        positions = self.lignes(self.page("/pro/trades"), "positions")
        self.assertIn(f"212,00{E}$ · cours du 09/11/2026 (grand livre) +19,20{E}€", positions[0])
        self.assertIn(f"21,00{E}€ · cours du 06/11/2026 (grand livre) +5,00{E}€", positions[1])
        self.assertIn(f"2 positions sur 2 avec un prix · cours du 06/11/2026 au 09/11/2026 +24,20{E}€", positions[2])

    def test_bascule_de_devise_et_lecture_seule(self):
        self.compte_reel()
        self.taux()
        avant = empreinte(self.chemin_ledger), empreinte(self.base)
        html = self.page("/pro/trades?devise=USD")
        self.assertIn(f"+98,00{E}$", self.lignes(html, "trades-clos")[1])
        self.assertIn(f"+20,00{E}$", self.lignes(html, "positions")[0])
        self.assertIn('href="/pro/trades?devise=USD" aria-current="true"', html)
        self.assertIn('href="/pro?devise=USD"', html)
        self.assertIn('href="/pro/trades?devise=EUR"', self.page("/pro"))
        self.assertEqual((empreinte(self.chemin_ledger), empreinte(self.base)), avant)
        self.assertEqual(self.client.post("/pro/trades", headers=EN_TETE).status_code, 405)

    def test_sans_taux_les_lignes_le_disent(self):
        self.compte_reel()
        html = self.page("/pro/trades")
        self.assertIn("taux indisponible", self.lignes(html, "trades-clos")[0])
        self.assertIn("taux indisponible", self.lignes(html, "positions")[0])
        self.assertIsNone(re.search(r"(?<!\d)0,00", " ".join(self.lignes(html, "trades-clos"))))


HARNAIS = """
const elements = {}, appels = [];
globalThis.document = {getElementById: (id) => elements[id] || (elements[id] = {
  innerHTML: "", hidden: true, files: [],
  set textContent(t) { this.innerHTML = "[texte]" + t; },
  insertAdjacentHTML(_, h) { this.innerHTML += h; }})};
globalThis.fetch = async (url, options) => {
  appels.push([url, options.method, options.headers["Content-Type"], typeof options.body === "string" ? options.body : "fichier"]);
  const reponse = url.endsWith("apercu") ? APERCU : Object.assign({ecrit: true}, APERCU, {jeton: undefined});
  return {ok: true, json: async () => reponse};
};
const APERCU = {trades_a_ajouter: 1, trades_deja_presents: 0, mouvements_a_ajouter: 0, mouvements_deja_presents: 0,
  ignores: {"<img src=x onerror=alert(1)>": 2}, erreurs: [], jeton: "jeton-de-test"};
ESC_HTML
SCRIPT
(async () => {
  afficherResume(Object.assign({}, APERCU, {erreurs: [[3, "date illisible : '<script>alert(1)</script>'"]]}), "Aperçu <b>", false);
  const piege = elements["import-apercu"].innerHTML;
  document.getElementById("import-fichier").files = [{size: 10}];
  await apercuReleve();
  const visible = !elements["import-confirmer"].hidden;
  await confirmerImport();
  await confirmerImport();
  console.log(JSON.stringify({piege, visible, appels, fin: elements["import-apercu"].innerHTML}));
})();
"""


@unittest.skipUnless(shutil.which("node"), "Node absent")
class TestScriptDeLaPage(BasePage):
    def test_texte_du_fichier_echappe_et_deux_temps(self):
        html = self.page("/pro/trades")
        esc = re.search(r"function escHtml\(s\) \{.*?\n      \}", html, re.S).group(0)
        script = [s for s in re.findall(r"<script>(.*?)</script>", html, re.S) if "apercuReleve" in s]
        self.assertEqual(len(script), 1)
        self.assertEqual(re.findall(r"\$\{(?!escHtml\()", script[0]), [])  # toute insertion passe par escHtml
        with tempfile.TemporaryDirectory() as d:
            chemin = os.path.join(d, "harnais.js")
            with open(chemin, "w", encoding="utf-8") as f:
                f.write(HARNAIS.replace("ESC_HTML", esc).replace("SCRIPT", script[0]))
            sortie = subprocess.run(["node", chemin], capture_output=True, text=True, encoding="utf-8", timeout=60)
        self.assertEqual(sortie.returncode, 0, sortie.stderr)
        vu = json.loads(sortie.stdout)
        for interdit in ("<img", "<script", "<b>"):
            self.assertNotIn(interdit, vu["piege"])
        self.assertIn("&lt;img src=x onerror=alert(1)&gt;", vu["piege"])
        self.assertIn("ligne 3 : date illisible", vu["piege"])
        self.assertTrue(vu["visible"])  # aperçu sans erreur, jeton reçu : la confirmation est proposée
        self.assertEqual(vu["appels"], [
            ["/pro/import/apercu", "POST", "text/csv", "fichier"],
            ["/pro/import/confirmer", "POST", "application/json", '{"jeton":"jeton-de-test"}']])  # une seule fois
        self.assertIn("Import terminé", vu["fin"])


if __name__ == "__main__":
    unittest.main()
