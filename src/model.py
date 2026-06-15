"""Modèle d'optimisation linéaire (Niveau 2, LP continu) — PuLP + CBC.

Simulateur Capacité–Commande du laminage à froid de Maghreb Steel.

Conventions de modélisation (cf. spécification) :

* Périmètre : les 66 commandes SAUF le Quarto (hors laminage à froid).
  Le HRC DEC est inclus (décapage PK seul).
* Une route `r = (ℓ₁,…,ℓ_k)` est une séquence de process de PK à la finition.
* Pour une route :
    - Π_r            = Πᵢ ρ(ℓᵢ)                 (rendement de chaîne)
    - θ(r,ℓᵢ)        = 1 / Π_{j>i} ρ(ℓⱼ)        (T en sortie de ℓᵢ par T finie)
    - HRC/T finie    = 1 / Π_r
    - Γ (transfo)    = Σᵢ cout[clé(ℓᵢ)][tranche] · θ(r,ℓᵢ)
    - Λ (HRC)        = prix_HRC[grade][largeur] / Π_r
    - Ξ (chutes)     = 1800 · Σᵢ chute(ℓᵢ) · (θ(r,ℓᵢ)/ρ(ℓᵢ))
    - zinc           = +450 MAD/T si famille ∈ {HDG, PPGI}, sinon 0

Variables :
    p[c,r,τ] ≥ 0   tonnage fini de c via r produit en semaine τ (τ ≤ échéance)
    x[c] ∈ [0, demande_c]   tonnage livré (à l'échéance)
    S[f,t] ∈ [min_f, max_f] stock fini de la famille f en fin de semaine t
"""

from __future__ import annotations

from dataclasses import dataclass, field
from math import prod

import pulp

from parse_data import Donnees

# ---------------------------------------------------------------------------
# Définitions structurelles
# ---------------------------------------------------------------------------

LIGNES = ["PK", "CRMA", "CRMB", "BAF", "SKP", "LGA", "LGB"]
FAMILLE_QUARTO = "Quarto"  # exclue du modèle

# Bornes hautes (exclues) des 7 tranches d'épaisseur
_BORNES_TRANCHE = [0.3, 0.4, 0.5, 0.7, 1.0, 1.5]


def tranche_epaisseur(ep: float) -> int:
    """Indice de tranche [bas, haut[ : <0.3→0 … ≥1.5→6."""
    for i, b in enumerate(_BORNES_TRANCHE):
        if ep < b:
            return i
    return 6


def routes_famille(famille: str) -> list[tuple[str, ...]]:
    """Routes admissibles (séquence de process) pour une famille."""
    if famille == "CRC":
        return [("PK", "CRMB", "BAF", "SKP")]
    if famille == "HRC DEC":
        return [("PK",)]
    if famille == "HDG":
        return [("PK", "CRMA", "LGA"), ("PK", "CRMB", "LGA"),
                ("PK", "CRMA", "LGB"), ("PK", "CRMB", "LGB")]
    if famille == "PPGI":
        return [("PK", "CRMA", "LGA"), ("PK", "CRMB", "LGA")]
    if famille == "BACR":
        return [("PK", "CRMB", "BAF", "LGB"),                       # voie A
                ("PK", "CRMA", "LGA"), ("PK", "CRMB", "LGA"),        # voie B
                ("PK", "CRMA", "LGB"), ("PK", "CRMB", "LGB")]
    raise ValueError(f"Famille inconnue : {famille}")


def cle_cout(process: str, famille: str) -> str:
    """Clé du coût de transformation : galva = '<ligne>-<famille>'."""
    if process in ("LGA", "LGB"):
        return f"{process}-{famille}"
    return process


_CLE_PENALITE = {
    "Haute": "Pénalité retard commande Haute",
    "Normale": "Pénalité retard commande Normale",
    "Basse": "Pénalité retard commande Basse",
}


