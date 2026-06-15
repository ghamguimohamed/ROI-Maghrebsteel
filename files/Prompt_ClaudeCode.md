# Prompt à coller dans Claude Code

> **Mode d'emploi.** Crée un dossier de projet, places-y le fichier `Donnees_MaghrebSteel.xlsx` dans `data/`, ouvre Claude Code à la racine, puis colle tout ce qui suit (à partir de « Tu es… »). Le prompt est auto-suffisant : il décrit le modèle assez précisément pour retomber sur les mêmes chiffres, et il fixe des critères d'acceptation que le code doit vérifier lui-même.

---

Tu es un ingénieur en recherche opérationnelle. Construis un projet Python propre et reproductible qui résout un problème d'optimisation linéaire de planification industrielle (simulateur Capacité–Commande pour le laminage à froid de Maghreb Steel), avec PuLP + CBC.

## Structure attendue

```
src/        parse_data.py, model.py, analyse.py, sensibilite.py
app/        app.py            (interface Streamlit)
data/       Donnees_MaghrebSteel.xlsx   (déjà fourni)
outputs/    (généré : plan de marche Excel, etc.)
tests/      test_validation.py
main.py     point d'entrée : lit, construit, résout, exporte, valide
README.md
requirements.txt
```

`requirements.txt` : pulp, pandas, numpy, openpyxl, streamlit, matplotlib. README : installation (`pip install -r requirements.txt`) et lancement (`python main.py`, `streamlit run app/app.py`). Docstrings sur les fonctions non triviales, commentaires sur les choix de modélisation. Le tout doit tourner en moins de 5 minutes.

## Données (9 onglets dans le xlsx)

- **Commandes** : 66 lignes (ID, Client, Famille, Grade, Épaisseur mm, Largeur mm, Tonnage T, Prix vente MAD/T, Semaine livraison 1-4, Priorité). En-tête en 3e ligne de l'onglet ; filtre les lignes dont l'ID commence par « CMD ».
- **Cadences** : cadence T/jour par ligne × famille (en-tête réelle en 3e ligne). « — » = ligne non utilisable pour cette famille.
- **Rendements** : par process, rendement / chute / déclassé / non-conforme.
- **Couts_Variables** : coût transfo MAD/T par process × 7 tranches d'épaisseur. Clés : PK, CRMA, CRMB, BAF, SKP, LGA-HDG, LGA-PPGI, LGA-BACR, LGB-HDG, LGB-BACR (en-tête tranches en 3e ligne).
- **Prix_HRC** : prix MAD/T par grade × largeur, puis bloc « disponibilité » (T) par grade.
- **Stocks_Initiaux** : trois blocs — stock PK par grade, stocks interprocess, stocks produits finis par famille (init / min / max). On n'utilise que le bloc **produits finis** dans le modèle essentiel.
- **Arrets_Planifies** : jours d'arrêt par ligne × semaine.
- **Parametres** : prix chutes 1800 ; coeff déclassé 0.5 / non-conforme 0.2 ; prix zinc 18000, conso zinc HDG et PPGI 0.025 ; prix peinture 12000, conso peinture PPGI 0.01 ; pénalités retard 500/200/0 ; stockage interprocess 25, fini 40.

Écris un parser robuste qui détecte dynamiquement la ligne d'en-tête de chaque onglet (ne suppose pas qu'elle est en ligne 1 : il y a souvent une ligne de titre et une ligne vide avant).

## Modèle (Niveau 2, LP continu) — à implémenter exactement

**Périmètre.** On modélise les 66 commandes **sauf le Quarto** (exclu du laminage à froid). On **inclut le HRC DEC** comme famille minimale (décapage PK seul).

**Routes admissibles par famille** (séquence de process, de PK à la finition) :
- CRC : `PK → CRMB → BAF → SKP` (voie unique).
- HRC DEC : `PK` (décapage seul).
- HDG : 4 routes = `PK → {CRMA|CRMB} → {LGA|LGB}`.
- PPGI : 2 routes = `PK → {CRMA|CRMB} → LGA` (LGA uniquement).
- BACR : 5 routes = voie A `PK → CRMB → BAF → LGB` + voie B `PK → {CRMA|CRMB} → {LGA|LGB}`.

