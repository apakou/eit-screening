# eit-screening

Prototype d'aide à la présélection des candidatures du MEST AI Startup Program.

Cette version contient onze briques :

- **l'import** : lit un dossier exporté en PDF depuis SurveyMonkey Apply et le
  transforme en données structurées ;
- **le générateur de dossiers fictifs** : fabrique des dossiers au même format,
  avec des anomalies placées volontairement, pour tester le système sans
  données personnelles réelles ;
- **les contrôles d'éligibilité** : âge, nationalité et réponses aux questions
  d'éligibilité, sous forme de constats soumis à l'évaluateur ;
- **l'appariement avec le test** : rattache chaque ligne de l'export de la
  plateforme de test au bon dossier et relève les tests introuvables, en retard
  ou trop rapides ;
- **les pièces jointes et les vidéos** : relit les CV et certificats (OCR
  compris) et transcrit les vidéos, avec l'horodatage de chaque segment ;
- **l'anonymisation** : produit, pour chaque dossier, le texte destiné au
  modèle de langage sans données personnelles, sous un pseudonyme aléatoire ;
- **l'indexation** : découpe les dossiers anonymisés en passages et les range
  dans Qdrant avec leurs embeddings bge-m3 ;
- **la recherche** : recherche dense et lexicale dans le dossier d'un candidat,
  fusion RRF et re-ranking, mesurée sur un jeu de questions à réponse connue ;
- **le verdict** : note, raison et citation vérifiée par critère, verdict
  proposé par une règle explicite ;
- **l'API et l'interface** : tableau des candidatures, dossier avec preuves,
  validation ou modification par l'évaluateur ;
- **l'évaluation** : un export unique des mesures.

## Installation

Python 3.11 ou plus récent, FFmpeg installé sur la machine.

```bash
pip install -e ".[dev]" --extra-index-url https://download.pytorch.org/whl/cpu
```

L'index supplémentaire installe PyTorch (requis par Docling) en version
processeur. Sans lui, pip installe la version CUDA, qui pèse plusieurs
gigaoctets. Les modèles de Docling, de RapidOCR et de Whisper sont téléchargés
au premier usage puis gardés en cache.

## Importer un dossier

```bash
eit-import chemin/vers/application.pdf -o dossier.json
```

Le fichier JSON contient l'identité, les réponses d'éligibilité, la formation,
les expériences, les cinq réponses libres, les fichiers envoyés, les références
et le texte des pièces jointes. Les pièces jointes sans texte (certificat
scanné, par exemple) sont marquées `needs_ocr`.

Depuis Python :

```python
from eit_screening.ingestion.smapply_pdf import parse_application

dossier = parse_application("application.pdf")
print(dossier.personal.country_of_citizenship, len(dossier.essays))
```

L'import ne dépend pas du texte des questions pour repérer les réponses : il
s'appuie sur la mise en page de l'export (réponse dans un rectangle gris,
libellé au-dessus). Si MEST modifie son formulaire, toutes les questions restent
lues et conservées dans `items` ; celles que le module ne sait pas ranger sont
signalées dans `warnings`.

## Contrôler l'éligibilité

```bash
eit-eligibility data/fictifs/dossiers --scenarios data/fictifs/scenarios.csv -o data/resultats/eligibilite.json
```

Pour chaque dossier, le module calcule l'âge à la date de référence, vérifie
que la nationalité appartient à la zone, contrôle l'année d'obtention du diplôme
et relève chaque réponse « No » aux questions d'éligibilité. Les règles suivent
le guide d'évaluation 2027 (21 à 35 ans au 1er janvier 2027, Afrique de l'Ouest
ou de l'Est, diplôme avant 2028). Il produit des **constats**, jamais un rejet : chaque
constat a un code, une gravité (`alerte` ou `à vérifier`), un message et les
réponses du dossier qui le montrent, citées telles quelles.

