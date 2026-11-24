"""
tests/test_pro_synchro_page.py — Bouton « Synchroniser » de la page /pro : son script.

1. le bouton est dans l'en-tête de la page, avec la zone du rapport ;
2. le script, exécuté par Node (sauté sans Node) : un seul POST vers /pro/synchroniser ; le
   rapport des deux synchronisations est affiché, tout texte du serveur échappé ; un refus
   affiche le message tel quel, comme du texte ; le bouton est rendu à la fin.

Lancement : .venv\\Scripts\\python.exe -m unittest tests.test_pro_synchro_page -v
Client de test Flask, bases temporaires ; aucun réseau, rien dans data/.
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

from tests.pro_page_fixtures import BasePage

HARNAIS = """
const elements = {}, appels = [];
globalThis.document = {getElementById: (id) => elements[id] || (elements[id] = {
  innerHTML: "", hidden: true, disabled: false,
  set textContent(t) { this.innerHTML = "[texte]" + t; }})};
const REPONSES = [
  {ok: true, paper: {positions: 2, boucles: 1, importes: 3, deja_presents: 0, annules: 0,
                     devises_incertaines: ["<b>X", "^FCHI"], erreurs: []},
   taux: {ajoutes: 2, deja_presents: 0, ecartes: 0, premier: "2026-11-06", dernier: "2026-11-09"}},
  {ok: false, message: "colonne « boucle » absente <img src=x onerror=alert(1)>"}];
globalThis.fetch = async (url, options) => {
  appels.push([url, options.method, options.body === undefined]);
  return {ok: true, json: async () => REPONSES[appels.length - 1]};
};
ESC_HTML
SCRIPT
(async () => {
  await synchroniser();
  const reussi = elements["synchro-rapport"].innerHTML;
  await synchroniser();
  console.log(JSON.stringify({reussi, refus: elements["synchro-rapport"].innerHTML, appels,
                              bouton: elements["synchro-bouton"].disabled, cache: elements["synchro-rapport"].hidden}));
})();
"""


class TestBouton(BasePage):
    def test_bouton_dans_l_en_tete(self):
        html = self.page("/pro")
        entete = html[html.index("Vue d'ensemble</h2>"):html.index('id="compte-reel"')]
        self.assertIn('id="synchro-bouton" onclick="synchroniser()"', entete)
        self.assertIn('id="synchro-rapport"', entete)
        self.assertNotIn("<form", html)

    @unittest.skipUnless(shutil.which("node"), "Node absent")
    def test_script_un_seul_post_rapport_echappe(self):
        html = self.page("/pro")
        esc = re.search(r"function escHtml\(s\) \{.*?\n      \}", html, re.S).group(0)
        script = [s for s in re.findall(r"<script>(.*?)</script>", html, re.S) if "async function synchroniser" in s]
        self.assertEqual(len(script), 1)
        self.assertEqual(re.findall(r"\$\{(?!escHtml\()", script[0]), [])  # toute insertion passe par escHtml
        with tempfile.TemporaryDirectory() as d:
            chemin = os.path.join(d, "harnais.js")
            with open(chemin, "w", encoding="utf-8") as f:
                f.write(HARNAIS.replace("ESC_HTML", esc).replace("SCRIPT", script[0]))
            sortie = subprocess.run(["node", chemin], capture_output=True, text=True, encoding="utf-8", timeout=60)
        self.assertEqual(sortie.returncode, 0, sortie.stderr)
        vu = json.loads(sortie.stdout)
        self.assertEqual(vu["appels"], [["/pro/synchroniser", "POST", True]] * 2)
        self.assertEqual((vu["bouton"], vu["cache"]), (False, False))
        for attendu in ("Synchronisation appliquée", "Exécutions ajoutées", "Taux EURUSD ajoutés",
                        "2026-11-06 → 2026-11-09", "&lt;b&gt;X, ^FCHI"):
            self.assertIn(attendu, vu["reussi"])
        self.assertNotIn("<b>X", vu["reussi"])
        self.assertTrue(vu["refus"].startswith("[texte]Synchronisation refusée, rien n'a été écrit. colonne « boucle »"))


if __name__ == "__main__":
    unittest.main()
