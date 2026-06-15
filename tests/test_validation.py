"""Validation indépendante de la solution (question E15).

Ce script est VOLONTAIREMENT séparé du solveur : à partir des seules valeurs
`x` (livré) et `p` (production) de la solution optimale, il recalcule toutes
les grandeurs « à la main » et vérifie :

  (a) capacité de chaque ligne/semaine ≤ jours disponibles ;
  (b) HRC consommé par grade ≤ disponibilité ;
  (c) bilans de stock cohérents + bornes min/max respectées ;
  (d) x[c] = Σ p[c]  et  x[c] ≤ demande ;
  (e) marge recalculée depuis (x, p) == objectif du solveur.

Tolérance numérique : 1e-4. Le test échoue (assert / exit 1) si une
contrainte est violée.
"""

from __future__ import annotations

import os
import sys
from math import prod

sys.path.insert(0, os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "src"))

import pulp  # noqa: E402

from model import (  # noqa: E402
    LIGNES, cle_cout, construire_et_resoudre, routes_famille, tranche_epaisseur,
)
from parse_data import charger_donnees  # noqa: E402

TOL = 1e-4


def _solution_brute(m):
    """Extrait x et p en valeurs flottantes pures (indépendant des objets PuLP)."""
    x = {c["id"]: (pulp.value(m.x[c["id"]]) or 0.0) for c in m.commandes}
    p = {}
    for (cid, ridx, t), v in m.p.items():
        val = pulp.value(v) or 0.0
        if val > TOL:
            p[(cid, ridx, t)] = val
    return x, p


def valider(chemin_xlsx: str, retards: bool = False,
            cout_stockage: bool = False) -> list[str]:
    """Renvoie la liste des violations détectées (vide = tout est correct)."""
    from model import penalite_priorite

    d = charger_donnees(chemin_xlsx)
    m = construire_et_resoudre(d, retards_autorises=retards,
                               cout_stockage=cout_stockage)
    x, p = _solution_brute(m)
    # livraisons par semaine (généralise le cas avec retards)
    xw = {k: (pulp.value(v) or 0.0) for k, v in m.xw.items()}
    cmds = {c["id"]: c for c in m.commandes}
    erreurs: list[str] = []

    # Recalcul indépendant des coefficients de route -----------------------
    def coeffs(cid, ridx):
        c = cmds[cid]
        route = routes_famille(c["famille"])[ridx]
        rhos = [d.rendements[pr]["rendement"] for pr in route]
        Pi = prod(rhos)
        theta = {}
        for i, pr in enumerate(route):
            aval = prod(rhos[i + 1:]) if i + 1 < len(route) else 1.0
            theta[pr] = 1.0 / aval
        tr = tranche_epaisseur(c["epaisseur"])
        fam = c["famille"]
        gamma = sum(d.couts[cle_cout(pr, fam)][tr] * theta[pr] for pr in route)
        lam = d.prix_hrc[c["grade"]][c["largeur"]] / Pi
        xi = 1800.0 * sum(d.rendements[pr]["chute"] * (theta[pr] / d.rendements[pr]["rendement"])
                          for pr in route)
        zinc = 450.0 if fam in ("HDG", "PPGI") else 0.0
        return route, Pi, theta, (xi - gamma - lam - zinc)

    # (d) liaison x = Σ p et x ≤ demande -----------------------------------
    for cid, c in cmds.items():
        somme_p = sum(v for (k, ridx, t), v in p.items() if k == cid)
        if abs(x[cid] - somme_p) > 1e-3:
            erreurs.append(f"(d) {cid}: x={x[cid]:.3f} != Σp={somme_p:.3f}")
        if x[cid] > c["tonnage"] + TOL:
            erreurs.append(f"(d) {cid}: livré {x[cid]:.3f} > demande {c['tonnage']}")
        # x = Σ_t livraisons par semaine
        somme_xw = sum(v for (k, t), v in xw.items() if k == cid)
        if abs(x[cid] - somme_xw) > 1e-3:
            erreurs.append(f"(d) {cid}: x={x[cid]:.3f} != Σxw={somme_xw:.3f}")
        # production jamais après l'échéance (sauf si retards autorisés)
        if not retards:
            for (k, ridx, t), v in p.items():
                if k == cid and t > c["semaine"]:
                    erreurs.append(f"(d) {cid}: production S{t} > échéance S{c['semaine']}")
        # livraison jamais avant l'échéance
        for (k, t), v in xw.items():
            if k == cid and v > TOL and t < c["semaine"]:
                erreurs.append(f"(d) {cid}: livraison S{t} < échéance S{c['semaine']}")

    # (a) capacité jours-machine -------------------------------------------
    for ligne in LIGNES:
        for t in d.semaines:
            jours = 0.0
            for (cid, ridx, tt), v in p.items():
                if tt != t:
                    continue
                route, Pi, theta, _ = coeffs(cid, ridx)
                if ligne in route:
                    cad = d.cadences[ligne][cmds[cid]["famille"]]
                    jours += theta[ligne] / cad * v
            dispo = d.jours_semaine - d.arrets[ligne][t]
            if jours > dispo + 1e-3:
                erreurs.append(f"(a) {ligne} S{t}: {jours:.4f} j > {dispo} j dispo")

    # (b) HRC par grade -----------------------------------------------------
    for g in d.dispo_hrc:
        conso = 0.0
        for (cid, ridx, t), v in p.items():
            if cmds[cid]["grade"] != g:
                continue
            _, Pi, _, _ = coeffs(cid, ridx)
            conso += v / Pi
        if conso > d.dispo_hrc[g] + 1e-2:
            erreurs.append(f"(b) HRC {g}: {conso:.2f} T > {d.dispo_hrc[g]} T")

    # (c) bilans de stock ---------------------------------------------------
    stock_total = 0.0
    for f in m.familles:
        sf = d.stocks_finis[f]
        prec = sf["init"]
        for t in d.semaines:
            prod_t = sum(v for (cid, ridx, tt), v in p.items()
                         if tt == t and cmds[cid]["famille"] == f)
            liv_t = sum(v for (cid, tt), v in xw.items()
                        if tt == t and cmds[cid]["famille"] == f)
            stock = prec + prod_t - liv_t
            if stock < sf["min"] - 1e-3 or stock > sf["max"] + 1e-3:
                erreurs.append(f"(c) stock {f} S{t} = {stock:.2f} hors [{sf['min']},{sf['max']}]")
            stock_total += stock
            prec = stock

    # (e) marge recalculée == objectif solveur -----------------------------
    marge = sum(cmds[cid]["prix"] * x[cid] for cid in cmds)
    for (cid, ridx, t), v in p.items():
        _, _, _, mu = coeffs(cid, ridx)
        marge += mu * v
    if retards:  # retrancher les pénalités de retard
        for (cid, t), v in xw.items():
            r = t - cmds[cid]["semaine"]
            if r > 0:
                marge -= penalite_priorite(d, cmds[cid]["priorite"]) * r * v
    if cout_stockage:  # retrancher le coût de stockage fini
        marge -= d.params.get("Coût stockage produit fini", 0.0) * stock_total
    if abs(marge - m.marge) > max(1.0, abs(m.marge) * 1e-6):
        erreurs.append(f"(e) marge recalculée {marge:.2f} != objectif {m.marge:.2f}")

    return erreurs


