================================================================================
  SCRIPT DE PRÉSENTATION — SIMULATEUR CAPACITÉ–COMMANDE MAGHREB STEEL
  UM6P · EMINES — School of Industrial Management
  Équipe : EL HMID Aicha · GHAMGUI Mohammed Amine · KEITA Josué ·
           LOUTFI Youness · BENYOUSSEF Mouad
================================================================================

Durée cible : 12–15 minutes + questions.
Conseil : 1 personne par grande partie, transitions annoncées. Parlez « métier »
d'abord, « maths » ensuite. Ne lisez pas le code à l'écran.

--------------------------------------------------------------------------------
0. OUVERTURE  (≈ 30 s)
--------------------------------------------------------------------------------
« Bonjour. Nous présentons un simulateur d'aide à la décision pour la
planification du laminage à froid de Maghreb Steel. La question posée par
l'usine est simple à énoncer, difficile à résoudre à la main : avec une
capacité machine limitée, un stock d'acier brut limité et 66 commandes à
échéances différentes, quelles commandes produire, par quel chemin de
fabrication, et quelle semaine, pour maximiser la marge ?

Notre réponse est un modèle d'optimisation linéaire, résolu en quelques
secondes, qui livre un plan de marche complet et explique chaque arbitrage. »

--------------------------------------------------------------------------------
1. LE PROBLÈME MÉTIER  (≈ 2 min)
--------------------------------------------------------------------------------
• La chaîne va du décapage (PK) à la finition (galvanisation LGA/LGB, ou
  recuit BAF + skin-pass SKP pour le CRC).
• Chaque famille de produit a des ROUTES possibles :
    - CRC      : PK → CRMB → BAF → SKP
    - HRC DEC  : PK seul (juste décapé)
    - HDG      : PK → (CRMA ou CRMB) → (LGA ou LGB)   → 4 routes
    - PPGI     : PK → (CRMA ou CRMB) → LGA            → 2 routes
    - BACR     : voie BAF (PK→CRMB→BAF→LGB) ou voie directe → 5 routes
• Trois ressources rares se disputent : les JOURS-MACHINE de chaque ligne,
  le STOCK D'ACIER BRUT (HRC) par grade, et la capacité de STOCKAGE des
  produits finis.
• On exclut le Quarto (filière séparée) et on autorise la production EN AVANCE
  (jamais en retard, dans le modèle essentiel).

Transition : « Pour décider, il faut chiffrer la marge de chaque décision. »

--------------------------------------------------------------------------------
2. LE MODÈLE MATHÉMATIQUE  (≈ 3 min)
--------------------------------------------------------------------------------
(a) VARIABLES de décision :
    - p[c, r, τ] : tonnes de la commande c produites via la route r, semaine τ ;
    - x[c]       : tonnes livrées au client (≤ sa demande) ;
    - S[f, t]    : stock de produits finis de la famille f en fin de semaine.

(b) LES COEFFICIENTS DE RENDEMENT — le cœur technique :
    « Chaque process perd de la matière : pour 1 tonne finie, il faut plus d'1
    tonne en amont. »
    - Π_r = produit des rendements de la route → rendement de chaîne ;
    - θ(r,ℓ) = tonnes en sortie du process ℓ par tonne finie = 1/(rendements aval) ;
    - HRC consommé par tonne finie = 1/Π_r ;
    - capacité en JOURS-MACHINE : θ(r,ℓ)/cadence × production.

(c) L'OBJECTIF : maximiser
      Σ prix·livré + Σ (chutes valorisées − coût transfo − coût HRC − zinc)·produit
    Zinc +450 MAD/T pour HDG et PPGI ; peinture PPGI déjà dans la ligne LGA-PPGI.

CONTRAINTES : 1) on ne livre que ce qu'on produit ; 2) chaque ligne ≤ 7 jours −
arrêts, chaque semaine ; 3) HRC consommé ≤ stock par grade ; 4) bilan de stock
fini avec min de sécurité et max d'entrepôt.

Phrase clé : « Programme linéaire continu, résolu avec PuLP + CBC. Optimum
global garanti, pas une heuristique. »

--------------------------------------------------------------------------------
3. DÉMONSTRATION LIVE  (≈ 3 min)
--------------------------------------------------------------------------------
Lancer :  streamlit run app/app.py

  1. En-tête (logo EMINES, équipe) puis les 4 indicateurs : marge ≈ 34,97 M MAD,
     service 81,2 %, 47 commandes pleines, 14 refusées.
  2. Onglet « Utilisation des lignes » : « La LGA est saturée à 100 % les trois
     premières semaines — notre goulot. La CRMA reste à 0 %. »
  3. Onglet « Refus » : on explique POURQUOI (HRC saturé ou LGA pleine).
  4. Onglet « Prix duals » : « Une tonne de HRC S320 en plus rapporterait
     1 889 MAD ; un jour-machine LGA, 10 490 MAD. Feuille de route d'investissement. »
  5. Manipuler un curseur (dispo DC01) ou ajouter une commande → le plan se
     recalcule sous leurs yeux.

Message : « Un planificateur non technicien pilote toute l'optimisation. »