| Code | Gravité | Cas |
|---|---|---|
| `age_out_of_range` | alerte | Âge hors tranche |
| `age_borderline` | à vérifier | Âge limite signalé par le guide 2027 (20 ans au dépôt, 35 ans) |
| `age_unknown` | à vérifier | Date de naissance absente ou illisible |
| `graduation_after_cutoff` | alerte | Diplôme obtenu en 2028 ou après |
| `graduation_review` | à vérifier | Diplôme obtenu en 2027 : mois à examiner |
| `citizenship_outside_region` | alerte, ou à vérifier si double nationalité | Nationalité hors zone |
| `citizenship_unknown` | à vérifier | Nationalité absente ou illisible |
| `eligibility_answer_no` | alerte | Réponse « No » à une question d'éligibilité |
| `eligibility_answer_unreadable` | à vérifier | Réponse absente ou illisible |
| `eligibility_answers_missing` | à vérifier | Aucune réponse d'éligibilité dans le dossier |

Les paramètres sont dans `src/eit_screening/screening/eligibility.toml` (valeurs
du guide 2027, hypothèses marquées). Pour essayer d'autres règles (celles du
formulaire 2026 par exemple), copier ce fichier, le modifier et le passer avec
`--config`. L'option `--scenarios` compare les
constats aux anomalies placées dans les dossiers fictifs.

## Rattacher l'export du test

```bash
eit-assessment data/fictifs/dossiers data/fictifs/assessment_results.csv --scenarios data/fictifs/scenarios.csv -o data/resultats/appariement.json
```

Chaque ligne de l'export est rattachée à un dossier par l'adresse e-mail, puis
par le nom et le prénom inversés, puis par un nom ressemblant (sans casse ni
accents, seuil réglable). Une ligne qui pourrait appartenir à deux dossiers
n'est rattachée à aucun : le module refuse de deviner.

| Code | Gravité | Cas |
|---|---|---|
| `assessment_not_found` | alerte | Aucune ligne de l'export pour ce dossier |
| `assessment_late` | alerte | Test terminé après la date limite (jour compris) |
| `assessment_too_fast` | à vérifier | Durée sous le seuil ; le score est cité |
| `assessment_match_ambiguous` | à vérifier | Une ligne pourrait être la sienne comme celle d'un autre |
| `assessment_multiple_results` | à vérifier | Plusieurs lignes pour ce dossier |
| `assessment_date_unreadable`, `assessment_duration_unreadable` | à vérifier | Cellule absente ou illisible |

Les paramètres sont dans `src/eit_screening/screening/assessment.toml` : noms
des colonnes et format de l'export (supposés), date limite, durée minimale,
seuil de ressemblance des noms. Quand MEST fournira un vrai export, seul ce
fichier devrait changer.

## Lire les pièces jointes et transcrire les vidéos

```bash
eit-media data/fictifs/dossiers -o data/resultats/extraction.json
```

Pour chaque dossier, le module écrit `extraction.json` à côté du PDF :

- **pièces jointes** : les pages ajoutées après le formulaire (CV, certificats)
  sont relues par Docling. Les pages scannées passent par l'OCR (RapidOCR par
  défaut, Tesseract en option). Chaque page garde son numéro et l'origine de
  son texte (`docling` ou `ocr`) ;
- **vidéos** : FFmpeg extrait l'audio, faster-whisper le transcrit sur le
  processeur. Chaque segment garde son début, sa fin et les valeurs de confiance
  de Whisper.

L'export ne contient que des liens protégés vers les vidéos : le module ne les
télécharge pas. Il cherche la vidéo à côté du PDF, sous le nom
`personal_statement.mp4` ou `assessment_reflection.mp4` (autres extensions
admises dans `media.toml`). À défaut, il lit la transcription écrite
(`personal_statement.txt`), comme pour les dossiers fictifs ; ses segments
n'ont alors pas d'horodatage.

`eit-anonymize` lit `extraction.json` s'il existe. Le texte issu de l'OCR ou de
la reconnaissance vocale y passe par une couche de plus : un mot qui ressemble
à un nom du dossier (« Mensa » pour « Mensah ») est masqué, car un nom mal lu
échappe à la comparaison exacte.

Les paramètres sont dans `src/eit_screening/media/media.toml`.

## Anonymiser les dossiers

```bash
eit-anonymize data/fictifs/dossiers -o data/anonymises --table ~/.local/share/eit-screening/pseudonymes-fictifs-2027.json
```

Pour chaque dossier, le module rassemble les textes utiles à l'évaluation
(réponses libres, transcriptions, pièces jointes, formation, expériences, noms
de fichiers) et y masque les données personnelles en quatre couches :

1. les identifiants que le dossier donne lui-même, pour le candidat et les tiers
   (parrain, références) : nom, chaque mot du nom, e-mails, téléphones, liens ;
