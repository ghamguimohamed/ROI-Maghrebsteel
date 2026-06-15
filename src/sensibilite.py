"""Analyses de sensibilité (questions E20–E22 et B8).

Chaque scénario part d'une copie profonde des données de base, applique la
perturbation, reconstruit et résout le modèle, puis compare à la référence.
"""

from __future__ import annotations

import copy

import pulp

from analyse import livraison
from model import construire_et_resoudre
from parse_data import Donnees, charger_donnees


def _marge_base(d: Donnees) -> tuple[float, object]:
    m = construire_et_resoudre(d)
    return m.marge, m


# ---------------------------------------------------------------------------
# E20 — Prix HRC +10 % sur tous les grades
# ---------------------------------------------------------------------------


def e20_hrc_plus_10(d: Donnees) -> dict:
    base, _ = _marge_base(d)
    d2 = copy.deepcopy(d)
    for g in d2.prix_hrc:
        for w in d2.prix_hrc[g]:
            d2.prix_hrc[g][w] *= 1.10
    m2 = construire_et_resoudre(d2)
    var = 100 * (m2.marge - base) / base
    return {
        "marge_base": base,
        "marge_scenario": m2.marge,
        "variation_pct": var,
        "statut": m2.statut,
    }


# ---------------------------------------------------------------------------
# E21 — 2 jours d'arrêt LGB supplémentaires en semaine 2
# ---------------------------------------------------------------------------


def e21_arret_lgb_s2(d: Donnees) -> dict:
    base, mb = _marge_base(d)
    livre_base = sum(livraison(mb).values())
    d2 = copy.deepcopy(d)
    d2.arrets["LGB"][2] = min(7, d2.arrets["LGB"][2] + 2)
    m2 = construire_et_resoudre(d2)
    livre2 = sum(livraison(m2).values())
    return {
        "marge_base": base,
        "marge_scenario": m2.marge,
        "delta_marge": m2.marge - base,
        "livre_base": livre_base,
        "livre_scenario": livre2,
        "delta_livre": livre2 - livre_base,
    }


# ---------------------------------------------------------------------------
# E22 — Nouvelle commande 300 T HDG DC01
# ---------------------------------------------------------------------------


def e22_commande_supplementaire(d: Donnees) -> dict:
    base, _ = _marge_base(d)
    d2 = copy.deepcopy(d)
    nouvelle = {
        "id": "CMD-NEW", "client": "Client_test", "famille": "HDG",
        "grade": "DC01", "epaisseur": 0.5, "largeur": 1140.0,
        "tonnage": 300.0, "prix": 11500.0, "semaine": 1, "priorite": "Haute",
    }
    d2.commandes.append(nouvelle)
    m2 = construire_et_resoudre(d2)
    livre_new = pulp.value(m2.x["CMD-NEW"])
    return {
        "marge_base": base,
        "marge_scenario": m2.marge,
        "delta_marge": m2.marge - base,
        "livre_new": livre_new,
        "demande_new": 300.0,
        "acceptee": livre_new >= 300.0 - 1e-3,
    }


# ---------------------------------------------------------------------------
# B8 — Balayage de la dispo DC01 (−50 % … +50 %)
# ---------------------------------------------------------------------------


def b8_balayage_dc01(d: Donnees, n: int = 21) -> dict:
    """Renvoie les points (dispo, marge) et tente de repérer la rupture de pente."""
    base_dispo = d.dispo_hrc["DC01"]
    facteurs = [0.5 + i * (1.0 / (n - 1)) for i in range(n)]  # 0.5 -> 1.5
    dispos, marges = [], []
    for f in facteurs:
        d2 = copy.deepcopy(d)
        d2.dispo_hrc["DC01"] = base_dispo * f
        m2 = construire_et_resoudre(d2)
        dispos.append(base_dispo * f)
        marges.append(m2.marge)

    # rupture de pente : variation max de la pente (dérivée seconde)
    rupture = None
    pentes = [(marges[i + 1] - marges[i]) / (dispos[i + 1] - dispos[i])
              for i in range(len(dispos) - 1)]
    max_d2 = 0.0
    for i in range(len(pentes) - 1):
        d2val = abs(pentes[i + 1] - pentes[i])
        if d2val > max_d2:
            max_d2 = d2val
            rupture = dispos[i + 1]
    return {"dispos": dispos, "marges": marges, "pentes": pentes, "rupture": rupture}


def b8_tracer(d: Donnees, chemin: str = "outputs/b8_dc01.png", n: int = 21) -> dict:
    """Trace la courbe marge = f(dispo DC01) et enregistre la figure."""
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    res = b8_balayage_dc01(d, n=n)
    fig, ax = plt.subplots(figsize=(8, 5))
    fig.patch.set_facecolor("white")
    ax.set_facecolor("white")
    ax.plot(res["dispos"], [mr / 1e6 for mr in res["marges"]],
            marker="o", color="#163A6B")
    if res["rupture"]:
        ax.axvline(res["rupture"], color="#E8512E", linestyle="--",
                   label=f"Rupture de pente ≈ {res['rupture']:.0f} T")
        ax.legend()
    ax.set_xlabel("Disponibilité HRC DC01 (T)")
    ax.set_ylabel("Marge optimale (M MAD)")
    ax.set_title("B8 — Sensibilité de la marge à la dispo DC01")
    ax.grid(True, alpha=0.3)
    fig.tight_layout()
    fig.savefig(chemin, dpi=110, facecolor="white")
    plt.close(fig)
    res["figure"] = chemin
    return res


# ---------------------------------------------------------------------------
# Extension — livraisons en retard avec pénalité
# ---------------------------------------------------------------------------


