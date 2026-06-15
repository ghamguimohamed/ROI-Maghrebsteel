"""Lecture robuste du classeur Donnees_MaghrebSteel.xlsx.

Chaque onglet possède une ligne de titre (ligne 1), souvent une ligne vide,
puis l'en-tête réel. Le parser ne suppose JAMAIS que l'en-tête est en ligne 1 :
il détecte dynamiquement la ligne d'en-tête à partir d'ancres (mots attendus).

La fonction publique `charger_donnees(chemin)` renvoie un objet `Donnees`
regroupant toutes les tables nécessaires au modèle.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import openpyxl

# ---------------------------------------------------------------------------
# Conteneur de données
# ---------------------------------------------------------------------------


@dataclass
class Donnees:
    commandes: list[dict] = field(default_factory=list)         # 1 dict / commande
    cadences: dict[str, dict[str, float]] = field(default_factory=dict)   # [ligne][famille] -> T/jour
    rendements: dict[str, dict[str, float]] = field(default_factory=dict)  # [process] -> taux
    couts: dict[str, list[float]] = field(default_factory=dict)  # [cle] -> 7 tranches
    prix_hrc: dict[str, dict[float, float]] = field(default_factory=dict)  # [grade][largeur] -> MAD/T
    dispo_hrc: dict[str, float] = field(default_factory=dict)    # [grade] -> tonnes
    stocks_finis: dict[str, dict[str, float]] = field(default_factory=dict)  # [famille] -> init/min/max
    stocks_interprocess: dict[str, dict[str, float]] = field(default_factory=dict)  # [point] -> init/min/max
    arrets: dict[str, dict[int, int]] = field(default_factory=dict)  # [ligne][semaine] -> jours
    params: dict[str, float] = field(default_factory=dict)

    # constantes pratiques
    semaines: tuple = (1, 2, 3, 4)
    jours_semaine: int = 7


# ---------------------------------------------------------------------------
# Utilitaires de lecture
# ---------------------------------------------------------------------------


def _lire_lignes(ws) -> list[list[Any]]:
    """Renvoie l'onglet sous forme de liste de listes (valeurs brutes)."""
    return [list(row) for row in ws.iter_rows(values_only=True)]


def _trouver_entete(lignes: list[list[Any]], ancres: list[str]) -> int:
    """Indice (0-based) de la première ligne contenant l'une des `ancres`.

    Comparaison insensible à la casse et aux espaces. Permet d'ignorer la
    ligne de titre et les lignes vides en début d'onglet.
    """
    ancres_norm = [a.strip().lower() for a in ancres]
    for i, ligne in enumerate(lignes):
        for cell in ligne:
            if cell is None:
                continue
            if str(cell).strip().lower() in ancres_norm:
                return i
    raise ValueError(f"En-tête introuvable (ancres={ancres})")


def _est_nombre(v: Any) -> bool:
    return isinstance(v, (int, float)) and not isinstance(v, bool)


# ---------------------------------------------------------------------------
# Parsers par onglet
# ---------------------------------------------------------------------------


def _parser_commandes(lignes: list[list[Any]]) -> list[dict]:
    """Filtre les lignes dont l'ID commence par 'CMD'."""
    h = _trouver_entete(lignes, ["ID"])
    cmds = []
    for ligne in lignes[h + 1:]:
        if not ligne or ligne[0] is None:
            continue
        if not str(ligne[0]).strip().upper().startswith("CMD"):
            continue
        cmds.append(
            {
                "id": str(ligne[0]).strip(),
                "client": ligne[1],
                "famille": str(ligne[2]).strip(),
                "grade": str(ligne[3]).strip(),
                "epaisseur": float(ligne[4]),
                "largeur": float(ligne[5]),
                "tonnage": float(ligne[6]),
                "prix": float(ligne[7]),
                "semaine": int(ligne[8]),
                "priorite": str(ligne[9]).strip() if ligne[9] else "Normale",
            }
        )
    return cmds


def _parser_cadences(lignes: list[list[Any]]) -> dict[str, dict[str, float]]:
    h = _trouver_entete(lignes, ["Ligne / Famille"])
    familles = [str(c).strip() for c in lignes[h][1:] if c is not None]
    cad: dict[str, dict[str, float]] = {}
    for ligne in lignes[h + 1:]:
        if not ligne or ligne[0] is None:
            continue
        nom = str(ligne[0]).strip()
        # on s'arrête au premier bloc de texte explicatif
        if nom not in {"PK", "CRMA", "CRMB", "BAF", "SKP", "LGA", "LGB"}:
            continue
        cad[nom] = {}
        for j, fam in enumerate(familles, start=1):
            val = ligne[j] if j < len(ligne) else None
            cad[nom][fam] = float(val) if _est_nombre(val) else None  # '—' -> None
    return cad


def _parser_rendements(lignes: list[list[Any]]) -> dict[str, dict[str, float]]:
    h = _trouver_entete(lignes, ["Process"])
    rdt: dict[str, dict[str, float]] = {}
    for ligne in lignes[h + 1:]:
        if not ligne or ligne[0] is None:
            continue
        nom = str(ligne[0]).strip()
        if nom not in {"PK", "CRMA", "CRMB", "BAF", "SKP", "LGA", "LGB"}:
            continue
        rdt[nom] = {
            "rendement": float(ligne[1]),
            "chute": float(ligne[2]),
            "declasse": float(ligne[3]),
            "nonconf": float(ligne[4]),
        }
    return rdt