--------------------------------------------------------------------------------
4. RÉSULTATS & ANALYSES DEMANDÉES  (≈ 3 min)
--------------------------------------------------------------------------------
• Marge optimale : 34 966 832 MAD ; service global 81,2 % (13 772 / 16 958 T).
• Par famille (marge/tonne) : PPGI 3 918 (100 % servi, le plus rentable),
  BACR 2 418, HDG 2 230, CRC 1 908 (51 % servi car peu rentable), HRC DEC 498.
  → « Le modèle privilégie spontanément les produits à forte valeur ajoutée. »

SENSIBILITÉ (E20–E22, B8) :
  - E20 : HRC +10 % → marge −25,8 %. L'usine est très exposée au prix de l'acier.
  - E21 : +2 jours d'arrêt LGB en S2 → impact ≈ 0. La LGB n'est pas le goulot →
          décision : planifier la maintenance LGB ici.
  - E22 : nouvelle commande 300 T HDG DC01 à 11 500 MAD/T → ACCEPTÉE en totalité,
          +707 000 MAD. C'est son coût d'opportunité : on sait dire oui.
  - B8 : dispo DC01 de −50 % à +50 % → la marge croît puis sa pente casse autour
         du niveau actuel : au-delà, le DC01 n'est plus le facteur limitant.

EXTENSION — LIVRAISONS EN RETARD (case à cocher dans l'app) :
  « Possibilité de livrer en retard avec pénalité (500/200/0 MAD/T/sem). Résultat
  instructif : sur le cas de base, gain minuscule (+32 000 MAD) → le goulot est
  la MATIÈRE (HRC), pas le calendrier ; mais sous une crise de capacité (LGA
  bridée), différer la production vers S4 rapporte +1 à +2 M MAD. »

EXTENSION — COÛT DE STOCKAGE DES PRODUITS FINIS (case à cocher) :
  « En facturant le stockage (40 MAD/T/sem), la marge passe de 34,97 à 34,74 M
  MAD, mais le stock détenu chute de 7 177 à 5 740 T·sem : le modèle bascule vers
  le JUSTE-À-TEMPS. »

NIVEAU 3 — STOCKS INTERPROCESS / FULL HARD (sélecteur dans l'app) :
  « Notre extension la plus aboutie lève l'hypothèse "tout traverse dans la
  semaine". On découpe chaque route en segments séparés par les tampons Full
  Hard (sortie CRMA/CRMB/BAF) : on peut laminer en S1 et galvaniser en S3, en
  stockant l'intermédiaire — dans la limite des tampons. Mathématiquement c'est
  une RELAXATION du Niveau 2, donc la marge ne peut qu'augmenter (propriété
  testée). Le gain est modeste (+24 000 MAD) car le vrai goulot reste la galva
  et le HRC ; mais on VOIT la charge LGA se lisser vers S4 au lieu de saturer
  S1-S3, et sous une panne d'un laminoir amont les tampons amortissent l'arrêt. »

--------------------------------------------------------------------------------
5. FIABILITÉ / VALIDATION  (≈ 1 min)
--------------------------------------------------------------------------------
« Un résultat d'optimisation ne vaut que s'il est vérifié. Trois garde-fous : »
  - Un validateur INDÉPENDANT du solveur (tests/test_validation.py) recalcule à
    la main toutes les contraintes : capacités, HRC, stocks, tampons, marge.
  - Les prix duals sont CONFIRMÉS empiriquement (reperturbation ±5 T → écart 0).
  - 5 tests automatisés (base, retards, stockage, Niveau 3, propriété de
    relaxation) ; tous passent.

--------------------------------------------------------------------------------
6. CONCLUSION  (≈ 30 s)
--------------------------------------------------------------------------------
« En résumé : un modèle d'optimisation linéaire complet, validé, et habillé
d'une interface utilisable par l'usine. Diagnostic transversal : sur ce carnet,
le facteur limitant est la MATIÈRE (HRC) puis la GALVA — ni le délai, ni le
stockage, ni les tampons amont ne changent fondamentalement la donne. C'est le
message industriel que nous remettons à l'usine. Merci, place aux questions. »

================================================================================
  ANTICIPER LES QUESTIONS DU JURY
================================================================================
Q. Pourquoi un modèle CONTINU et pas en nombres entiers ?
   → Les tonnages sont continus ; le LP donne l'optimum global et les prix duals.
     Un raffinement entier (lots mini) est une extension naturelle.

Q. Pourquoi la CRMA reste à 0 % ?
   → À spec égale la CRMB est moins chère et de meilleur rendement sur nos
     routes ; la CRMA est une réserve utile seulement si la CRMB sature.

Q. Que signifie un dual de 10 490 MAD/jour-machine sur la LGA ?
   → Un jour de production LGA en plus (heures sup, week-end) rapporterait
     jusqu'à ~10 490 MAD — tant que la LGA reste le goulot.

Q. Pourquoi le CRC n'est servi qu'à 51 % ?
   → Sa marge/tonne (1 908) est la plus faible des produits laminés ; quand la
     capacité manque, le modèle sacrifie le CRC au profit du PPGI/HDG/BACR.

Q. Comment garantissez-vous l'absence de bug de modélisation ?
   → Validateur indépendant + vérification empirique des duals + résultats
     stables et cohérents métier (goulots et arbitrages ont un sens).

Q. Le Niveau 3 ne devrait-il pas beaucoup améliorer la marge ?
   → Non, et c'est un résultat en soi : les tampons amont ne lèvent pas le vrai
     goulot (galva + HRC). Leur valeur apparaît surtout en cas de panne amont.
================================================================================
