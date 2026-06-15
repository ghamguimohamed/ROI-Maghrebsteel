"""Interface Streamlit — Simulateur Capacité–Commande Maghreb Steel (question B6).

Pensée pour un utilisateur non technique :
  * carnet de commandes éditable (ajout / modification / suppression) ;
  * curseurs de sensibilité (prix HRC, dispo d'un grade, arrêts d'une ligne) ;
  * bouton « Relancer l'optimisation » ;
  * résultats lisibles : marge, taux de service, plan de marche, utilisation
    des lignes, refus avec leur raison, et prix duals (valeurs cachées).

Lancement :  streamlit run app/app.py
"""

from __future__ import annotations

import copy
import os
import sys

import pandas as pd
import streamlit as st

ICI = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, os.path.join(ICI, "src"))

import analyse  # noqa: E402
import equipe  # noqa: E402
from model import construire_et_resoudre  # noqa: E402
from model_n3 import construire_et_resoudre_n3  # noqa: E402
from parse_data import charger_donnees  # noqa: E402

CHEMIN_XLSX = os.path.join(ICI, "data", "Donnees_MaghrebSteel.xlsx")

st.set_page_config(page_title="EMINES · Simulateur Maghreb Steel",
                   layout="wide", page_icon="🏭")

# Fond blanc garanti (au-delà du thème config.toml)
st.markdown(
    """
    <style>
      .stApp { background-color: #FFFFFF; }
      [data-testid="stHeader"] { background: #FFFFFF; }
      .bloc-equipe { color:#3F3F41; font-size:0.9rem; }
      .bandeau { border-bottom:3px solid #E8512E; margin-bottom:0.6rem; }
    </style>
    """,
    unsafe_allow_html=True,
)


# ---------------------------------------------------------------------------
# Données de base (mises en cache)
# ---------------------------------------------------------------------------


@st.cache_data
def _donnees_base():
    return charger_donnees(CHEMIN_XLSX)


def _commandes_df(d) -> pd.DataFrame:
    return pd.DataFrame(d.commandes)[
        ["id", "client", "famille", "grade", "epaisseur", "largeur",
         "tonnage", "prix", "semaine", "priorite"]
    ]


# ---------------------------------------------------------------------------
# En-tête
# ---------------------------------------------------------------------------

col_logo, col_titre = st.columns([1, 2])
with col_logo:
    if os.path.exists(equipe.LOGO_PNG):
        st.image(equipe.LOGO_PNG, width="stretch")
with col_titre:
    st.markdown(f"<div class='bandeau'></div>", unsafe_allow_html=True)
    st.title(equipe.TITRE_PROJET)
    st.caption(equipe.SOUS_TITRE)
    st.markdown(
        "<div class='bloc-equipe'><b>Équipe&nbsp;:</b> "
        + " · ".join(equipe.EQUIPE) + "</div>",
        unsafe_allow_html=True,
    )

st.divider()

base = _donnees_base()

if "commandes" not in st.session_state:
    st.session_state.commandes = _commandes_df(base)

# ---------------------------------------------------------------------------
# Barre latérale — sensibilité
# ---------------------------------------------------------------------------

with st.sidebar:
    if os.path.exists(equipe.LOGO_PNG):
        st.image(equipe.LOGO_PNG, width="stretch")
    st.header("Hypothèses")

    niveau = st.radio(
        "Modèle",
        ["Niveau 2 (essentiel)", "Niveau 3 (stocks interprocess)"],
        help="Le Niveau 3 autorise le découplage laminage / galvanisation via "
             "des tampons Full Hard : on peut laminer tôt et galvaniser plus "
             "tard, dans la limite de la capacité des tampons.")

    facteur_hrc = st.slider("Prix de l'acier brut (HRC)", 0.8, 1.3, 1.0, 0.05,
                            help="1.0 = prix actuel. Curseur = multiplicateur.")

    grade_sel = st.selectbox("Stock d'acier brut à ajuster",
                             list(base.dispo_hrc.keys()))
    fac_dispo = st.slider(f"Disponibilité {grade_sel}", 0.5, 1.5, 1.0, 0.05)

    ligne_sel = st.selectbox("Ligne à perturber",
                             ["PK", "CRMA", "CRMB", "BAF", "SKP", "LGA", "LGB"])
    sem_sel = st.selectbox("Semaine", [1, 2, 3, 4])
    jours_arret = st.slider("Jours d'arrêt ajoutés", 0, 5, 0)

    st.divider()
    retards = st.checkbox(
        "Autoriser les livraisons en retard (avec pénalité)",
        value=False,
        help="Une commande peut être livrée après son échéance moyennant une "
             "pénalité (500/200/0 MAD/T/semaine selon la priorité). Utile en "
             "cas de manque de capacité.")
    cout_stock = st.checkbox(
        "Facturer le stockage des produits finis",
        value=False,
        help="Compte le coût de stockage (40 MAD/T/semaine) du stock fini "
             "détenu : la production en avance n'est plus gratuite, le plan "
             "tend vers le juste-à-temps.")

    st.divider()
    lancer = st.button("🔄 Relancer l'optimisation", type="primary",
                       width="stretch")

# ---------------------------------------------------------------------------
# Carnet de commandes éditable
# ---------------------------------------------------------------------------

st.subheader("Carnet de commandes")
st.caption("Modifiez, ajoutez ou supprimez des lignes, puis relancez le calcul.")

edited = st.data_editor(
    st.session_state.commandes,
    num_rows="dynamic",
    width="stretch",
    column_config={
        "tonnage": st.column_config.NumberColumn("Tonnage (T)"),
        "prix": st.column_config.NumberColumn("Prix (MAD/T)"),
        "semaine": st.column_config.NumberColumn("Semaine", min_value=1, max_value=4),
    },
    key="editeur",
)
st.session_state.commandes = edited