def _parser_couts(lignes: list[list[Any]]) -> dict[str, list[float]]:
    h = _trouver_entete(lignes, ["Process \\ Épaisseur (mm)", "Process \\ Epaisseur (mm)"])
    cles_attendues = {
        "PK", "CRMA", "CRMB", "BAF", "SKP",
        "LGA-HDG", "LGA-PPGI", "LGA-BACR", "LGB-HDG", "LGB-BACR",
    }
    couts: dict[str, list[float]] = {}
    for ligne in lignes[h + 1:]:
        if not ligne or ligne[0] is None:
            continue
        nom = str(ligne[0]).strip()
        if nom not in cles_attendues:
            continue
        couts[nom] = [float(v) for v in ligne[1:8]]
    return couts


def _parser_prix_hrc(lignes: list[list[Any]]) -> tuple[dict, dict]:
    h = _trouver_entete(lignes, ["Grade \\ Largeur"])
    largeurs = [float(c) for c in lignes[h][1:] if _est_nombre(c)]
    prix: dict[str, dict[float, float]] = {}
    for ligne in lignes[h + 1:]:
        if not ligne or ligne[0] is None:
            break  # fin du bloc prix
        nom = str(ligne[0]).strip()
        if not _est_nombre(ligne[1]):
            break
        prix[nom] = {largeurs[j]: float(ligne[j + 1]) for j in range(len(largeurs))}

    # bloc disponibilité
    hd = _trouver_entete(lignes, ["Grade"])
    dispo: dict[str, float] = {}
    for ligne in lignes[hd + 1:]:
        if not ligne or ligne[0] is None:
            continue
        nom = str(ligne[0]).strip()
        if nom in prix and _est_nombre(ligne[1]):
            dispo[nom] = float(ligne[1])
    return prix, dispo


def _parser_stocks_finis(lignes: list[list[Any]]) -> dict[str, dict[str, float]]:
    """Seul le bloc 'produits finis' est utilisé par le modèle essentiel."""
    h = _trouver_entete(lignes, ["Famille"])
    stocks: dict[str, dict[str, float]] = {}
    for ligne in lignes[h + 1:]:
        if not ligne or ligne[0] is None:
            continue
        nom = str(ligne[0]).strip()
        if not _est_nombre(ligne[1]):
            continue
        stocks[nom] = {
            "init": float(ligne[1]),
            "min": float(ligne[2]),
            "max": float(ligne[3]),
        }
    return stocks


def _parser_stocks_interprocess(lignes: list[list[Any]]) -> dict[str, dict[str, float]]:
    """Bloc 'Stocks interprocess (Full Hard)'. Clé = préfixe avant ' (' :
    FH-CRMA, FH-CRMB, BAF-out, SKP-out."""
    h = _trouver_entete(lignes, ["Point de stockage"])
    connus = {"FH-CRMA", "FH-CRMB", "BAF-out", "SKP-out"}
    stocks: dict[str, dict[str, float]] = {}
    for ligne in lignes[h + 1:]:
        if not ligne or ligne[0] is None:
            continue
        if not _est_nombre(ligne[1]):
            continue
        nom = str(ligne[0]).split("(")[0].strip()
        if nom not in connus:
            continue
        stocks[nom] = {
            "init": float(ligne[1]),
            "min": float(ligne[2]),
            "max": float(ligne[3]),
        }
    return stocks


def _parser_arrets(lignes: list[list[Any]]) -> dict[str, dict[int, int]]:
    h = _trouver_entete(lignes, ["Ligne"])
    arrets: dict[str, dict[int, int]] = {}
    for ligne in lignes[h + 1:]:
        if not ligne or ligne[0] is None:
            continue
        nom = str(ligne[0]).strip()
        if nom not in {"PK", "CRMA", "CRMB", "BAF", "SKP", "LGA", "LGB"}:
            continue
        arrets[nom] = {t: int(ligne[t]) for t in (1, 2, 3, 4)}
    return arrets


def _parser_parametres(lignes: list[list[Any]]) -> dict[str, float]:
    h = _trouver_entete(lignes, ["Paramètre", "Parametre"])
    params: dict[str, float] = {}
    for ligne in lignes[h + 1:]:
        if not ligne or ligne[0] is None:
            continue
        if _est_nombre(ligne[1]):
            params[str(ligne[0]).strip()] = float(ligne[1])
    return params


# ---------------------------------------------------------------------------
# Point d'entrée
# ---------------------------------------------------------------------------


def charger_donnees(chemin: str) -> Donnees:
    """Charge l'ensemble du classeur et renvoie un objet `Donnees`."""
    wb = openpyxl.load_workbook(chemin, data_only=True)

    d = Donnees()
    d.commandes = _parser_commandes(_lire_lignes(wb["Commandes"]))
    d.cadences = _parser_cadences(_lire_lignes(wb["Cadences"]))
    d.rendements = _parser_rendements(_lire_lignes(wb["Rendements"]))
    d.couts = _parser_couts(_lire_lignes(wb["Couts_Variables"]))
    d.prix_hrc, d.dispo_hrc = _parser_prix_hrc(_lire_lignes(wb["Prix_HRC"]))
    d.stocks_finis = _parser_stocks_finis(_lire_lignes(wb["Stocks_Initiaux"]))
    d.stocks_interprocess = _parser_stocks_interprocess(_lire_lignes(wb["Stocks_Initiaux"]))
    d.arrets = _parser_arrets(_lire_lignes(wb["Arrets_Planifies"]))
    d.params = _parser_parametres(_lire_lignes(wb["Parametres"]))
    return d


if __name__ == "__main__":  # diagnostic rapide
    import os

    ici = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
    d = charger_donnees(os.path.join(ici, "data", "Donnees_MaghrebSteel.xlsx"))
    print(f"{len(d.commandes)} commandes lues")
    print("Familles :", sorted({c['famille'] for c in d.commandes}))
    print("Dispo HRC :", d.dispo_hrc)
    print("Cadences PK :", d.cadences['PK'])
