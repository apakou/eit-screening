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
  propose une décision et ses raisons ; MEST décide.
- **Guide d'évaluation 2027** (reçu le 22 novembre 2026). Il remplace le
  formulaire 2026 comme référence et tranche les contradictions ci-dessous. Il
  fixe aussi :
  - la **décision** : trois valeurs (`Interview Invitation`,
    `Interview Reject`, `Waitlist`) et un booléen distinct,
    `request_further_review` ; « Request Final Review » n'est plus un verdict ;
  - le **diplôme** : obtenu en 2028 ou après, la candidature est écartée ; en
    2027, elle est signalée pour examen du mois d'obtention ;
  - le **test** : ClassMarker, date limite le 20 juillet à 23 h 59 GMT,
    plateforme ouverte jusqu'au 22 juillet, toute soumission après le 20
    signalée ;
  - les **identifiants** de candidature : `EIT-2027-XXXXXX` ;
  - une **grille sur 40 points** dont il nomme les domaines.
  « Écarté » se traduit par une décision proposée `Interview Reject` ; le
  système ne décide toujours pas seul, l'évaluateur valide ou modifie.
- **Prototype réduit.** On construit le pipeline, une API et une interface à
  deux écrans. Le reste de la pile décrite dans le mémoire est présenté comme
  architecture cible.
- **Modèle de langage.** Modèle ouvert (famille Gemma ou Qwen) hébergé chez un
  fournisseur, derrière une API compatible OpenAI. Le fournisseur et les prix
  restent à choisir. Condition : seul du texte anonymisé lui est envoyé.
- **Données.** Par défaut, dossiers fictifs produits par `eit-generate`. De
  vrais dossiers pourront s'ajouter si MEST les fournit, sans changer le code.
- **Lieux masqués** (22 novembre 2026). Pays, villes, nationalités et langues
  locales sont masqués dans le texte envoyé au modèle, pour qu'il ne puisse pas
  déduire la nationalité. Les noms d'établissements et d'employeurs sont gardés
  pour le critère CV ; ils laissent parfois deviner le pays, et ce biais résiduel
  sera mesuré par un test contrefactuel.
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

## Contradictions tranchées par le guide 2027

Le formulaire réel de la cohorte 2026 et le texte du mémoire ne disaient pas la
même chose. Le guide d'évaluation 2027 tranche ; le code le suit et garde ces
valeurs paramétrables.

| Point | Formulaire 2026 | Mémoire | Guide 2027 (retenu) |
|---|---|---|---|
| Test technique | TestGorilla, 70 minutes | ClassMarker | ClassMarker, date limite 20 juillet 23 h 59 GMT |
| Âge | 21 à 30 ans | 21 à 35 ans | 21 à 35 ans au 1er janvier 2027, cas limites signalés |
| Citoyenneté | Afrique de l'Ouest | Afrique de l'Est ou de l'Ouest | Afrique de l'Ouest ou de l'Est |
| Programme | Janvier à décembre 2026, dont 7 mois à Accra | 12 mois à Accra, engagements en 2027 | Dates non données |

Hypothèses prises pour appliquer le guide, à confirmer avec MEST :

- **Âge.** Le guide signale sans l'écarter « un candidat de 20 ans qui aura
  21 ans au démarrage » et « un de 35 ans qui pourrait atteindre 36 ans pendant
  le programme ». Il ne donne ni le démarrage ni la fin du programme. Le code
  signale (constat « à vérifier ») : 20 ans au dépôt et 21 ans au 1er janvier
  2027 ; 20 ans au 1er janvier mais 21 ans au démarrage, si une date de
  démarrage est configurée ; 35 ans au 1er janvier, comparé à la fin du
  programme si elle est configurée, sinon tous (`eligibility.toml`,
  `program_start`, `program_end`).
- **Afrique de l'Est.** Liste de l'ONU (18 pays), comme pour l'Afrique de
  l'Ouest. Elle diffère de la Communauté d'Afrique de l'Est (EAC) : la RDC est
  dans l'EAC mais pas dans la liste ; Éthiopie, Zambie, Zimbabwe, Malawi,
  Mozambique, Madagascar, Maurice, Seychelles, Comores, Djibouti et Érythrée
  sont dans la liste mais pas dans l'EAC.
- **Année du test.** 2026 (20 juillet 2026), pour une promotion qui commence
  en 2027.
- **Fuseau horaire de l'export ClassMarker.** GMT par défaut.
- **Durée du test ClassMarker.** Non donnée ; 70 minutes gardées (durée
  TestGorilla 2026), seuil de durée anormale à 20 minutes.

## Ce qui manque encore

- **Domaines de la grille du guide 2027.** Le guide note sur 40 points des
  domaines qu'il nomme, mais leurs noms (et une éventuelle pondération) n'ont
  pas encore été transmis. `grille.toml` garde les quatre critères notés sur 10
  du mémoire (Resume & Technical Experience, Entrepreneurial Motivation &
  Vision, Communication & Clarity, Program Fit & Collaboration), marqués comme
  provisoires ; aucune pondération ne doit être inventée.
- **Concerns.** Le mémoire en annonce 8 ; seuls trois noms sont connus :
  « Assessment not found », « Assessment concerns », « Generic AI responses ».
- **Seuils de décision.** Rien ne dit à partir de quelle note un candidat est
  invité en entretien (hypothèses : 28 et 20 sur 40, `verdict.toml`).
- **Format de l'export ClassMarker** (colonnes, format et fuseau des dates).
- **Accord écrit de MEST** pour l'envoi de texte anonymisé à un modèle hébergé.
- **Accès aux vidéos.** L'export ne contient que des liens protégés. Le module
  attend les vidéos à côté du PDF (`personal_statement.mp4`,
  `assessment_reflection.mp4`) ; reste à savoir comment MEST peut les fournir.
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
