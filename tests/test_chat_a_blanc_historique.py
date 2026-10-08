"""
tests/test_chat_a_blanc_historique.py — Fidélité du mode à blanc avec la mémoire des échanges :
CHAT_HISTORIQUE=1 et un historique simulé donnent le même prompt que le vrai chat qui lit les
mêmes échanges dans chat_history ; forcé à 0, l'historique est ignoré des deux côtés.

Lancement : .venv\\Scripts\\python.exe -m unittest tests.test_chat_a_blanc_historique -v
Bases et dossiers temporaires, réseau coupé, échanges inventés.
"""

import os
import sqlite3
import sys
import unittest
from datetime import datetime, timedelta, timezone
from unittest import mock

RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, RACINE)

from tests.test_chat_a_blanc import BaseFidelite  # base hors ligne, sans test propre
from scripts import _chat_a_blanc as ab
import config
from agents.chat import _historique

FIGE = datetime(2026, 11, 2, 15, 0, tzinfo=timezone.utc)
HISTO = [{"role": "user", "texte": "Que penses-tu de NVDA ?", "il_y_a_min": 5},
         {"role": "assistant", "texte": "NVDA : HOLD, score +0.37 (valeur inventée).", "il_y_a_min": 5}]


class TestFideliteHistorique(BaseFidelite):

    def setUp(self):
        super().setUp()
        from agents.chat.chat_engine import initialiser_chat_db
        initialiser_chat_db()
        conn = sqlite3.connect(self.base)  # côté chat : les mêmes échanges dans chat_history
        conn.executemany("INSERT INTO chat_history (role, message, context_used, timestamp) VALUES (?, ?, ?, ?)",
                         [(m["role"], m["texte"], "groq" if m["role"] == "assistant" else None,
                           (FIGE - timedelta(minutes=m["il_y_a_min"])).strftime("%Y-%m-%d %H:%M:%S"))
                          for m in HISTO])
        conn.commit()
        conn.close()
        fige = mock.patch.object(_historique, "_maintenant", return_value=FIGE)
        fige.start()
        self.patchs.append(fige)

    def test_meme_prompt_avec_historique_simule(self):
        cas = ab.construire_cas("Et lui ?", self.cas, historique_simule=HISTO, chat_historique=True)
        with mock.patch.object(config, "CHAT_HISTORIQUE", True):
            chat = self._prompt_du_chat("Et lui ?")
        self.assertEqual((cas["system"], cas["prompt"]), (chat["system"], chat["prompt"]))
        for attendu in (_historique.TITRE_BLOC, "Tickers repris du message précédent : NVDA",
                        "== ANALYSE ACTIFS ==", "[il y a 5 min] Utilisateur :"):
            self.assertIn(attendu, cas["prompt"])
        self.assertEqual((cas["tickers_herites"], cas["messages_historique"], cas["sources_coupees"]),
                         (True, 2, ["alpha_vantage"]))
        self.assertEqual(self.tmp(), [])

    def test_interrupteur_force_a_zero_ignore_l_historique(self):
        cas = ab.construire_cas("Et lui ?", self.cas, historique_simule=HISTO, chat_historique=False)
        with mock.patch.object(config, "CHAT_HISTORIQUE", False):
            chat = self._prompt_du_chat("Et lui ?")
        self.assertEqual(cas["prompt"], chat["prompt"])
        self.assertNotIn(_historique.TITRE_BLOC, cas["prompt"])
        self.assertEqual((cas["tickers_herites"], cas["messages_historique"]), (False, 0))


if __name__ == "__main__":
    unittest.main()
