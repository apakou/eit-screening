# Cadrage du projet

## Contexte

Le projet accompagne un mémoire de Master (Lomé Business School, option génie
logiciel) intitulé « Intégration de la Génération Augmentée par la Recherche
(RAG) dans les Systèmes d'Information pour l'aide à la décision : application à
la sélection des candidats du MEST AI Startup Program ».

L'auteur est un ancien de la première cohorte du programme : il connaît le
processus du côté candidat.

**Problématique.** Dans quelle mesure un système RAG peut-il proposer, pour
chaque candidature, un verdict de présélection justifié par des preuves tirées
du dossier, que les évaluateurs peuvent valider en confiance ?

**Hypothèses à tester.**

1. Les verdicts proposés sont, pour une large part, validés sans modification
   par les évaluateurs.
2. Les raisons affichées sont fidèles au dossier : chaque citation s'y trouve
   et appuie bien l'affirmation.
3. L'outil réduit le temps passé par dossier.

## Calendrier

Le mémoire est déposé après validation par le directeur de mémoire. Les
livrables lui sont envoyés en trois lots.

| Lot | Contenu | Envoi visé |
|---|---|---|
| 1 | Introduction et Partie I (théorie) | 29 novembre 2026 |
| 2 | Partie II (conception), réalignée sur le prototype réel | 6 décembre 2026 |
| 3 | Partie III (résultats), conclusion, pages liminaires | 13 décembre 2026 |

Le code doit donc produire ses premiers chiffres avant le 6 décembre.

## Décisions prises

- **Périmètre.** Revue des candidatures et présélection uniquement. Le système
  propose un verdict et ses raisons ; MEST décide.
- **Prototype réduit.** On construit le pipeline, une API et une interface à
  deux écrans. Le reste de la pile décrite dans le mémoire est présenté comme
  architecture cible.
- **Modèle de langage.** Modèle ouvert (famille Gemma ou Qwen) hébergé chez un
  fournisseur, derrière une API compatible OpenAI. Le fournisseur et les prix
  restent à choisir. Condition : seul du texte anonymisé lui est envoyé.
- **Données.** Par défaut, dossiers fictifs produits par `eit-generate`. De
  vrais dossiers pourront s'ajouter si MEST les fournit, sans changer le code.
- **Honnêteté du mémoire.** Le texte distingue ce qui est construit et mesuré de
  ce qui est seulement conçu.

## Prototype et architecture cible

| Brique | Dans le prototype | Architecture cible seulement |
|---|---|---|
| Import PDF, éligibilité, appariement, anonymisation | Oui | |
| Lecture des pièces jointes (Docling), transcription (faster-whisper) | Oui | |
| Embeddings bge-m3, Qdrant, re-ranking bge-reranker-v2-m3 | Oui | |
| Verdict par modèle ouvert, sortie JSON contrainte | Oui, modèle hébergé | Serveur vLLM sur GPU |
| API FastAPI, PostgreSQL | Oui | |
| Interface Next.js (tableau, preuves, validation) | Oui, deux écrans | |
| Docker Compose | Oui | Kubernetes |
| Keycloak, Celery et Redis, SeaweedFS, Langfuse, Prometheus | Non | Oui |

## Contradictions à faire trancher par MEST

Le formulaire réel de la cohorte 2026 et le texte du mémoire ne disent pas la
même chose. Tant que MEST n'a pas répondu, le code suit le formulaire 2026 et
garde ces valeurs paramétrables.

| Point | Formulaire 2026 | Mémoire |
|---|---|---|
| Test technique | TestGorilla, 70 minutes | ClassMarker |
| Âge | 21 à 30 ans | 21 à 35 ans |
| Citoyenneté | Afrique de l'Ouest | Afrique de l'Est ou de l'Ouest |
| Programme | Janvier à décembre 2026, dont 7 mois à Accra | 12 mois à Accra, engagements en 2027 |

## Ce qui manque encore

- **Guide d'évaluation de MEST.** Le mémoire cite une grille sur 40 points en
  quatre critères notés sur 10 (Resume & Technical Experience, Entrepreneurial
  Motivation & Vision, Communication & Clarity, Program Fit & Collaboration) et
  8 Concerns. Seuls trois noms de Concerns sont connus : « Assessment not
  found », « Assessment concerns », « Generic AI responses ». La liste complète
  et les repères de notation restent à obtenir.
- **Seuils de décision.** Rien ne dit à partir de quelle note un candidat est
  invité en entretien.
- **Format de l'export du test** (colonnes, format des dates), date limite
  réelle du test (hypothèse : 10 août 2025) et durée en dessous de laquelle un
  test est suspect (hypothèse : 20 minutes sur 70).
- **Date de calcul de l'âge** (hypothèse : 1er janvier 2026) et **liste des
  pays** retenue pour « Afrique de l'Ouest » (hypothèse : les 16 pays de l'ONU).
- **Accord écrit de MEST** pour l'envoi de texte anonymisé à un modèle hébergé.
- **Vérité terrain.** Aucun dossier ne porte aujourd'hui de note ni de décision
  d'évaluateur. Il faut faire noter les dossiers fictifs par deux évaluateurs ou
  anciens de MEST, ou obtenir des dossiers réels avec leurs décisions.

## Protocole d'évaluation prévu

- **Jeu de référence.** 40 dossiers, dont 40 % de cas à anomalie.
- **Qualité du RAG.** Mesures RAGAS : fidélité, pertinence de la réponse,
  précision et rappel du contexte.
- **Alignement.** Part des verdicts proposés que les évaluateurs valident sans
  les modifier. Le taux d'accord entre deux évaluateurs humains sert de plafond
  réaliste.
- **Détection.** Part des anomalies de `scenarios.csv` retrouvées, et fausses
  alertes.
- **Temps.** Durée de traitement par dossier, et temps passé par évaluateur avec
  et sans l'outil.
- **Comparaison.** Même modèle sans recherche documentaire (dossier entier dans
  le prompt, ou aucune preuve), pour mesurer l'apport du RAG.
- **Test utilisateur.** Deux évaluateurs, en plan croisé : l'un traite le lot A
  à la main et le lot B avec l'outil, l'autre l'inverse. Le protocole initial du
  mémoire faisait noter deux fois les mêmes dossiers, ce qui faussait la mesure
  du temps. Questionnaire SUS en fin de séance.

## Ce que le mémoire attend du code

Le chapitre 6 a besoin, pour chaque mesure ci-dessus, d'un chiffre et de la
commande qui le reproduit. Prévoir un export unique des résultats (CSV ou JSON)
avec la date, la version du code, le modèle utilisé et la graine.
