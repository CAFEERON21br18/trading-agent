"""
dashboard/pro/ — Dashboard professionnel : pages qui lisent le grand livre (data/ledger.db).

Seul endroit de l'agent autorisé à importer ledger, mesures et importeurs
(tests/test_socle_hors_production.py). Aucun cycle, ni le moteur de décision, ni le paper
trader ne passent par ici : aucune décision ne change.
- donnees.py, latent.py, prix.py : préparation des données, sans Flask ;
- les routes et les gabarits viennent avec les pages (/pro, /pro/trades).
Le portefeuille fantôme Jev n'est ni lu ni affiché.
"""