Pour le coût de galva, choisis la bonne clé selon (ligne, famille) : `LGA-HDG`, `LGB-HDG`, `LGA-PPGI`, `LGA-BACR`, `LGB-BACR`. Les autres process utilisent leur clé simple.

**Tranche d'épaisseur** (bornes `[bas, haut[`) : <0.3 → idx0 ; [0.3,0.4[ → 1 ; [0.4,0.5[ → 2 ; [0.5,0.7[ → 3 ; [0.7,1.0[ → 4 ; [1.0,1.5[ → 5 ; ≥1.5 → 6.

**Coefficients par route** `r = (ℓ₁,…,ℓ_k)` (ℓ_k = finition) :
- rendement de chaîne `Π_r = Πᵢ ρ(ℓᵢ)`.
- coefficient de débit du process ℓᵢ (tonnes en sortie de ℓᵢ par tonne finie) : `θ(r,ℓᵢ) = 1 / Π_{j>i} ρ(ℓⱼ)` (vaut 1 pour la finition).
- HRC par tonne finie : `1/Π_r`.
- coût transfo unitaire : `Γ = Σᵢ cout[clé(ℓᵢ)][tranche] · θ(r,ℓᵢ)`.
- coût HRC unitaire : `Λ = prix_HRC[grade][largeur] / Π_r`.
- valorisation chutes unitaire : `Ξ = 1800 · Σᵢ chute(ℓᵢ) · (θ(r,ℓᵢ)/ρ(ℓᵢ))`.
- zinc : `+450 MAD/T` si famille ∈ {HDG, PPGI}, sinon 0. **Pas** de peinture séparée (déjà dans le coût LGA-PPGI). **Pas** de zinc pour BACR. Déclassé/non-conforme **non** valorisés.

