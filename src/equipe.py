"""Identité du projet : établissement, équipe, libellés.

Centralisé ici pour être réutilisé par l'app Streamlit, l'export Excel et le
générateur de logo. Modifier une seule fois met tout à jour.
"""

from __future__ import annotations

import os

ETABLISSEMENT = "UM6P · EMINES — School of Industrial Management"

TITRE_PROJET = "Simulateur Capacité – Commande"
SOUS_TITRE = "Optimisation de la planification du laminage à froid — Maghreb Steel"

# Membres du groupe (ordre et format NOM Prénom)
EQUIPE = [
    "EL HMID Aicha",
    "GHAMGUI Mohammed Amine",
    "KEITA Josué",
    "LOUTFI Youness",
    "BENYOUSSEF Mouad",
]

# Couleurs de la charte (reprises des logos)
ORANGE = "#E8512E"   # UM6P
NAVY = "#163A6B"     # EMINES
GRIS = "#3F3F41"

# Chemin du logo (généré par assets/make_logo.py)
_RACINE = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
LOGO_PNG = os.path.join(_RACINE, "assets", "logo_emines.png")


def equipe_texte(sep: str = " · ") -> str:
    return sep.join(EQUIPE)