2. toute autre adresse e-mail, numéro de téléphone ou lien ;
3. les pays, villes, nationalités et langues locales, pour que le modèle ne
   puisse pas déduire la nationalité ;
4. les noms de personnes et les lieux inconnus du dossier, repérés par Presidio
   et spaCy.

Le candidat devient `[CANDIDAT]`, les tiers `[PERSONNE_1]`, `[PERSONNE_2]`…, les
lieux `[PAYS]`, `[VILLE]`, `[NATIONALITÉ]`, `[LANGUE]` ou `[LIEU]`. Les noms
d'établissements et d'employeurs déclarés dans le dossier sont gardés tels quels
(« University of Ghana ») : ils renseignent le parcours, mais laissent parfois
deviner le pays. Le genre, l'âge et la nationalité sont gardés comme
métadonnées, à côté du texte.
Chaque dossier est écrit sous un pseudonyme aléatoire (`C-1A2B3C4D.json`), sans
son numéro de candidature. La table de correspondance est écrite à part, avec
des droits de lecture réservés à l'utilisateur ; le module refuse de la placer
dans le dossier de sortie. Relancer l'anonymisation garde les mêmes pseudonymes.

Les paramètres sont dans `src/eit_screening/privacy/anonymize.toml`. Le modèle
spaCy `en_core_web_md` (licence MIT, environ 55 Mo) est installé avec le projet.

## Indexer les passages

```bash
docker compose up -d qdrant
eit-index data/anonymises --qdrant-url http://127.0.0.1:6333 -o data/resultats/indexation.json
```

Le module lit les dossiers anonymisés et les découpe en passages de 120 mots au
plus. Chaque passage garde sa provenance : section, question, page, horodatage
et position exacte dans le texte anonymisé. Les segments horodatés d'une vidéo
sont regroupés. Chaque passage reçoit un vecteur dense et des poids lexicaux
calculés par bge-m3 (environ 2,3 Go, téléchargé au premier usage), puis il est
rangé dans Qdrant sous le pseudonyme du candidat. La commande vérifie ensuite que
chaque passage relu dans Qdrant pointe exactement vers son texte.

Qdrant tourne dans Docker (`docker-compose.yml`, port ouvert sur la machine
locale seulement, données dans `data/qdrant`). Le conteneur redémarre avec la
machine ; `docker compose down` l'arrête. Les fichiers de `data/qdrant`
appartiennent à root (créés par le conteneur) : pour les effacer, utiliser
`sudo` ou `docker run --rm -v "$PWD/data:/d" busybox rm -rf /d/qdrant`. Sans `--qdrant-url`, la base est
locale, sans serveur (`data/qdrant-local`). Les paramètres sont dans
`src/eit_screening/search/search.toml`.

## Rechercher dans un dossier

```bash
eit-search C-1A2B3C4D --qdrant-url http://127.0.0.1:6333
eit-search-eval --qdrant-url http://127.0.0.1:6333 -o data/resultats/recherche.json
```

`eit-search` pose, dans le dossier d'un candidat, une requête par critère de la
grille (`src/eit_screening/grille.toml`) et affiche les passages trouvés avec
leur provenance. Chaque requête passe par une recherche dense et une recherche
lexicale limitées au pseudonyme du candidat, fusionnées par Qdrant (RRF), puis
par le re-ranking bge-reranker-v2-m3 (environ 2,3 Go, téléchargé au premier
usage).

`eit-search-eval` mesure quatre chaînes (dense, lexicale, hybride, hybride avec
re-ranking) sur un jeu de questions dont les passages pertinents se déduisent de
la structure du dossier (`search/questions.toml`). Sur la cohorte de référence,
la recherche dense seule fait le mieux ; le re-ranking dégrade le résultat
(voir `docs/feuille-de-route.md`, étape 6).

## Proposer une décision

```bash
eit-verdict data/anonymises --qdrant-url http://127.0.0.1:6333 --table ~/.local/share/eit-screening/pseudonymes-fictifs-2027.json
```

Pour chaque dossier anonymisé, le module cherche les passages de chaque critère
de la grille, puis demande au modèle de langage, pour chaque critère, une note,
une raison et une citation recopiée mot pour mot. Le modèle dit aussi si les
réponses libres sont génériques. La sortie est contrainte par un schéma JSON
et vérifiée ; une réponse non conforme est redemandée.

