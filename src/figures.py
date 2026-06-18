"""Génère les 5 figures de la présentation + vérifie les chiffres de référence.

Chaque figure répond à une question du sujet :
  E14  Plan de marche  : tonnage produit par ligne × semaine
  E16  Utilisation des lignes par semaine (%)
  E18  Shadow prices du HRC par grade (MAD/T)
  E19  Marge/T + taux de service par famille
  B8   Courbe d'enveloppe : marge optimale = f(dispo DC01)

Lancement :  python src/figures.py        (écrit les PNG dans outputs/)
"""

from __future__ import annotations

import os
import sys

import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt  # noqa: E402

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

import analyse  # noqa: E402
from model import LIGNES, construire_et_resoudre  # noqa: E402
from parse_data import charger_donnees  # noqa: E402
from sensibilite import b8_tracer  # noqa: E402

NAVY = "#163A6B"
ORANGE = "#E8512E"
GRIS = "#9AA0A6"

ICI = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
OUT = os.path.join(ICI, "outputs")
XLSX = os.path.join(ICI, "data", "Donnees_MaghrebSteel.xlsx")


def _style(ax, titre):
    ax.set_title(titre, color=NAVY, fontsize=13, fontweight="bold", pad=12)
    ax.spines[["top", "right"]].set_visible(False)


# ---------------------------------------------------------------------------
# E16 — Heatmap utilisation des lignes
# ---------------------------------------------------------------------------


def fig_e16(m, chemin):
    df = analyse.utilisation(m).set_index("Ligne")
    cols = [c for c in df.columns if c.startswith("S")]
    data = df[cols].values

    fig, ax = plt.subplots(figsize=(7.2, 5.2))
    fig.patch.set_facecolor("white")
    im = ax.imshow(data, cmap="Blues", vmin=0, vmax=100, aspect="auto")

    ax.set_xticks(range(len(cols)), [c.replace(" (%)", "") for c in cols])
    ax.set_yticks(range(len(df.index)), df.index)
    for i in range(data.shape[0]):
        for j in range(data.shape[1]):
            v = data[i, j]
            ax.text(j, i, f"{v:.0f}", ha="center", va="center",
                    color="white" if v > 55 else NAVY, fontsize=10, fontweight="bold")
    cb = fig.colorbar(im, ax=ax, fraction=0.046, pad=0.04)
    cb.set_label("Taux d'occupation (%)", color=NAVY)
    _style(ax, "E16 — Utilisation des lignes par semaine")
    ax.set_xlabel("Semaine")
    fig.tight_layout()
    fig.savefig(chemin, dpi=130, facecolor="white")
    plt.close(fig)


# ---------------------------------------------------------------------------
# E14 — Plan de marche (tonnage produit par ligne × semaine)
# ---------------------------------------------------------------------------


def fig_e14(m, chemin):
    df = analyse.plan_de_marche(m).set_index("Ligne")
    cols = [c for c in df.columns if c.startswith("S")]
    n = len(LIGNES)
    largeur = 0.2
    fig, ax = plt.subplots(figsize=(9, 5))
    fig.patch.set_facecolor("white")
    couleurs = ["#163A6B", "#3E6BA8", "#7AA0CF", "#Bcd0e8"]
    couleurs = [NAVY, "#3E6BA8", "#7AA0CF", "#C3D4EA"]
    x = range(n)
    for k, c in enumerate(cols):
        vals = [df.loc[lg, c] for lg in LIGNES]
        ax.bar([xx + k * largeur for xx in x], vals, largeur,
               label=c, color=couleurs[k])
    ax.set_xticks([xx + 1.5 * largeur for xx in x], LIGNES)
    ax.set_ylabel("Tonnage produit en sortie (T)")
    ax.legend(title="Semaine", frameon=False)
    _style(ax, "E14 — Plan de marche : tonnage produit par ligne et semaine")
    fig.tight_layout()
    fig.savefig(chemin, dpi=130, facecolor="white")
    plt.close(fig)


# ---------------------------------------------------------------------------
# E18 — Shadow prices HRC par grade
# ---------------------------------------------------------------------------


def fig_e18(m, chemin):
    duals = {g: (m.c_hrc[g].pi or 0.0) for g in m.c_hrc}
    ordre = sorted(duals, key=lambda g: duals[g], reverse=True)
    vals = [duals[g] for g in ordre]
    couleurs = [NAVY if v > 1e-6 else GRIS for v in vals]

    fig, ax = plt.subplots(figsize=(8, 4.6))
    fig.patch.set_facecolor("white")
    barres = ax.barh(ordre, vals, color=couleurs)
    ax.invert_yaxis()
    for b, v in zip(barres, vals):
        ax.text(v + 20, b.get_y() + b.get_height() / 2,
                f"{v:.0f}" + ("  (non saturé)" if v < 1e-6 else ""),
                va="center", color=NAVY, fontsize=10, fontweight="bold")
    ax.set_xlabel("Prix dual (MAD / tonne de HRC)")
    ax.set_xlim(0, max(vals) * 1.25 + 50)
    _style(ax, "E18 — Valeur marginale du HRC par grade")
    fig.tight_layout()
    fig.savefig(chemin, dpi=130, facecolor="white")
    plt.close(fig)


