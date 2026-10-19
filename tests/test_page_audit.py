"""
tests/test_page_audit.py — Phase 4, partie D : page « Audit » du dashboard (consultation de message_audit).

1. GET /audit servi par le dashboard, entrée du menu, script de la page ;
2. lecture seule : aucune route modifiante sous /audit ni /api/audit ; le script ne fait que des GET
   vers /api/audit/* et n'exporte rien (ni téléchargement, ni presse-papiers, ni stockage) ;
3. échappement : le script est exécuté par Node (sauté sans Node) sur un faux DOM, avec des réponses
   d'API piégées (balises dans chaque champ) : aucune balise ne passe telle quelle dans la page.

Lancement : .venv\\Scripts\\python.exe -m unittest tests.test_page_audit -v
Sans base ni réseau : l'API est simulée dans Node.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
import unittest
from unittest import mock

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)
for _cle in ("EMAIL_SENDER", "EMAIL_APP_PASSWORD", "EMAIL_RECIPIENT"):
    os.environ.setdefault(_cle, "test")  # config.py exige ces variables (pas de .env)

from tests.journaux_isoles import isoler_journaux
isoler_journaux()  # avant tout import du code testé : rien dans logs/ (production)

from dashboard.app import app

JS = os.path.join(RACINE, "dashboard", "static", "js", "audit_page.js")
PIEGE = "<img src=x onerror=alert(1)>"

# Faux DOM et fausse API : la liste puis le détail du message n° 1, chaque champ piégé
HARNAIS = r"""
const fs = require("fs");
const PIEGE = %(piege)s;
const sorties = [];
function element(id) {
  return { id, value: "", textContent: "", _html: "", disabled: false, dataset: { id: "1" }, open: false,
    classList: { add() {}, remove() {} }, ecouteurs: {},
    set innerHTML(v) { this._html = v; sorties.push(v); }, get innerHTML() { return this._html; },
    addEventListener(t, f) { this.ecouteurs[t] = f; },
    querySelector() { return zone; }, querySelectorAll() { return id === "aud-liste" ? [item] : []; } };
}
const zone = element("zone"), item = element("item"), elements = {};
global.document = { getElementById: id => (elements[id] = elements[id] || element(id)) };
%(esc)s
global.escHtml = escHtml;
const message = { id: 1, timestamp: "2026-10-19T08:00:00+00:00", source: PIEGE, message_utilisateur: PIEGE,
  llm_utilise: PIEGE, erreur: PIEGE, latence_ms: PIEGE, contournement: true, actions: true,
  fallback: [{ fournisseur: PIEGE, ok: false }], extrait_reponse: PIEGE };
const complet = { ...message, reponse_brute: PIEGE, prompt_envoye: PIEGE, contexte_injecte: { [PIEGE]: PIEGE },
  chaine_de_fallback: [{ etape: "configuration", gemini_modele: PIEGE, gemini_cle: PIEGE },
                       { fournisseur: PIEGE, modele: PIEGE, ok: false, statut: PIEGE, type_erreur: PIEGE, erreur: PIEGE }],
  verification_chiffres: { nb_chiffres: PIEGE, soutenus: PIEGE, non_soutenus: [PIEGE], taux_non_soutenus: 0.5 },
  actions_declenchees: { ecritures: [{ categorie: "persistante", operation: PIEGE, cible: PIEGE }], decider_lances: [PIEGE] },
  decisions_trading_generees: [{ cible: PIEGE }], origine_client: { via: PIEGE },
  passe_par_decision_engine: PIEGE, passe_par_budget_manager: 0 };