Le code vérifie ensuite chaque citation : si elle n'est pas mot pour mot dans le
dossier, elle est marquée « introuvable » et ne compte pas comme preuve. La
décision proposée vient d'une règle explicite (`verdict/verdict.toml`) qui
combine les notes, les constats d'éligibilité et de test (étapes 1 et 2) et les
citations. Guide 2027 : trois décisions (`Interview Invitation`,
`Interview Reject`, `Waitlist`) et un booléen distinct, `request_further_review`.
Un constat qui écarte selon le guide fait proposer `Interview Reject` ; un
constat signalé, un Concern ou une citation introuvable demande la revue
complémentaire. Chaque appel est journalisé (`<pseudonyme>.appel.json` : messages
envoyés, passages, réponses brutes).

Le client parle le protocole compatible OpenAI. Par défaut, il vise Ollama sur
la machine locale (`llama3.2`, substitut du modèle hébergé prévu par le
cadrage) : aucun texte ne quitte la machine. Pour un fournisseur hébergé,
changer `base_url` et `model` et mettre la clé dans la variable
`EIT_LLM_API_KEY`. Seul du texte anonymisé est envoyé : ni genre, ni âge, ni
nationalité, ni numéro de candidature.

`--dossier-entier` lance la variante de comparaison sans recherche (tout le
dossier dans le prompt).

## API et interface

```bash
docker compose up -d postgres
eit-api-load --verdicts data/verdicts --anonymises data/anonymises
eit-api                                   # http://127.0.0.1:8000/docs
cd ui && pnpm install && pnpm dev --port 3100   # http://localhost:3100
```

L'API (FastAPI, PostgreSQL) sert la liste des candidatures, le détail d'un
dossier, et enregistre la décision de l'évaluateur : valider la décision proposée,
ou le modifier avec un commentaire obligatoire. Chaque décision garde
l'évaluateur, la date, la décision et la demande de revue proposées et retenues ; le journal
n'est jamais réécrit. Pas d'authentification dans le prototype : l'évaluateur
saisit son nom.

L'interface (Next.js, TypeScript, Tailwind CSS, shadcn/ui) a deux écrans :

- **tableau des candidatures**, triable (total, alertes, Concerns, âge) et
  filtrable (verdict, statut, genre) ;
- **dossier** : verdict, règle appliquée, constats et raisons à gauche ; dossier
  anonymisé à droite, citations vérifiées surlignées ; boutons pour valider ou
  modifier, et historique des décisions.

## Évaluer

```bash
eit-evaluate --table ~/.local/share/eit-screening/pseudonymes-fictifs-2027.json
```

Rassemble les mesures de toutes les étapes dans `data/resultats/evaluation.json`
(date, version du code, modèles, graine) et confronte les constats aux anomalies
de `scenarios.csv`. Les mesures qui demandent des évaluateurs (alignement,
accord entre évaluateurs, temps, SUS) sont listées comme non mesurées.

## Générer des dossiers fictifs

```bash
eit-generate -n 40 --graine 2026 -o data/fictifs
```

La même graine redonne toujours la même cohorte.

| Fichier | Contenu |
|---|---|
| `dossiers/<numéro>/application.pdf` | Dossier au format de l'export |
| `dossiers/<numéro>/reference.json` | Données exactes ayant servi à fabriquer le PDF |
| `dossiers/<numéro>/personal_statement.txt` | Transcription de la vidéo de présentation |
| `dossiers/<numéro>/assessment_reflection.txt` | Transcription de la vidéo de réflexion |
| `dossiers/<numéro>/pieces_jointes.json` | Texte attendu de chaque certificat, pour mesurer l'OCR |
| `assessment_results.csv` | Export de la plateforme de test |
| `scenarios.csv` | Niveau et anomalie de chaque dossier, adresse de sa ligne dans l'export du test (`email_test`) |

### Niveaux et anomalies

Chaque dossier a un niveau (`fort`, `moyen`, `faible`) qui règle la qualité des
réponses, du parcours et du score au test. Quarante pour cent des dossiers
portent en plus une anomalie :

