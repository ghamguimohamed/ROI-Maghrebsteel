"""Génère le logo combiné UM6P | EMINES sur fond blanc.

Reproduction vectorielle (matplotlib) de la charte des deux établissements,
exportée en PNG haute résolution pour réutilisation dans l'app Streamlit et
le classeur Excel. Lancer une fois :  python assets/make_logo.py
"""

from __future__ import annotations

import os

import matplotlib

matplotlib.use("Agg")
import matplotlib.font_manager as fm  # noqa: E402
import matplotlib.pyplot as plt  # noqa: E402
from matplotlib.patches import FancyBboxPatch  # noqa: E402

ORANGE = "#E8512E"
NAVY = "#163A6B"
GRIS = "#3F3F41"

ICI = os.path.dirname(os.path.abspath(__file__))
SORTIE = os.path.join(ICI, "logo_emines.png")

# Police grasse disponible
_BOLD = fm.FontProperties(weight="bold")
_HEAVY = fm.FontProperties(weight="bold", stretch="condensed")


def construire():
    # Logo vertical EMINES (tout en bleu marine, fond blanc)
    fig = plt.figure(figsize=(8.4, 9.0), dpi=200)
    fig.patch.set_facecolor("white")
    ax = fig.add_axes([0, 0, 1, 1])
    ax.set_xlim(0, 100)
    ax.set_ylim(0, 108)
    ax.axis("off")
    ax.set_facecolor("white")

    # --- EMINES (grand, gras, marine) -------------------------------------
    ax.text(50, 80, "EMINES", ha="center", va="center",
            color=NAVY, fontsize=82, fontproperties=_HEAVY)

    # --- School of Industrial Management ----------------------------------
    ax.text(50, 62, "School of Industrial Management", ha="center", va="center",
            color=NAVY, fontsize=18, fontproperties=_BOLD)

    # --- Université Mohammed VI Polytechnique (bas, capitales espacées) ----
    ax.text(50, 28, "U N I V E R S I T É   M O H A M M E D   V I",
            ha="center", va="center", color=NAVY, fontsize=13,
            fontproperties=_BOLD)
    ax.text(50, 19, "P O L Y T E C H N I Q U E",
            ha="center", va="center", color=NAVY, fontsize=13,
            fontproperties=_BOLD)

    fig.savefig(SORTIE, dpi=200, facecolor="white", bbox_inches="tight",
                pad_inches=0.2)
    plt.close(fig)
    print("Logo généré :", SORTIE)


if __name__ == "__main__":
    construire()