const appels = [];
global.fetch = async (url, options) => {
  appels.push({ url, methode: (options && options.method) || "GET" });
  const corps = url.startsWith("/api/audit/stats") ? { total: PIEGE, par_llm: { [PIEGE]: PIEGE }, total_7_jours: 1, conservation_jours: 90 }
    : url.startsWith("/api/audit/messages?") ? { total: 1, page: 1, pages: 1, messages: [message] } : complet;
  return { ok: true, json: async () => corps };
};
eval(fs.readFileSync(%(js)s, "utf8"));
setTimeout(async () => {
  item.open = true; item.ecouteurs.toggle();
  setTimeout(() => {  // les statistiques passent par textContent : jamais interprétées
    console.log(JSON.stringify({ sorties, appels, detail: zone.innerHTML.length,
                                 stats: elements["aud-stats"].textContent.length }));
  }, 50);
}, 50);
"""


def fonction_esc_html() -> str:
    with open(os.path.join(RACINE, "dashboard", "templates", "base.html"), encoding="utf-8") as f:
        base = f.read()
    return re.search(r"function escHtml\(s\) \{.*?\n      \}", base, re.S).group(0)


class TestPage(unittest.TestCase):
    def test_page_et_menu(self):
        client = app.test_client()
        r = client.get("/audit")
        self.assertEqual(r.status_code, 200)
        html = r.get_data(as_text=True)
        self.assertIn("/static/js/audit_page.js", html)
        self.assertIn('href="/audit"', client.get("/architecture").get_data(as_text=True))

    def test_lecture_seule(self):
        for regle in app.url_map.iter_rules():
            if regle.rule.startswith(("/audit", "/api/audit")):
                self.assertLessEqual(regle.methods, {"GET", "HEAD", "OPTIONS"}, regle.rule)
        with open(JS, encoding="utf-8") as f:
            js = f.read()
        self.assertNotIn("method:", js)
        self.assertEqual(set(re.findall(r"lire\(`?\"?(/api/[a-z/]*[a-z])", js)), {"/api/audit/stats", "/api/audit/messages"})
        for interdit in ("download", "Blob", "clipboard", "localStorage", "window.open", "sendBeacon"):
            self.assertNotIn(interdit, js)


class TestApi(unittest.TestCase):
    def test_verification_chiffres_en_objet(self):
        from utils import database, message_audit_db, message_audit_query
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            base = os.path.join(d, "t.db")
            verif = {"version": 1, "nb_chiffres": 3, "soutenus": 2, "non_soutenus": ["7,5"],
                     "petits_entiers": 0, "taux_non_soutenus": 0.3333}
            with mock.patch.object(database, "DB_PATH", base), \
                    mock.patch.object(message_audit_query, "DB_PATH", base):
                rid = message_audit_db.inserer_audit({"timestamp": "2026-10-19T08:00:00+00:00", "source": "pwa",
                                                      "message_utilisateur": "question inventée",
                                                      "verification_chiffres": json.dumps(verif)})
                r = app.test_client().get(f"/api/audit/messages/{rid}")
                vide = message_audit_db.inserer_audit({"timestamp": "2026-10-19T08:01:00+00:00", "source": "pwa"})
                r_vide = app.test_client().get(f"/api/audit/messages/{vide}")
        self.assertEqual(r.status_code, 200)
        self.assertEqual(r.get_json()["verification_chiffres"], verif)  # objet, plus du texte
        self.assertIsNone(r_vide.get_json()["verification_chiffres"])


@unittest.skipUnless(shutil.which("node"), "Node absent")
class TestEchappement(unittest.TestCase):
    def test_aucune_balise_ne_passe(self):
        with tempfile.TemporaryDirectory(ignore_cleanup_errors=True) as d:
            script = os.path.join(d, "harnais.js")
            with open(script, "w", encoding="utf-8") as f:
                f.write(HARNAIS % {"piege": json.dumps(PIEGE), "esc": fonction_esc_html(), "js": json.dumps(JS)})
            r = subprocess.run(["node", script], capture_output=True, text=True, encoding="utf-8", timeout=30)
        self.assertEqual(r.returncode, 0, r.stderr)
        resultat = json.loads(r.stdout.strip().splitlines()[-1])
        self.assertGreater(resultat["detail"], 500)  # le détail a bien été rendu
        for html in resultat["sorties"]:
            self.assertNotIn("<img", html)
        self.assertIn("&lt;img", "".join(resultat["sorties"]))
        self.assertTrue(all(a["methode"] == "GET" and a["url"].startswith("/api/audit/") for a in resultat["appels"]))


if __name__ == "__main__":
    unittest.main()