| Code | Anomalie |
|---|---|
| `assessment_name_swapped` | Nom et prénom inversés dans l'export du test, avec une autre adresse e-mail |
| `assessment_not_found` | Aucun résultat de test |
| `assessment_late` | Test rendu après la date limite (21 ou 22 juillet 2026) |
| `assessment_too_fast` | Test terminé en un temps anormalement court avec un score élevé |
| `generic_ai_answers` | Réponses libres génériques, sans aucun fait personnel |
| `age_out_of_range` | Date de naissance hors tranche, malgré la réponse « Yes » |
| `age_borderline` | 20 ans au dépôt et 21 ans au 1er janvier 2027, ou 35 ans au 1er janvier 2027 |
| `citizenship_outside_region` | Nationalité hors Afrique de l'Ouest et de l'Est, malgré la réponse « Yes » |
| `graduation_after_cutoff` | Diplôme obtenu en 2028 |
| `graduation_review` | Diplôme obtenu en 2027 |
| `missing_resume` | CV non fourni |
| `poor_audio` | Vidéo de présentation presque inaudible |

`scenarios.csv` dit ce que le système doit retrouver. Il ne remplace pas la note
d'un évaluateur : il décrit seulement ce qui a été construit.

## Tests

```bash
pytest
```

Les tests génèrent 40 dossiers, les relisent avec le module d'import et
vérifient que chaque champ relu est identique à la référence.

Les tests de l'étape 4 chargent de vrais modèles : Docling sur un dossier, et
Whisper « small » (environ 460 Mo, téléchargé au premier lancement) sur une
courte vidéo dont la voix est synthétisée par FFmpeg. Ils demandent un FFmpeg
compilé avec le filtre `flite` (c'est le cas du paquet Ubuntu). Les tests de
l'étape 5 chargent bge-m3, ceux de l'étape 6 le re-ranking. Durée totale :
environ 3 minutes, 4,4 Go de mémoire au plus. Ne rien lancer de lourd à côté.

Contrôle de fuite sur toute la cohorte anonymisée (code indépendant du module
d'anonymisation) :

```bash
eit-leak-check data/fictifs/dossiers data/anonymises --table ~/.local/share/eit-screening/pseudonymes-fictifs-2027.json
```

L'import a aussi été vérifié sur un dossier réel de la cohorte 2026 : 73
questions lues, aucun avertissement. Ce dossier n'est pas dans le dépôt.

## Hypothèses à confirmer avec MEST

- **Export du test.** Les colonnes de `assessment_results.csv` sont une
  supposition ; le format réel de l'export ClassMarker reste à obtenir.
- **Date limite du test.** Guide 2027 : 20 juillet à 23 h 59 GMT ; l'année
  (2026) et le fuseau des dates de l'export (GMT) sont des hypothèses
  (`assessment.toml`).
- **Règles du guide 2027 non précisées** (dates du programme, liste des pays
  d'Afrique de l'Est, domaines de la grille) : voir `docs/cadrage.md`.
- **Fichier manquant.** L'export réel d'une question de fichier sans réponse
  n'a pas été observé ; le générateur écrit « (No response) ».
- **Questions conditionnelles.** Les champs de parrainage et « If Other » ne
  sont écrits que lorsqu'ils s'appliquent.
- **Pièces jointes.** L'export ne dit pas à quel fichier correspond chaque
  page ajoutée ; l'import les garde dans l'ordre, sans les rattacher.

## Limites des dossiers fictifs

- Les réponses libres viennent d'une banque de textes (`content.py`). Sur 40
  dossiers, un même texte peut revenir jusqu'à quatre fois. La banque doit être
  enrichie avant de faire noter les dossiers par des évaluateurs.
- Les vidéos ne sont pas fabriquées : les fichiers `.txt` tiennent lieu de
  sortie de la reconnaissance vocale.

## Confidentialité

- Tous les noms, adresses et numéros des dossiers fictifs sont inventés
  (domaines `example.*`, numéros au préfixe `000`).
- Le dossier `data/` n'est jamais versionné. Les dossiers réels ne doivent pas
  quitter la machine de la personne autorisée à les traiter.

## Suite du projet

- `CLAUDE.md` : règles du projet, lues par Claude Code à l'ouverture.
- `docs/cadrage.md` : périmètre, décisions prises, points à confirmer avec MEST.
- `docs/feuille-de-route.md` : étapes à venir et critères d'acceptation.