def penalite_priorite(d: Donnees, priorite: str) -> float:
    """Pénalité de retard (MAD/T/semaine) selon la priorité de la commande."""
    return d.params.get(_CLE_PENALITE.get(priorite, ""), 0.0)


# ---------------------------------------------------------------------------
# Pré-calcul des coefficients par (commande, route)
# ---------------------------------------------------------------------------


@dataclass
class RouteCalc:
    """Coefficients d'une route donnée appliquée à une commande."""
    processes: tuple[str, ...]
    Pi: float                      # rendement de chaîne
    theta: dict[str, float]        # θ(r,ℓ) par process de la route
    hrc_par_t: float               # 1 / Π_r
    cout_transfo: float            # Γ
    cout_hrc: float                # Λ
    valo_chutes: float             # Ξ
    zinc: float                    # extra zinc
    marge_unitaire: float          # Ξ − Γ − Λ − zinc (par T finie produite)


def _calc_route(cmd: dict, route: tuple[str, ...], d: Donnees) -> RouteCalc:
    rdt = d.rendements
    tr = tranche_epaisseur(cmd["epaisseur"])
    fam = cmd["famille"]

    rhos = [rdt[p]["rendement"] for p in route]
    Pi = prod(rhos)

    theta = {}
    for i, p in enumerate(route):
        aval = prod(rhos[i + 1:]) if i + 1 < len(route) else 1.0
        theta[p] = 1.0 / aval

    cout_transfo = sum(d.couts[cle_cout(p, fam)][tr] * theta[p] for p in route)
    cout_hrc = d.prix_hrc[cmd["grade"]][cmd["largeur"]] / Pi
    valo_chutes = 1800.0 * sum(
        rdt[p]["chute"] * (theta[p] / rdt[p]["rendement"]) for p in route
    )
    zinc = 450.0 if fam in ("HDG", "PPGI") else 0.0

    marge = valo_chutes - cout_transfo - cout_hrc - zinc
    return RouteCalc(route, Pi, theta, 1.0 / Pi, cout_transfo, cout_hrc,
                     valo_chutes, zinc, marge)


# ---------------------------------------------------------------------------
# Conteneur du modèle résolu
# ---------------------------------------------------------------------------


@dataclass
class Modele:
    prob: Any = None
    statut: str = ""
    marge: float = 0.0
    # variables (objets PuLP)
    p: dict = field(default_factory=dict)    # (cid, ridx, t) -> var
    x: dict = field(default_factory=dict)    # cid -> var (livré total)
    xw: dict = field(default_factory=dict)   # (cid, t) -> var (livré la semaine t)
    S: dict = field(default_factory=dict)    # (fam, t) -> var
    # contraintes (pour duals)
    c_cap: dict = field(default_factory=dict)   # (ligne, t) -> contrainte
    c_hrc: dict = field(default_factory=dict)   # grade -> contrainte
    # méta
    commandes: list = field(default_factory=list)   # commandes modélisées
    routes: dict = field(default_factory=dict)      # cid -> [RouteCalc, ...]
    donnees: Donnees = None
    familles: list = field(default_factory=list)
    retards_autorises: bool = False
    penalite_retard: float = 0.0   # MAD de pénalités de retard dans l'optimum
    cout_stockage: bool = False
    cout_stockage_paye: float = 0.0  # MAD de stockage fini dans l'optimum
    # spécifique Niveau 3 (model_n3.py)
    g: dict = field(default_factory=dict)         # (cid, ridx, s, t) -> var flux segment
    segments: dict = field(default_factory=dict)  # (cid, ridx) -> list[list[process]]
    c_tampon: dict = field(default_factory=dict)  # (point, t) -> contrainte tampon


# ---------------------------------------------------------------------------
# Construction + résolution
# ---------------------------------------------------------------------------


