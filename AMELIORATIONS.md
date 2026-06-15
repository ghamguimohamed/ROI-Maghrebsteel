# Pistes d'amélioration (pour aller au-delà du barème)

Ce document liste ce qui est **déjà en place** pour la qualité, puis des
**extensions** classées par rapport valeur / effort, afin de viser la note
maximale et d'anticiper les questions du jury.

## Déjà en place (points forts à mettre en avant)

- **Optimum global garanti** (LP continu, PuLP + CBC) — pas une heuristique.
- **Parser robuste** : détection dynamique des en-têtes (résiste aux lignes de
  titre / lignes vides, change d'onglet sans casser).
- **Validation indépendante** du solveur (recalcul manuel de toutes les
  contraintes) → preuve d'absence de bug de modélisation.
- **Vérification empirique des prix duals** (reperturbation ±5 T) → écart 0.
- **Interface Streamlit** sans jargon : carnet éditable, curseurs, plan de marche.
- **Export Excel** avec page de garde (logo, équipe) et 7 feuilles d'analyse.
- **Reproductibilité** : `requirements.txt`, `main.py` unique, < 5 min.
- **Livraisons en retard avec pénalité (IMPLÉMENTÉ).** Option `retards_autorises`
  du modèle : une commande peut être produite et livrée après son échéance,
  pénalisée à 500/200/0 MAD/T/semaine selon sa priorité (paramètres du xlsx).
  - Sur le cas de base : gain ≈ +32 000 MAD seulement → **preuve que le goulot
    est la matière première HRC (pool sur l'horizon), pas l'ordonnancement.**
  - Sous une crise de capacité (ex. LGA bridée en S1) : gain de **+1 à +2 M MAD**
    en différant la production vers S4 — la flexibilité de délai devient décisive.
  - Accessible via la case à cocher de l'app et `sensibilite.comparer_retards`.
- **Coût de stockage des produits finis (IMPLÉMENTÉ).** Option `cout_stockage`
  du modèle : le stock fini détenu en fin de semaine est facturé à 40 MAD/T/sem
  (paramètre du xlsx). La production en avance n'est plus gratuite.
  - Effet : la marge passe de 34,97 à 34,74 M MAD (−229 612 MAD de stockage) et
    le stock fini détenu chute de **7 177 à 5 740 T·sem** → le plan tend vers le
    **juste-à-temps**.
  - Accessible via la case à cocher de l'app et `sensibilite.comparer_stockage`.
- **Niveau 3 — stocks interprocess (Full Hard) (IMPLÉMENTÉ).** Module
  `model_n3.py` : la route est découpée en segments séparés par les tampons
  (sortie CRMA/CRMB/BAF) ; chaque segment peut tourner une semaine différente
  (laminer tôt, galvaniser plus tard), borné par la capacité des tampons.
  - Relaxation du Niveau 2 (`marge_N3 ≥ marge_N2`, propriété testée) ; gain
    base ≈ +24 000 MAD, plus élevé sous panne d'un laminoir amont (les tampons
    amortissent l'arrêt). Charge LGA lissée vers S4 au lieu de saturer S1–S3.
  - Sélecteur « Niveau 3 » dans l'app + validateur indépendant `valider_n3`.

## Extensions à fort impact / faible effort

1. **Graphiques dans l'app** : courbe B8 intégrée, et un « waterfall » de la
   marge par famille pour la soutenance.

## Extensions à fort impact / effort moyen

2. **Lots minimaux (MILP).** Imposer un tonnage mini par campagne (variables
   binaires) évite les micro-séries irréalistes. Coût : passage en nombres
   entiers, temps de calcul plus long, perte des duals exacts.

3. **Multi-période glissant / réoptimisation.** Rejouer le plan chaque semaine
   avec les réalisations observées (rolling horizon).

4. **Stocks PK par grade.** Ajouter le 3ᵉ bloc de stock (bobines décapées par
   grade) pour un découplage PK → laminage, en complément du Niveau 3.

## Extensions « bonus » (différenciantes)

7. **Optimisation robuste / scénarios de prix HRC.** Au lieu d'un seul prix,
   optimiser sur plusieurs scénarios pondérés (le test E20 montre l'exposition).

8. **Frontière de Pareto marge / taux de service.** Tracer le compromis quand on
   force un service minimum par contrainte — utile pour la direction commerciale.

9. **Export PDF automatique** du rapport de marche (one-click pour le management).

## Limites assumées (à dire au jury, ça rassure)

- Modèle déterministe (demande et capacités connues).
- Tonnages continus (pas de tailles de bobine discrètes).
- Flux interprocess instantanés au Niveau 2 (levé au Niveau 3 via tampons).
- Niveau 3 : tampons traités comme un pool de tonnes physiques agrégées, le
  stock initial étant une réserve fixe (bobines d'autres spécifications) qui
  satisfait automatiquement le stock de sécurité minimal.
