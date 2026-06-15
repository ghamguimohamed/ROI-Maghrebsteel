"""Modèle de Niveau 3 — stocks interprocess (Full Hard) entre laminage et galva.

Le modèle essentiel (Niveau 2, `model.py`) suppose qu'une route traverse tous
ses process dans la même semaine. Le Niveau 3 lève cette hypothèse : une route
est découpée en SEGMENTS séparés par des tampons « Full Hard », et chaque
segment peut tourner une semaine différente. On gagne ainsi de la flexibilité
de calendrier (laminer tôt, galvaniser plus tard), limitée par la capacité de
stockage des tampons.

Décomposition en segments
--------------------------
Les points de tampon (données `Stocks_Initiaux`, bloc interprocess) sont situés
en sortie de CRMA, CRMB, BAF et SKP. Un segment est une suite maximale de
process se terminant juste avant un tampon (ou à la finition). SKP étant
toujours la finition du CRC, le tampon SKP-out se confond avec le stock fini
CRC et n'est pas modélisé séparément. Le PK est toujours regroupé avec le
laminoir suivant (pas de tampon PK dans ce modèle).

Exemples :
  CRC  PK→CRMB→BAF→SKP   : [PK,CRMB] -FH-CRMB- [BAF] -BAF-out- [SKP]
  HDG  PK→CRMA→LGA       : [PK,CRMA] -FH-CRMA- [LGA]
  BACR PK→CRMB→BAF→LGB   : [PK,CRMB] -FH-CRMB- [BAF] -BAF-out- [LGB]
  HRC DEC PK             : [PK]

Hypothèses (assumées et documentées)
------------------------------------
* Variable de flux `g[c,r,s,t]` = tonnage FINI-équivalent traité par le
  segment s de la route r de la commande c en semaine t.
* Précédence par commande (cumulatif) : on ne peut pas traiter en aval plus
  que ce que l'amont a produit jusque-là — le WIP par commande reste ≥ 0.
* Les tampons sont bornés en TONNES PHYSIQUES, agrégées par point :
  `init[point] + Σ θ(r,ℓ)·WIP ≤ max`. Le stock initial (≥ min partout) est
  traité comme une réserve fixe de bobines d'autres spécifications : il occupe
  une partie de la capacité du tampon mais n'est pas consommable par le carnet
  courant (le min de sécurité est donc automatiquement satisfait).
* Coûts, rendements, capacité, HRC, stock fini, livraisons : identiques au
  Niveau 2 (la marge unitaire couvre déjà tous les process de la route).

Le Niveau 3 est une RELAXATION du Niveau 2 (on retrouve le Niveau 2 en forçant
tous les segments la même semaine) : sa marge optimale est donc ≥ celle du
Niveau 2.
"""

from __future__ import annotations

import pulp

from model import (
    FAMILLE_QUARTO, LIGNES, Modele, _calc_route, penalite_priorite,
    routes_famille,
)
from parse_data import Donnees

# Process en sortie desquels se trouve un tampon Full Hard -> nom du point
_TAMPON = {"CRMA": "FH-CRMA", "CRMB": "FH-CRMB", "BAF": "BAF-out", "SKP": "SKP-out"}


def segments(route: tuple[str, ...]) -> list[list[str]]:
    """Découpe une route en segments séparés par les tampons interprocess.

    Un tampon ferme le segment courant SAUF si le process est la finition
    (dernier de la route) : son flux part alors vers le stock fini.
    """
    segs, courant = [], []
    for i, pr in enumerate(route):
        courant.append(pr)
        est_dernier = (i == len(route) - 1)
        if pr in _TAMPON and not est_dernier:
            segs.append(courant)
            courant = []
    if courant:
        segs.append(courant)
    return segs


def point_tampon(segment: list[str]) -> str | None:
    """Point de tampon en sortie d'un segment (None si segment de finition)."""
    return _TAMPON.get(segment[-1])