def valider_n3(chemin_xlsx: str) -> list[str]:
    """Validation indépendante du modèle de Niveau 3 (stocks interprocess).

    Recalcule depuis les flux de segments g[c,r,s,t] : capacité, HRC, bilans
    de stock fini, précédence/conservation, bornes des tampons et marge.
    """
    from model_n3 import construire_et_resoudre_n3, point_tampon

    d = charger_donnees(chemin_xlsx)
    m = construire_et_resoudre_n3(d)
    cmds = {c["id"]: c for c in m.commandes}
    g = {k: (pulp.value(v) or 0.0) for k, v in m.g.items()}
    xw = {k: (pulp.value(v) or 0.0) for k, v in m.xw.items()}
    x = {cid: (pulp.value(m.x[cid]) or 0.0) for cid in cmds}
    erreurs: list[str] = []
    sem = list(d.semaines)

    def rc(cid, ridx):
        return m.routes[cid][ridx]

    def n_seg(cid, ridx):
        return len(m.segments[(cid, ridx)])

    # (d) liaison + conservation + précédence -------------------------------
    for cid, c in cmds.items():
        for ridx in range(len(m.routes[cid])):
            last = n_seg(cid, ridx) - 1
            tot_fini = sum(g[(cid, ridx, last, t)] for t in sem)
            for s in range(n_seg(cid, ridx)):
                tot_s = sum(g[(cid, ridx, s, t)] for t in sem)
                if abs(tot_s - tot_fini) > 1e-3:
                    erreurs.append(f"(d) conservation {cid} r{ridx} seg{s}: {tot_s:.2f} != {tot_fini:.2f}")
                if s < last:  # précédence cumulative
                    for t in sem:
                        amont = sum(g[(cid, ridx, s, tau)] for tau in sem if tau <= t)
                        aval = sum(g[(cid, ridx, s + 1, tau)] for tau in sem if tau <= t)
                        if aval > amont + 1e-3:
                            erreurs.append(f"(d) précédence {cid} r{ridx} seg{s} S{t}: aval {aval:.2f} > amont {amont:.2f}")
        somme_fini = sum(g[(cid, ridx, n_seg(cid, ridx) - 1, t)]
                         for ridx in range(len(m.routes[cid])) for t in sem)
        somme_xw = sum(v for (k, t), v in xw.items() if k == cid)
        if abs(x[cid] - somme_fini) > 1e-3 or abs(x[cid] - somme_xw) > 1e-3:
            erreurs.append(f"(d) liaison {cid}: x={x[cid]:.2f} fini={somme_fini:.2f} xw={somme_xw:.2f}")
        if x[cid] > c["tonnage"] + TOL:
            erreurs.append(f"(d) {cid}: livré > demande")

    # (a) capacité ----------------------------------------------------------
    for ligne in LIGNES:
        for t in sem:
            jours = 0.0
            for cid, c in cmds.items():
                cad = d.cadences[ligne].get(c["famille"])
                for ridx in range(len(m.routes[cid])):
                    for s, seg in enumerate(m.segments[(cid, ridx)]):
                        if ligne in seg:
                            jours += rc(cid, ridx).theta[ligne] / cad * g[(cid, ridx, s, t)]
            dispo = d.jours_semaine - d.arrets[ligne][t]
            if jours > dispo + 1e-3:
                erreurs.append(f"(a) {ligne} S{t}: {jours:.3f} > {dispo}")

    # (b) HRC (segment 0) ---------------------------------------------------
    for gr in d.dispo_hrc:
        conso = sum(rc(cid, ridx).hrc_par_t * g[(cid, ridx, 0, t)]
                    for cid, c in cmds.items() if c["grade"] == gr
                    for ridx in range(len(m.routes[cid])) for t in sem)
        if conso > d.dispo_hrc[gr] + 1e-2:
            erreurs.append(f"(b) HRC {gr}: {conso:.2f} > {d.dispo_hrc[gr]}")

    # (e) tampons interprocess (tonnes physiques) ---------------------------
    for point, sf in d.stocks_interprocess.items():
        if point == "SKP-out":
            continue
        for t in sem:
            phys = sf["init"]
            for cid in cmds:
                for ridx in range(len(m.routes[cid])):
                    for s, seg in enumerate(m.segments[(cid, ridx)]):
                        if point_tampon(seg) != point:
                            continue
                        theta = rc(cid, ridx).theta[seg[-1]]
                        wip = sum(g[(cid, ridx, s, tau)] - g[(cid, ridx, s + 1, tau)]
                                  for tau in sem if tau <= t)
                        phys += theta * wip
            if phys > sf["max"] + 1e-2 or phys < sf["min"] - 1e-2:
                erreurs.append(f"(e) tampon {point} S{t} = {phys:.2f} hors [{sf['min']},{sf['max']}]")

    # (c) bilan stock fini --------------------------------------------------
    for f in m.familles:
        sf = d.stocks_finis[f]
        prec = sf["init"]
        for t in sem:
            prod_t = sum(g[(cid, ridx, n_seg(cid, ridx) - 1, t)]
                         for cid, c in cmds.items() if c["famille"] == f
                         for ridx in range(len(m.routes[cid])))
            liv_t = sum(v for (cid, tt), v in xw.items()
                        if tt == t and cmds[cid]["famille"] == f)
            stock = prec + prod_t - liv_t
            if stock < sf["min"] - 1e-3 or stock > sf["max"] + 1e-3:
                erreurs.append(f"(c) stock {f} S{t} = {stock:.2f} hors bornes")
            prec = stock

    # (f) marge -------------------------------------------------------------
    marge = sum(cmds[cid]["prix"] * x[cid] for cid in cmds)
    for cid in cmds:
        for ridx in range(len(m.routes[cid])):
            last = n_seg(cid, ridx) - 1
            marge += rc(cid, ridx).marge_unitaire * sum(g[(cid, ridx, last, t)] for t in sem)
    if abs(marge - m.marge) > max(1.0, abs(m.marge) * 1e-6):
        erreurs.append(f"(f) marge recalculée {marge:.2f} != objectif {m.marge:.2f}")

    return erreurs


