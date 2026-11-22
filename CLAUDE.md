# eit-screening

Prototype d'aide à la présélection des candidatures du MEST AI Startup Program.
Il est développé pour un mémoire de Master en génie logiciel (Lomé Business
School) : le code doit produire des résultats mesurés, repris dans le mémoire.

## Ce que fait le produit

Pour chaque candidature, le système propose un **verdict de présélection** et
les **raisons** qui l'appuient. Un évaluateur de MEST valide ou modifie ce
verdict. **Le système ne décide jamais seul**, même pour un candidat hors
critères : il propose, l'humain tranche, et les deux décisions sont conservées.

- Verdicts possibles : `Interview Invitation`, `Interview Reject`, `Waitlist`,
  `Request Final Review`.
- Raisons : pour chaque critère de la grille, une phrase et la citation exacte
  du dossier qui l'appuie.
- Alertes : contrôles d'éligibilité et anomalies (« Concerns »).
- Hors périmètre : les entretiens et l'admission finale.

## État du code

| Module | État |
|---|---|
| `src/eit_screening/models.py` | Fait. Modèle `Application` partagé par tout le projet |
| `src/eit_screening/ingestion/smapply_pdf.py` | Fait. Export PDF SurveyMonkey Apply vers `Application` |
| `src/eit_screening/synthetic/` | Fait. Dossiers fictifs avec anomalies connues d'avance |
| `src/eit_screening/screening/eligibility.py` | Fait. Constats d'éligibilité, paramètres dans `eligibility.toml` |
| `src/eit_screening/screening/assessment_match.py` | Fait. Appariement avec l'export du test, paramètres dans `assessment.toml` |
| Anonymisation | À faire ensuite |
| Indexation, recherche, verdict, API, interface, évaluation | À faire ensuite |

Le détail des étapes et leurs critères d'acceptation sont dans
`docs/feuille-de-route.md`. Les décisions déjà prises et les points à confirmer
avec MEST sont dans `docs/cadrage.md`. Lire ces deux fichiers avant de commencer
une nouvelle étape.

## Commandes

```bash
pip install -e ".[dev]"                             # installation
pytest                                              # tests (environ 45 s)
eit-generate -n 40 --graine 2026 -o data/fictifs    # cohorte fictive de référence
eit-import data/fictifs/dossiers/0000001007/application.pdf -o dossier.json
eit-eligibility data/fictifs/dossiers --scenarios data/fictifs/scenarios.csv -o data/resultats/eligibilite.json
eit-assessment data/fictifs/dossiers data/fictifs/assessment_results.csv --scenarios data/fictifs/scenarios.csv -o data/resultats/appariement.json
```

## Règles sur les données

- Ne jamais versionner `data/` ni aucun dossier de candidature, réel ou fictif.
- Les dossiers réels restent sur la machine de la personne autorisée. Ne pas les
  copier dans le dépôt, dans un test, dans un message de commit ou dans un
  exemple de documentation.
- Seul du texte **anonymisé** peut partir vers un modèle de langage hébergé.
  Tout le reste (lecture des PDF, transcription, embeddings, recherche) tourne
  en local.
- Le genre, l'âge et la nationalité servent aux contrôles d'éligibilité et aux
  filtres, jamais au texte envoyé au modèle de langage.
- Le pseudonyme d'un candidat est un identifiant aléatoire. La table de
  correspondance est stockée à part ; ne jamais dériver le pseudonyme du numéro
  de candidature.

## Règles sur les résultats

- Ne jamais inventer, arrondir favorablement ni compléter un chiffre
  d'évaluation. Un résultat du mémoire doit pouvoir être reproduit par une
  commande du dépôt.
- `data/fictifs/scenarios.csv` dit ce que le système doit retrouver. Il ne tient
  pas lieu de note d'évaluateur.
- Chaque citation produite par le modèle doit être vérifiée par le code : si
  elle n'est pas mot pour mot dans le dossier, elle est signalée, pas affichée
  comme preuve.

## Conventions de code

- Python 3.11 ou plus. Identifiants en anglais ; commentaires, docstrings et
  messages destinés à l'utilisateur en français.
- Modèles de données avec Pydantic v2, dans `models.py` ou à côté du module
  concerné. Les modules échangent des objets typés, pas des dictionnaires.
- Chaque étape apporte ses tests. Les tests n'utilisent que des dossiers fictifs
  générés à la volée (voir `tests/test_roundtrip.py`).
- Une nouvelle dépendance s'ajoute dans `pyproject.toml`, sous licence libre, et
  doit pouvoir s'exécuter sans service payant.
- Le client du modèle de langage parle le protocole compatible OpenAI, avec une
  adresse configurable : le même code doit fonctionner avec un modèle hébergé
  aujourd'hui et un serveur local (vLLM, Ollama) demain.

## Architecture visée par le prototype

```
PDF + vidéos + export du test
  -> import (fait) -> éligibilité -> appariement avec le test -> anonymisation
  -> découpage et indexation (bge-m3, Qdrant) -> recherche hybride + re-ranking
  -> verdict et raisons (modèle ouvert, sortie JSON contrainte)
  -> API FastAPI + PostgreSQL -> interface Next.js (tableau, preuves, validation)
```

Keycloak, Celery, SeaweedFS, la supervision et Kubernetes appartiennent à
l'architecture cible décrite dans le mémoire. Ils ne sont pas à développer.

## Points incertains à ne pas trancher seul

- La grille sur 40 points et la liste exacte des 8 Concerns viennent du mémoire,
  pas d'un document de MEST. Les garder dans un fichier de configuration, sans
  les coder en dur.
- Le formulaire 2026 et le mémoire se contredisent sur l'âge, la zone
  géographique et la plateforme de test (voir `docs/cadrage.md`). Tant que MEST
  n'a pas tranché, suivre le formulaire 2026 et rendre ces valeurs paramétrables.
- Le format réel de l'export du test est inconnu : `assessment_results.csv` est
  une supposition.