def construire(d: Donnees, retards_autorises: bool = False,
               cout_stockage: bool = False) -> Modele:
    """Construit le programme linéaire (sans le résoudre).

    Si ``retards_autorises`` est faux (défaut), on reproduit exactement le
    modèle essentiel : production en avance autorisée, livraison à l'échéance.

    Si vrai, une commande peut être PRODUITE et LIVRÉE après son échéance,
    moyennant une pénalité de retard (MAD/T/semaine selon la priorité) ;
    une commande sinon refusée peut alors être servie en retard.

    Si ``cout_stockage`` est vrai, le stock de produits finis détenu en fin de
    semaine est facturé (40 MAD/T/semaine, cf. Paramètres) : la production en
    avance n'est alors plus gratuite et le modèle tend vers le juste-à-temps.
    """
    m = Modele(donnees=d, retards_autorises=retards_autorises,
               cout_stockage=cout_stockage)
    m.prob = pulp.LpProblem("MaghrebSteel", pulp.LpMaximize)

    # Commandes retenues (hors Quarto)
    m.commandes = [c for c in d.commandes if c["famille"] != FAMILLE_QUARTO]
    m.familles = sorted({c["famille"] for c in m.commandes})
    semaines = list(d.semaines)

    # Pré-calcul des routes
    for c in m.commandes:
        m.routes[c["id"]] = [_calc_route(c, r, d) for r in routes_famille(c["famille"])]

    def semaines_prod(ech):
        # avec retards : on peut produire n'importe quelle semaine
        return semaines if retards_autorises else [t for t in semaines if t <= ech]

    def semaines_liv(ech):
        # avec retards : on peut livrer à l'échéance ou plus tard
        return [t for t in semaines if t >= ech] if retards_autorises else [ech]

    # --- Variables ---------------------------------------------------------
    for c in m.commandes:
        cid, ech = c["id"], c["semaine"]
        m.x[cid] = pulp.LpVariable(f"x_{cid}", lowBound=0, upBound=c["tonnage"])
        for t in semaines_liv(ech):
            m.xw[(cid, t)] = pulp.LpVariable(f"xw_{cid}_{t}", lowBound=0)
        for ridx in range(len(m.routes[cid])):
            for t in semaines_prod(ech):
                m.p[(cid, ridx, t)] = pulp.LpVariable(f"p_{cid}_{ridx}_{t}", lowBound=0)

    for f in m.familles:
        sf = d.stocks_finis[f]
        for t in semaines:
            m.S[(f, t)] = pulp.LpVariable(
                f"S_{f}_{t}".replace(" ", ""), lowBound=sf["min"], upBound=sf["max"])

    # --- Objectif ----------------------------------------------------------
    obj = []
    for c in m.commandes:
        obj.append(c["prix"] * m.x[c["id"]])                 # chiffre d'affaires
    for (cid, ridx, t), var in m.p.items():
        obj.append(m.routes[cid][ridx].marge_unitaire * var)  # marge de production
    if retards_autorises:                                     # pénalités de retard
        for c in m.commandes:
            pen = penalite_priorite(d, c["priorite"])
            if pen == 0:
                continue
            for t in semaines_liv(c["semaine"]):
                retard = t - c["semaine"]
                if retard > 0:
                    obj.append(-pen * retard * m.xw[(c["id"], t)])
    if cout_stockage:                                          # stockage fini
        cs = d.params.get("Coût stockage produit fini", 0.0)
        for (f, t) in m.S:
            obj.append(-cs * m.S[(f, t)])
    m.prob += pulp.lpSum(obj)

    # --- Contrainte 1 : liaison  x = Σ_t xw = Σ p --------------------------
    for c in m.commandes:
        cid = c["id"]
        livs = [m.xw[(cid, t)] for t in semaines_liv(c["semaine"])]
        m.prob += m.x[cid] == pulp.lpSum(livs), f"liv_{cid}"
        prods = [m.p[(cid, ridx, t)]
                 for ridx in range(len(m.routes[cid])) for t in semaines
                 if (cid, ridx, t) in m.p]
        m.prob += m.x[cid] == pulp.lpSum(prods), f"liaison_{cid}"

    # --- Contrainte 2 : capacité en jours-machine --------------------------
    for ligne in LIGNES:
        for t in semaines:
            termes = []
            for c in m.commandes:
                cid, fam = c["id"], c["famille"]
                cad = d.cadences[ligne].get(fam)
                for ridx, rc in enumerate(m.routes[cid]):
                    if ligne in rc.processes and (cid, ridx, t) in m.p:
                        coef = rc.theta[ligne] / cad
                        termes.append(coef * m.p[(cid, ridx, t)])
            if termes:
                dispo = d.jours_semaine - d.arrets[ligne][t]
                m.c_cap[(ligne, t)] = pulp.LpConstraint(
                    pulp.lpSum(termes), pulp.LpConstraintLE, f"cap_{ligne}_{t}", dispo)
                m.prob += m.c_cap[(ligne, t)]

    # --- Contrainte 3 : HRC par grade (pool sur l'horizon) -----------------
    grades = sorted({c["grade"] for c in m.commandes})
    for g in grades:
        if g not in d.dispo_hrc:
            continue
        termes = []
        for c in m.commandes:
            if c["grade"] != g:
                continue
            cid = c["id"]
            for ridx, rc in enumerate(m.routes[cid]):
                for t in semaines:
                    if (cid, ridx, t) in m.p:
                        termes.append(rc.hrc_par_t * m.p[(cid, ridx, t)])
        if termes:
            m.c_hrc[g] = pulp.LpConstraint(
                pulp.lpSum(termes), pulp.LpConstraintLE, f"hrc_{g}", d.dispo_hrc[g])
            m.prob += m.c_hrc[g]

    # --- Contrainte 4 : bilan de stock fini --------------------------------
    for f in m.familles:
        init = d.stocks_finis[f]["init"]
        for t in semaines:
            prod_t = [m.p[(c["id"], ridx, t)]
                      for c in m.commandes if c["famille"] == f
                      for ridx in range(len(m.routes[c["id"]]))
                      if (c["id"], ridx, t) in m.p]
            liv_t = [m.xw[(c["id"], t)] for c in m.commandes
                     if c["famille"] == f and (c["id"], t) in m.xw]
            prec = init if t == semaines[0] else m.S[(f, t - 1)]
            m.prob += (m.S[(f, t)] == prec + pulp.lpSum(prod_t) - pulp.lpSum(liv_t),
                       f"stock_{f}_{t}".replace(" ", ""))

    return m


