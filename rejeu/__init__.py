"""
rejeu/ — Rejeu sur plusieurs années du cœur technique de l'agent (registre §10).

Le rejeu APPELLE les vraies fonctions de l'agent (score technique, moteur de décision, risque,
taille de position, règles du paper trader) sur des barres quotidiennes historiques, et mesure le
résultat avec des frais. Il ne réécrit pas ces règles et ne modifie aucun fichier de l'agent :
ce qui ne peut pas tourner hors production (réseau, base, heure courante, e-mails) est enveloppé
d'ici (rejeu/enveloppe.py).

Sens unique : aucun module de agents/, utils/, alerts/, config.py ni des cycles n'importe ce
paquet (tests/test_rejeu_isolement.py). Aucune décision de l'agent en production ne change.
Rien n'est écrit dans data/database.db, data/registre.db ni data/ledger.db : le rejeu n'écrit que
dans data/rejeu/ (hors git) et reports/rejeu/ (hors git). Ni Jev ni aucun LLM n'est appelé.
Tous les paramètres sont dans rejeu/parametres.py, figés avant le premier lancement.
"""
