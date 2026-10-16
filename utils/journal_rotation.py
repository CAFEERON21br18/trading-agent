"""
utils/journal_rotation.py — Rotation des fichiers de log sans « Logging error » (TODO §1).

Sous Windows, un fichier ouvert par un autre processus ne peut pas être renommé (WinError 32).
RotatingFileHandler décale d'abord les sauvegardes, puis renomme le fichier courant : quand ce
renommage échoue, une sauvegarde est perdue à chaque essai, la ligne n'est pas écrite et une trace
« --- Logging error --- » part sur stderr, ligne après ligne.

RotationTolerante renomme le fichier courant en premier (vers <fichier>.rotation). S'il est ouvert
ailleurs, rien n'est déplacé : la ligne est écrite dans le fichier courant et la rotation est
retentée après REESSAI_S secondes. Une rotation interrompue plus loin (sauvegarde ouverte par un
lecteur) est terminée au prochain essai. utils/logger.py donne un fichier par tâche : ce cas ne
se produit que si la même tâche tourne deux fois à la fois ou si un programme garde le fichier
ouvert (éditeur, Get-Content -Wait).
"""

import os
import time
from logging.handlers import RotatingFileHandler

REESSAI_S = 60


class RotationTolerante(RotatingFileHandler):
    """RotatingFileHandler dont la rotation ne lève jamais d'erreur et ne perd aucune sauvegarde."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.attente = self.baseFilename + ".rotation"
        self.prochain_essai = 0.0  # time.monotonic() ; 0 = pas d'échec en cours
        self.echecs = 0

    def shouldRollover(self, record) -> bool:
        if time.monotonic() < self.prochain_essai:
            return False
        return bool(super().shouldRollover(record))

    def doRollover(self) -> None:
        if self.stream:
            self.stream.close()
            self.stream = None
        if self.backupCount > 0:
            try:
                if not os.path.exists(self.attente):  # sinon : terminer d'abord la rotation précédente
                    os.replace(self.baseFilename, self.attente)
                for i in range(self.backupCount - 1, 0, -1):
                    ancien = f"{self.baseFilename}.{i}"
                    if os.path.exists(ancien):
                        os.replace(ancien, f"{self.baseFilename}.{i + 1}")
                os.replace(self.attente, f"{self.baseFilename}.1")
                self.prochain_essai = 0.0
            except OSError:  # PermissionError (WinError 32) : fichier ouvert par un autre processus
                self.echecs += 1
                self.prochain_essai = time.monotonic() + REESSAI_S
        self.stream = self._open()