# ---------------------------------------------------------------------------
# E19 — Marge/T + taux de service par famille
# ---------------------------------------------------------------------------


def fig_e19(m, chemin):
    df = analyse.marge_famille(m)
    fams = df["Famille"].tolist()
    marge_t = df["Marge/T (MAD)"].tolist()
    service = df["Service (%)"].tolist()

    fig, ax1 = plt.subplots(figsize=(8.6, 5))
    fig.patch.set_facecolor("white")
    barres = ax1.bar(fams, marge_t, color=NAVY, width=0.6, label="Marge / tonne")
    for b, v in zip(barres, marge_t):
        # valeur à l'intérieur de la barre (évite la collision avec la courbe)
        dedans = v > max(marge_t) * 0.12
        ax1.text(b.get_x() + b.get_width() / 2,
                 v - max(marge_t) * 0.05 if dedans else v + max(marge_t) * 0.03,
                 f"{v:.0f}", ha="center",
                 va="top" if dedans else "bottom",
                 color="white" if dedans else NAVY, fontsize=10, fontweight="bold")
    ax1.set_ylabel("Marge par tonne livrée (MAD/T)", color=NAVY)
    ax1.set_ylim(0, max(marge_t) * 1.30)

    ax2 = ax1.twinx()
    ax2.plot(fams, service, "o-", color=ORANGE, linewidth=2, markersize=9,
             label="Taux de service")
    for x, v in zip(fams, service):
        ax2.text(x, v + 4, f"{v:.0f}%", ha="center", color=ORANGE,
                 fontsize=9, fontweight="bold")
    ax2.set_ylabel("Taux de service (%)", color=ORANGE)
    ax2.set_ylim(0, 125)
    ax2.spines["top"].set_visible(False)

    ax1.set_title("E19 — Marge par tonne et taux de service par famille",
                  color=NAVY, fontsize=13, fontweight="bold", pad=12)
    ax1.spines["top"].set_visible(False)
    fig.tight_layout()
    fig.savefig(chemin, dpi=130, facecolor="white")
    plt.close(fig)


# ---------------------------------------------------------------------------
# Vérification des chiffres de référence
# ---------------------------------------------------------------------------


def verifier(m):
    syn = {r["Indicateur"]: r["Valeur"] for _, r in analyse.synthese(m).iterrows()}
    print("=" * 60)
    print("VÉRIFICATION DES CHIFFRES DE RÉFÉRENCE")
    print("=" * 60)
    print(f"Statut                 : {syn['Statut']}")
    print(f"Marge optimale         : {syn['Marge totale (MAD)']:,.0f} MAD  (réf 34 966 832)")
    print(f"Taux de service        : {syn['Taux de service global (%)']:.1f} %  (réf 81,2)")
    print(f"Pleines/part./refusées : {int(syn['Commandes pleines'])} / "
          f"{int(syn['Commandes partielles'])} / {int(syn['Commandes refusées'])}  (réf 47/4/14)")
    print("-" * 60)
    print("Utilisation (horizon) :")
    util = analyse.utilisation(m).set_index("Ligne")["Horizon (%)"]
    for lg in LIGNES:
        print(f"   {lg:5}: {util[lg]:5.1f} %")
    print("-" * 60)
    print("Shadow prices HRC (MAD/T) :")
    for g in sorted(m.c_hrc, key=lambda g: (m.c_hrc[g].pi or 0), reverse=True):
        print(f"   {g:5}: {m.c_hrc[g].pi or 0:7.1f}")
    print("=" * 60)


def main():
    os.makedirs(OUT, exist_ok=True)
    d = charger_donnees(XLSX)
    m = construire_et_resoudre(d)
    verifier(m)

    fig_e14(m, os.path.join(OUT, "fig_E14_plan_de_marche.png"))
    fig_e16(m, os.path.join(OUT, "fig_E16_utilisation.png"))
    fig_e18(m, os.path.join(OUT, "fig_E18_shadow_hrc.png"))
    fig_e19(m, os.path.join(OUT, "fig_E19_marge_famille.png"))
    b8_tracer(d, os.path.join(OUT, "fig_B8_enveloppe_dc01.png"))

    print("\n5 figures générées dans outputs/ :")
    for f in ["fig_E14_plan_de_marche", "fig_E16_utilisation", "fig_E18_shadow_hrc",
              "fig_E19_marge_famille", "fig_B8_enveloppe_dc01"]:
        print(f"   {f}.png")


if __name__ == "__main__":
    main()