def _chemin():
    ici = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    return os.path.join(ici, "data", "Donnees_MaghrebSteel.xlsx")


def test_validation():
    """Modèle essentiel (livraison à l'échéance)."""
    erreurs = valider(_chemin(), retards=False)
    assert not erreurs, "Violations détectées :\n" + "\n".join(erreurs)


def test_validation_retards():
    """Extension : livraisons en retard avec pénalité."""
    erreurs = valider(_chemin(), retards=True)
    assert not erreurs, "Violations (retards) :\n" + "\n".join(erreurs)


def test_validation_stockage():
    """Extension : facturation du stockage des produits finis."""
    erreurs = valider(_chemin(), cout_stockage=True)
    assert not erreurs, "Violations (stockage) :\n" + "\n".join(erreurs)


def test_validation_n3():
    """Niveau 3 : stocks interprocess (Full Hard)."""
    erreurs = valider_n3(_chemin())
    assert not erreurs, "Violations (Niveau 3) :\n" + "\n".join(erreurs)


def test_n3_relaxation():
    """Le Niveau 3 est une relaxation du Niveau 2 : marge_N3 >= marge_N2."""
    from model import construire_et_resoudre
    from model_n3 import construire_et_resoudre_n3
    d = charger_donnees(_chemin())
    m2 = construire_et_resoudre(d)
    m3 = construire_et_resoudre_n3(d)
    assert m3.marge >= m2.marge - 1.0, f"N3 {m3.marge} < N2 {m2.marge}"


if __name__ == "__main__":
    ici = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    erreurs = valider(os.path.join(ici, "data", "Donnees_MaghrebSteel.xlsx"))
    if erreurs:
        print("ÉCHEC — violations détectées :")
        for e in erreurs:
            print("  -", e)
        sys.exit(1)
    print("OK — la solution respecte toutes les contraintes (a)-(e).")