**Variables.**
- `p[c, r, τ] ≥ 0` : tonnage fini de la commande c via la route r, produit en semaine τ, pour τ ≤ semaine de livraison de c (**production en avance autorisée**, jamais après l'échéance).
- `x[c] ∈ [0, demande_c]` : tonnage livré (à l'échéance t_c).
- `S[f, t] ∈ [min_f, max_f]` pour t = 1..4 ; `S[f,0] = init_f` (constante).

**Contraintes.**
1. Liaison : `x[c] = Σ_{r,τ} p[c,r,τ]`.
2. Capacité en **jours-machine**, pour chaque (ligne ℓ, semaine t) :
   `Σ_{c,r : ℓ∈r} (θ(r,ℓ)/cadence[ℓ][famille_c]) · p[c,r,t] ≤ 7 − arret[ℓ][t]`.
3. HRC par grade (pool sur tout l'horizon) :
   `Σ_{c : grade=g} Σ_{r,τ} (1/Π_r) · p[c,r,τ] ≤ dispo_HRC[g]`.
4. Bilan stock fini, pour chaque (famille f, semaine t) :
   `S[f,t] = S[f,t−1] + Σ_{c∈f} Σ_r p[c,r,t] − Σ_{c∈f, t_c=t} x[c]`.

**Objectif (maximiser)** :
`Σ_c prix_c · x[c] + Σ_{c,r,τ} (Ξ − Γ − Λ − zinc) · p[c,r,τ]`.

Pas de stocks interprocess dans le modèle essentiel (flux qui traverse dans la semaine).

## Sorties à produire (`analyse.py` + export Excel dans `outputs/`)

Un classeur `plan_de_marche.xlsx` avec plusieurs feuilles :
1. **Synthèse** : statut, marge totale, taux de service global, nb commandes pleines/partielles/refusées, marge moyenne/T.
2. **Plan de marche** : tonnage produit (output) par ligne × semaine.
3. **Utilisation** : taux d'occupation (jours utilisés / disponibles) par ligne × semaine + horizon.
4. **Commandes** : pour chaque commande, demande, livré, % servi, statut.
5. **Refus** : commandes non pleinement servies + grade + indication de la contrainte bloquante (grade HRC saturé ? famille passant par LGA ?).
6. **Shadow_prices** : duals des contraintes saturées (capacités en MAD/jour-machine, HRC en MAD/T), triés.
7. **Marge_famille** : par famille — livré, demande, service, marge, marge/T.

Récupère les *shadow prices* via `constraint.pi` (CBC) ; pour fiabiliser, ajoute une fonction qui les **vérifie empiriquement** en reperturbant la dispo HRC de chaque grade (±quelques tonnes) et en relançant, puis compare.

## Validation indépendante (`tests/test_validation.py`, question E15)

Un script **séparé du solveur** qui, à partir des valeurs `x` et `p` de la solution, recalcule à la main et vérifie : (a) capacité de chaque ligne/semaine ≤ jours dispo ; (b) HRC par grade ≤ dispo ; (c) bilans de stock cohérents et bornes min/max respectées ; (d) `x[c] = Σ p` et `x[c] ≤ demande` ; (e) la marge recalculée depuis x,p égale l'objectif du solveur. Tolérance numérique ~1e-4. Le test échoue si une contrainte est violée.

## Sensibilité (`sensibilite.py`, questions E20–E22 + B8)

- **E20** : relancer avec prix HRC ×1.10 sur tous les grades ; reporter la nouvelle marge et la variation %.
- **E21** : relancer avec 2 jours d'arrêt LGB supplémentaires en semaine 2 ; reporter l'impact marge et le tonnage livré.
- **E22** : ajouter une commande `300 T HDG DC01, ép. 0.5 mm, largeur 1140, semaine 1, prix 11500 MAD/T` ; dire si elle est acceptée et le delta de marge (coût d'opportunité).
- **B8** : faire varier la dispo DC01 de −50 % à +50 %, tracer la marge optimale (matplotlib) et repérer le point de rupture de pente.

## Interface Streamlit (`app/app.py`, question B6)

Une appli pour un utilisateur non technique : un tableau éditable du carnet de commandes (ajout / modification / suppression d'une commande), un bouton « Relancer l'optimisation », et l'affichage des résultats — marge, taux de service, plan de marche, utilisation des lignes, liste des refus avec leur raison, et les *shadow prices*. Prévoir aussi des curseurs pour la sensibilité (prix HRC, dispo d'un grade, jours d'arrêt d'une ligne) qui relancent le calcul. Soigne la lisibilité (titres clairs, tableaux et un ou deux graphiques) ; pas de jargon dans l'UI.

## Critères d'acceptation (le code doit retomber dessus)

Sur le jeu de données fourni, le modèle essentiel doit donner :
- **statut Optimal**, **marge ≈ 34 966 832 MAD**, **taux de service ≈ 81,2 %** (≈ 13 772 / 16 958 T) ;
- **47 commandes pleines, 4 partielles, 14 refusées** ;
- **LGA saturée à 100 % en S1, S2, S3** ; **CRMA utilisée à 0 %** ; LGB ≈ 37 % sur l'horizon ;
- plafonds HRC **saturés sur S320, DX51, DX52, DC01**, **DD13 non saturé** ;
- *shadow prices* HRC ≈ S320 1889, DX51 1788, DX52 1396, DC01 385 MAD/T ; LGA ≈ 10 500 MAD/jour-machine en S1–S2 ;
- marge/T par famille ≈ PPGI 3918 (100 % servi), BACR 2418, HDG 2230, CRC 1908 (51 %), HRC DEC 498 ;
- **E20** ≈ −25,8 % ; **E21** delta ≈ 0 ; **E22** acceptée 300/300, delta ≈ +707 000 MAD.

Si un écart notable apparaît, c'est un bug de modélisation : vérifie d'abord les conventions de rendement (θ et Π), la formule de capacité en jours-machine, et le périmètre (Quarto exclu, HRC DEC inclus, production en avance autorisée).