def construire_n3(d: Donnees, retards_autorises: bool = False,
                  cout_stockage: bool = False) -> Modele:
    """Construit le programme linéaire de Niveau 3 (sans le résoudre)."""
    m = Modele(donnees=d, retards_autorises=retards_autorises,
               cout_stockage=cout_stockage)
    m.prob = pulp.LpProblem("MaghrebSteel_N3", pulp.LpMaximize)

    m.commandes = [c for c in d.commandes if c["famille"] != FAMILLE_QUARTO]
    m.familles = sorted({c["famille"] for c in m.commandes})
    semaines = list(d.semaines)

    # Pré-calcul routes + segments
    segs = {}     # (cid, ridx) -> list[list[process]]
    for c in m.commandes:
        cid = c["id"]
        m.routes[cid] = [_calc_route(c, r, d) for r in routes_famille(c["famille"])]
        for ridx, r in enumerate(routes_famille(c["famille"])):
            segs[(cid, ridx)] = segments(r)
    m.segments = segs  # type: ignore[attr-defined]

    def semaines_liv(ech):
        return [t for t in semaines if t >= ech] if retards_autorises else [ech]

    # --- Variables ---------------------------------------------------------
    g = {}        # (cid, ridx, s, t) -> flux segment
    for c in m.commandes:
        cid, ech = c["id"], c["semaine"]
        m.x[cid] = pulp.LpVariable(f"x_{cid}", lowBound=0, upBound=c["tonnage"])
        for t in semaines_liv(ech):
            m.xw[(cid, t)] = pulp.LpVariable(f"xw_{cid}_{t}", lowBound=0)
        for ridx in range(len(m.routes[cid])):
            for s in range(len(segs[(cid, ridx)])):
                for t in semaines:
                    g[(cid, ridx, s, t)] = pulp.LpVariable(
                        f"g_{cid}_{ridx}_{s}_{t}", lowBound=0)
    m.g = g  # type: ignore[attr-defined]

    for f in m.familles:
        sf = d.stocks_finis[f]
        for t in semaines:
            m.S[(f, t)] = pulp.LpVariable(
                f"S_{f}_{t}".replace(" ", ""), lowBound=sf["min"], upBound=sf["max"])

    def flux_seg(cid, ridx, s):
        """Liste des variables g du segment s, toutes semaines."""
        return [g[(cid, ridx, s, t)] for t in semaines]

    def output_fini(cid, ridx, t):
        """Flux du segment de finition (dernier) en semaine t."""
        last = len(segs[(cid, ridx)]) - 1
        return g[(cid, ridx, last, t)]

    # --- Objectif (identique au Niveau 2) ----------------------------------
    obj = []
    for c in m.commandes:
        obj.append(c["prix"] * m.x[c["id"]])
    for c in m.commandes:
        cid = c["id"]
        for ridx, rc in enumerate(m.routes[cid]):
            for t in semaines:
                obj.append(rc.marge_unitaire * output_fini(cid, ridx, t))
    if retards_autorises:
        for c in m.commandes:
            pen = penalite_priorite(d, c["priorite"])
            if pen:
                for t in semaines_liv(c["semaine"]):
                    if t - c["semaine"] > 0:
                        obj.append(-pen * (t - c["semaine"]) * m.xw[(c["id"], t)])
    if cout_stockage:
        cs = d.params.get("Coût stockage produit fini", 0.0)
        for v in m.S.values():
            obj.append(-cs * v)
    m.prob += pulp.lpSum(obj)

    # --- Liaison livraison / production ------------------------------------
    for c in m.commandes:
        cid = c["id"]
        livs = [m.xw[(cid, t)] for t in semaines_liv(c["semaine"])]
        m.prob += m.x[cid] == pulp.lpSum(livs), f"liv_{cid}"
        finis = [output_fini(cid, ridx, t)
                 for ridx in range(len(m.routes[cid])) for t in semaines]
        m.prob += m.x[cid] == pulp.lpSum(finis), f"liaison_{cid}"

    # --- Conservation entre segments : Σ_t g[s] = Σ_t g[s+1] ---------------
    for c in m.commandes:
        cid = c["id"]
        for ridx in range(len(m.routes[cid])):
            ns = len(segs[(cid, ridx)])
            for s in range(ns - 1):
                m.prob += (pulp.lpSum(flux_seg(cid, ridx, s))
                           == pulp.lpSum(flux_seg(cid, ridx, s + 1)),
                           f"cons_{cid}_{ridx}_{s}")

    # --- Précédence cumulative (WIP par commande ≥ 0) ----------------------
    for c in m.commandes:
        cid = c["id"]
        for ridx in range(len(m.routes[cid])):
            ns = len(segs[(cid, ridx)])
            for s in range(ns - 1):
                for t in semaines:
                    amont = pulp.lpSum(g[(cid, ridx, s, tau)] for tau in semaines if tau <= t)
                    aval = pulp.lpSum(g[(cid, ridx, s + 1, tau)] for tau in semaines if tau <= t)
                    m.prob += aval <= amont, f"prec_{cid}_{ridx}_{s}_{t}"

    # --- Capacité en jours-machine -----------------------------------------
    for ligne in LIGNES:
        for t in semaines:
            termes = []
            for c in m.commandes:
                cid, fam = c["id"], c["famille"]
                cad = d.cadences[ligne].get(fam)
                for ridx, rc in enumerate(m.routes[cid]):
                    for s, seg in enumerate(segs[(cid, ridx)]):
                        if ligne in seg:
                            termes.append(rc.theta[ligne] / cad * g[(cid, ridx, s, t)])
            if termes:
                dispo = d.jours_semaine - d.arrets[ligne][t]
                m.c_cap[(ligne, t)] = pulp.LpConstraint(
                    pulp.lpSum(termes), pulp.LpConstraintLE, f"cap_{ligne}_{t}", dispo)
                m.prob += m.c_cap[(ligne, t)]

    # --- HRC par grade (consommé par PK = segment 0) -----------------------
    for grade in sorted({c["grade"] for c in m.commandes}):
        if grade not in d.dispo_hrc:
            continue
        termes = []
        for c in m.commandes:
            if c["grade"] != grade:
                continue
            cid = c["id"]
            for ridx, rc in enumerate(m.routes[cid]):
                for t in semaines:
                    termes.append(rc.hrc_par_t * g[(cid, ridx, 0, t)])
        if termes:
            m.c_hrc[grade] = pulp.LpConstraint(
                pulp.lpSum(termes), pulp.LpConstraintLE, f"hrc_{grade}", d.dispo_hrc[grade])
            m.prob += m.c_hrc[grade]

    # --- Tampons interprocess (tonnes physiques agrégées) ------------------
    m.c_tampon = {}  # type: ignore[attr-defined]
    for point, sf in d.stocks_interprocess.items():
        if point == "SKP-out":          # confondu avec le stock fini CRC
            continue
        for t in semaines:
            termes = []
            for c in m.commandes:
                cid = c["id"]
                for ridx, rc in enumerate(m.routes[cid]):
                    for s, seg in enumerate(segs[(cid, ridx)]):
                        if point_tampon(seg) != point:
                            continue
                        # WIP physique par commande = θ(ℓ) · (amont - aval) cumulés
                        theta = rc.theta[seg[-1]]
                        wip = pulp.lpSum(
                            g[(cid, ridx, s, tau)] - g[(cid, ridx, s + 1, tau)]
                            for tau in semaines if tau <= t)
                        termes.append(theta * wip)
            if termes:
                ctr = pulp.LpConstraint(
                    pulp.lpSum(termes), pulp.LpConstraintLE,
                    f"tampon_{point}_{t}", sf["max"] - sf["init"])
                m.c_tampon[(point, t)] = ctr  # type: ignore[index]
                m.prob += ctr

    # --- Bilan de stock fini -----------------------------------------------
    for f in m.familles:
        init = d.stocks_finis[f]["init"]
        for t in semaines:
            prod_t = [output_fini(c["id"], ridx, t)
                      for c in m.commandes if c["famille"] == f
                      for ridx in range(len(m.routes[c["id"]]))]
            liv_t = [m.xw[(c["id"], t)] for c in m.commandes
                     if c["famille"] == f and (c["id"], t) in m.xw]
            prec = init if t == semaines[0] else m.S[(f, t - 1)]
            m.prob += (m.S[(f, t)] == prec + pulp.lpSum(prod_t) - pulp.lpSum(liv_t),
                       f"stock_{f}_{t}".replace(" ", ""))

    return m


def resoudre_n3(m: Modele, msg: bool = False) -> Modele:
    m.prob.solve(pulp.PULP_CBC_CMD(msg=msg))
    m.statut = pulp.LpStatus[m.prob.status]
    m.marge = pulp.value(m.prob.objective)
    if m.retards_autorises:
        total = 0.0
        for c in m.commandes:
            pen = penalite_priorite(m.donnees, c["priorite"])
            for t in m.donnees.semaines:
                if t - c["semaine"] > 0 and (c["id"], t) in m.xw:
                    total += pen * (t - c["semaine"]) * (pulp.value(m.xw[(c["id"], t)]) or 0.0)
        m.penalite_retard = total
    if m.cout_stockage:
        cs = m.donnees.params.get("Coût stockage produit fini", 0.0)
        m.cout_stockage_paye = cs * sum((pulp.value(v) or 0.0) for v in m.S.values())
    return m


def construire_et_resoudre_n3(d: Donnees, msg: bool = False,
                              retards_autorises: bool = False,
                              cout_stockage: bool = False) -> Modele:
    return resoudre_n3(
        construire_n3(d, retards_autorises=retards_autorises,
                      cout_stockage=cout_stockage), msg=msg)