# ---------------------------------------------------------------------------
# Optimisation
# ---------------------------------------------------------------------------


def _construire_donnees():
    d = copy.deepcopy(base)
    # carnet édité
    cmds = []
    for _, row in st.session_state.commandes.iterrows():
        if pd.isna(row["id"]) or str(row["id"]).strip() == "":
            continue
        cmds.append({
            "id": str(row["id"]).strip(),
            "client": row.get("client", ""),
            "famille": str(row["famille"]).strip(),
            "grade": str(row["grade"]).strip(),
            "epaisseur": float(row["epaisseur"]),
            "largeur": float(row["largeur"]),
            "tonnage": float(row["tonnage"]),
            "prix": float(row["prix"]),
            "semaine": int(row["semaine"]),
            "priorite": str(row.get("priorite", "Normale")).strip(),
        })
    d.commandes = cmds
    # sensibilité
    for g in d.prix_hrc:
        for w in d.prix_hrc[g]:
            d.prix_hrc[g][w] *= facteur_hrc
    d.dispo_hrc[grade_sel] *= fac_dispo
    d.arrets[ligne_sel][sem_sel] = min(7, d.arrets[ligne_sel][sem_sel] + jours_arret)
    return d


@st.cache_data(show_spinner="Optimisation en cours…")
def _resoudre(_signature, retards_flag, stock_flag, niveau_flag):
    d = _construire_donnees()
    solveur = construire_et_resoudre_n3 if niveau_flag == "n3" else construire_et_resoudre
    m = solveur(d, retards_autorises=retards_flag, cout_stockage=stock_flag)
    return {
        "statut": m.statut,
        "retards": retards_flag,
        "synthese": analyse.synthese(m),
        "plan": analyse.plan_de_marche(m),
        "utilisation": analyse.utilisation(m),
        "commandes": analyse.commandes(m),
        "refus": analyse.refus(m),
        "shadow": analyse.shadow_prices(m),
        "famille": analyse.marge_famille(m),
        "retards_detail": analyse.retards_detail(m),
    }


niveau_flag = "n3" if niveau.startswith("Niveau 3") else "n2"

# signature pour invalider le cache quand une hypothèse change
sig = (facteur_hrc, grade_sel, fac_dispo, ligne_sel, sem_sel, jours_arret,
       retards, cout_stock, niveau_flag, st.session_state.commandes.to_json())

# _resoudre est mis en cache (clé = signature) : on recalcule à chaque
# changement d'hypothèse, mais sans coût si rien n'a bougé. Le bouton
# « Relancer » force simplement un nouveau passage.
_ = lancer  # le clic suffit à déclencher un rerun Streamlit
res = _resoudre(sig, retards, cout_stock, niveau_flag)

# ---------------------------------------------------------------------------
# Résultats
# ---------------------------------------------------------------------------

st.subheader("Résultats")

syn = {r["Indicateur"]: r["Valeur"] for _, r in res["synthese"].iterrows()}
c1, c2, c3, c4 = st.columns(4)
c1.metric("Marge totale", f"{syn['Marge totale (MAD)']:,.0f} MAD")
c2.metric("Taux de service", f"{syn['Taux de service global (%)']:.1f} %")
c3.metric("Commandes pleines", int(syn["Commandes pleines"]))
c4.metric("Commandes refusées", int(syn["Commandes refusées"]))

noms_onglets = ["Plan de marche", "Utilisation des lignes",
                "Marge par famille", "Refus", "Prix duals", "Commandes"]
if res.get("retards"):
    noms_onglets.append("Retards")
onglets = st.tabs(noms_onglets)

with onglets[0]:
    st.caption("Tonnage produit (sortie) par ligne et par semaine.")
    plan = res["plan"].set_index("Ligne")
    st.bar_chart(plan[[c for c in plan.columns if c.startswith("S")]])
    st.dataframe(res["plan"], width="stretch", hide_index=True)

with onglets[1]:
    st.caption("Taux d'occupation des lignes (100 % = saturée).")
    util = res["utilisation"].set_index("Ligne")
    st.bar_chart(util[[c for c in util.columns if c.startswith("S")]])
    st.dataframe(res["utilisation"], width="stretch", hide_index=True)

with onglets[2]:
    st.dataframe(res["famille"], width="stretch", hide_index=True)

with onglets[3]:
    if res["refus"].empty:
        st.success("Toutes les commandes sont pleinement servies.")
    else:
        st.dataframe(res["refus"], width="stretch", hide_index=True)

with onglets[4]:
    st.caption("Valeur d'une unité supplémentaire de capacité ou de matière "
               "(MAD par jour-machine, ou par tonne d'acier brut).")
    if res["shadow"].empty:
        st.info("Aucune contrainte saturée.")
    else:
        st.dataframe(res["shadow"], width="stretch", hide_index=True)

with onglets[5]:
    st.dataframe(res["commandes"], width="stretch", hide_index=True)

if res.get("retards"):
    with onglets[6]:
        st.caption("Commandes livrées après leur échéance et pénalité associée.")
        det = res["retards_detail"]
        if det.empty:
            st.success("Aucune livraison en retard : tout est servi à l'heure.")
        else:
            st.dataframe(det, width="stretch", hide_index=True)

# ---------------------------------------------------------------------------
# Pied de page
# ---------------------------------------------------------------------------

st.divider()
st.markdown(
    f"<div style='text-align:center;color:#6b7280;font-size:0.82rem'>"
    f"{equipe.ETABLISSEMENT}<br>"
    f"<b>Équipe :</b> {' · '.join(equipe.EQUIPE)}</div>",
    unsafe_allow_html=True,
)