def resoudre(m: Modele, msg: bool = False) -> Modele:
    """Résout le modèle avec CBC et remplit statut / marge / pénalités."""
    m.prob.solve(pulp.PULP_CBC_CMD(msg=msg))
    m.statut = pulp.LpStatus[m.prob.status]
    m.marge = pulp.value(m.prob.objective)
    # Pénalités de retard effectivement payées à l'optimum
    if m.retards_autorises:
        total = 0.0
        for c in m.commandes:
            pen = penalite_priorite(m.donnees, c["priorite"])
            if pen == 0:
                continue
            for t in m.donnees.semaines:
                retard = t - c["semaine"]
                if retard > 0 and (c["id"], t) in m.xw:
                    total += pen * retard * (pulp.value(m.xw[(c["id"], t)]) or 0.0)
        m.penalite_retard = total
    if m.cout_stockage:
        cs = m.donnees.params.get("Coût stockage produit fini", 0.0)
        m.cout_stockage_paye = cs * sum(
            (pulp.value(v) or 0.0) for v in m.S.values())
    return m


def construire_et_resoudre(d: Donnees, msg: bool = False,
                           retards_autorises: bool = False,
                           cout_stockage: bool = False) -> Modele:
    return resoudre(
        construire(d, retards_autorises=retards_autorises,
                   cout_stockage=cout_stockage), msg=msg)