def comparer_retards(d: Donnees, arret_ligne: str | None = None,
                     arret_semaine: int = 1, arret_jours: int = 0) -> dict:
    """Compare le modèle sans / avec livraisons en retard, éventuellement sous
    une perturbation de capacité (pour mettre en évidence le gain)."""
    d2 = copy.deepcopy(d)
    if arret_ligne and arret_jours:
        d2.arrets[arret_ligne][arret_semaine] = min(
            7, d2.arrets[arret_ligne][arret_semaine] + arret_jours)

    m_sans = construire_et_resoudre(d2, retards_autorises=False)
    m_avec = construire_et_resoudre(d2, retards_autorises=True)
    liv_sans = sum(livraison(m_sans).values())
    liv_avec = sum(livraison(m_avec).values())
    return {
        "marge_sans": m_sans.marge,
        "marge_avec": m_avec.marge,
        "gain_marge": m_avec.marge - m_sans.marge,
        "livre_sans": liv_sans,
        "livre_avec": liv_avec,
        "penalites": m_avec.penalite_retard,
    }


def comparer_niveaux(d: Donnees, arret_ligne: str | None = None,
                     arret_semaine: int = 2, arret_jours: int = 0) -> dict:
    """Compare Niveau 2 (essentiel) et Niveau 3 (stocks interprocess),
    éventuellement sous une panne d'un laminoir amont."""
    from model_n3 import construire_et_resoudre_n3
    d2 = copy.deepcopy(d)
    if arret_ligne and arret_jours:
        d2.arrets[arret_ligne][arret_semaine] = min(
            7, d2.arrets[arret_ligne][arret_semaine] + arret_jours)
    m2 = construire_et_resoudre(d2)
    m3 = construire_et_resoudre_n3(d2)
    return {
        "marge_n2": m2.marge,
        "marge_n3": m3.marge,
        "gain": m3.marge - m2.marge,
    }


def comparer_stockage(d: Donnees) -> dict:
    """Compare le modèle sans / avec facturation du stockage fini."""
    import pulp as _pl
    m_sans = construire_et_resoudre(d, cout_stockage=False)
    m_avec = construire_et_resoudre(d, cout_stockage=True)
    stock_sans = sum(_pl.value(v) for v in m_sans.S.values())
    stock_avec = sum(_pl.value(v) for v in m_avec.S.values())
    return {
        "marge_sans": m_sans.marge,
        "marge_avec": m_avec.marge,
        "cout_stockage": m_avec.cout_stockage_paye,
        "stock_sans": stock_sans,
        "stock_avec": stock_avec,
    }


# ---------------------------------------------------------------------------
# Exécution directe
# ---------------------------------------------------------------------------


def lancer_tout(chemin_xlsx: str) -> None:
    d = charger_donnees(chemin_xlsx)
    print("E20 — Prix HRC +10 % :")
    r = e20_hrc_plus_10(d)
    print(f"   marge {r['marge_base']:,.0f} -> {r['marge_scenario']:,.0f}"
          f"  ({r['variation_pct']:+.1f} %)")

    print("E21 — +2 jours arrêt LGB S2 :")
    r = e21_arret_lgb_s2(d)
    print(f"   delta marge = {r['delta_marge']:+,.0f} MAD ;"
          f" delta livré = {r['delta_livre']:+.1f} T")

    print("E22 — Commande 300 T HDG DC01 :")
    r = e22_commande_supplementaire(d)
    statut = "ACCEPTÉE" if r["acceptee"] else "refusée"
    print(f"   {statut} {r['livre_new']:.0f}/300 ;"
          f" delta marge = {r['delta_marge']:+,.0f} MAD")

    print("B8 — Balayage dispo DC01 :")
    r = b8_tracer(d)
    print(f"   figure : {r['figure']} ; rupture de pente ≈ {r['rupture']:.0f} T")

    print("EXT — Livraisons en retard (extension) :")
    r = comparer_retards(d)
    print(f"   cas de base : gain marge = {r['gain_marge']:+,.0f} MAD"
          f" (bottleneck = HRC, peu d'effet)")
    r = comparer_retards(d, arret_ligne="LGA", arret_semaine=1, arret_jours=4)
    print(f"   sous crise capacité LGA S1 : gain marge = {r['gain_marge']:+,.0f} MAD"
          f" ; pénalités payées = {r['penalites']:,.0f} MAD")

    print("EXT — Coût de stockage des produits finis (extension) :")
    r = comparer_stockage(d)
    print(f"   marge {r['marge_sans']:,.0f} -> {r['marge_avec']:,.0f}"
          f" (coût stockage {r['cout_stockage']:,.0f} MAD)")
    print(f"   stock fini détenu : {r['stock_sans']:,.0f} -> {r['stock_avec']:,.0f}"
          f" T·sem (juste-à-temps)")

    print("EXT — Niveau 3 : stocks interprocess (extension) :")
    r = comparer_niveaux(d)
    print(f"   cas de base : N2 {r['marge_n2']:,.0f} -> N3 {r['marge_n3']:,.0f}"
          f" (gain {r['gain']:+,.0f} MAD)")
    r = comparer_niveaux(d, arret_ligne="CRMB", arret_semaine=2, arret_jours=4)
    print(f"   sous panne CRMB S2 : gain N3 = {r['gain']:+,.0f} MAD"
          f" (les tampons amortissent l'arrêt amont)")


if __name__ == "__main__":
    import os
    ici = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    lancer_tout(os.path.join(ici, "data", "Donnees_MaghrebSteel.xlsx"))
