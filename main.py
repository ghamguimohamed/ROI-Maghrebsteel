"""Point d'entrée : lit les données, construit et résout le modèle, exporte le
plan de marche, vérifie les shadow prices et valide la solution.

Usage :  python main.py
"""

from __future__ import annotations

import os
import sys

ICI = os.path.dirname(os.path.abspath(__file__))
sys.path.insert(0, os.path.join(ICI, "src"))

import analyse  # noqa: E402
from model import construire_et_resoudre  # noqa: E402
from parse_data import charger_donnees  # noqa: E402

CHEMIN_XLSX = os.path.join(ICI, "data", "Donnees_MaghrebSteel.xlsx")
DOSSIER_OUT = os.path.join(ICI, "outputs")
PLAN = os.path.join(DOSSIER_OUT, "plan_de_marche.xlsx")


def main() -> None:
    os.makedirs(DOSSIER_OUT, exist_ok=True)

    print("1) Lecture des données …")
    d = charger_donnees(CHEMIN_XLSX)
    print(f"   {len(d.commandes)} commandes lues "
          f"({len([c for c in d.commandes if c['famille'] != 'Quarto'])} modélisées).")

    print("2) Construction + résolution (PuLP / CBC) …")
    m = construire_et_resoudre(d)
    print(f"   Statut : {m.statut} ; marge = {m.marge:,.0f} MAD")

    print("3) Synthèse :")
    print(analyse.synthese(m).to_string(index=False))

    print("\n4) Shadow prices (contraintes saturées) :")
    print(analyse.shadow_prices(m).to_string(index=False))

    print("\n5) Vérification empirique des duals HRC :")
    print(analyse.verifier_shadow_hrc(m).to_string(index=False))

    print(f"\n6) Export du plan de marche -> {PLAN}")
    analyse.exporter_excel(m, PLAN)

    print("\n7) Validation indépendante de la solution :")
    sys.path.insert(0, os.path.join(ICI, "tests"))
    from test_validation import valider
    erreurs = valider(CHEMIN_XLSX)
    if erreurs:
        print("   ÉCHEC :")
        for e in erreurs:
            print("     -", e)
        sys.exit(1)
    print("   OK — toutes les contraintes (a)-(e) sont respectées.")

    print("\nTerminé.")


if __name__ == "__main__":
    main()
