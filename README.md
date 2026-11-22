# eit-screening

Prototype d'aide à la présélection des candidatures du MEST AI Startup Program.

Cette version contient six briques :

- **l'import** : lit un dossier exporté en PDF depuis SurveyMonkey Apply et le
  transforme en données structurées ;
- **le générateur de dossiers fictifs** : fabrique des dossiers au même format,
  avec des anomalies placées volontairement, pour tester le système sans
  données personnelles réelles.
- **les contrôles d'éligibilité** : âge, nationalité et réponses aux questions
  d'éligibilité, sous forme de constats soumis à l'évaluateur ;
- **l'appariement avec le test** : rattache chaque ligne de l'export de la
  plateforme de test au bon dossier et relève les tests introuvables, en retard
  ou trop rapides ;
- **les pièces jointes et les vidéos** : relit les CV et certificats (OCR
  compris) et transcrit les vidéos, avec l'horodatage de chaque segment ;
- **l'anonymisation** : produit, pour chaque dossier, le texte destiné au
  modèle de langage sans données personnelles, sous un pseudonyme aléatoire.

Les étapes suivantes (indexation, recherche, notation, interface) viendront
s'appuyer sur ces briques.

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
que la nationalité appartient à la zone et relève chaque réponse « No » aux
questions d'éligibilité. Il produit des **constats**, jamais un rejet : chaque
constat a un code, une gravité (`alerte` ou `à vérifier`), un message et les
réponses du dossier qui le montrent, citées telles quelles.

| Code | Gravité | Cas |
|---|---|---|
| `age_out_of_range` | alerte | Âge hors tranche |
| `age_unknown` | à vérifier | Date de naissance absente ou illisible |
| `citizenship_outside_region` | alerte, ou à vérifier si double nationalité | Nationalité hors zone |
| `citizenship_unknown` | à vérifier | Nationalité absente ou illisible |
| `eligibility_answer_no` | alerte | Réponse « No » à une question d'éligibilité |
| `eligibility_answer_unreadable` | à vérifier | Réponse absente ou illisible |
| `eligibility_answers_missing` | à vérifier | Aucune réponse d'éligibilité dans le dossier |

Les paramètres sont dans `src/eit_screening/screening/eligibility.toml` (valeurs
du formulaire 2026). Pour essayer les valeurs du mémoire, copier ce fichier, le
modifier et le passer avec `--config`. L'option `--scenarios` compare les
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
eit-anonymize data/fictifs/dossiers -o data/anonymises --table ~/.local/share/eit-screening/pseudonymes-fictifs.json
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
| `assessment_late` | Test passé après la date limite |
| `assessment_too_fast` | Test terminé en un temps anormalement court avec un score élevé |
| `generic_ai_answers` | Réponses libres génériques, sans aucun fait personnel |
| `age_out_of_range` | Date de naissance hors tranche, malgré la réponse « Yes » |
| `citizenship_outside_region` | Nationalité hors Afrique de l'Ouest, malgré la réponse « Yes » |
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
compilé avec le filtre `flite` (c'est le cas du paquet Ubuntu). Durée totale :
environ 2 minutes.

Contrôle de fuite sur toute la cohorte anonymisée (code indépendant du module
d'anonymisation) :

```bash
eit-leak-check data/fictifs/dossiers data/anonymises --table ~/.local/share/eit-screening/pseudonymes-fictifs.json
```

L'import a aussi été vérifié sur un dossier réel de la cohorte 2026 : 73
questions lues, aucun avertissement. Ce dossier n'est pas dans le dépôt.

## Hypothèses à confirmer avec MEST

- **Export du test.** Les colonnes de `assessment_results.csv` sont une
  supposition ; le format réel de la plateforme de test reste à obtenir.
- **Date limite du test.** Fixée au 10 août 2025 dans `profiles.py` et dans
  `assessment.toml`.
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
