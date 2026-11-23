# eit-screening

Prototype d'aide à la présélection des candidatures du MEST AI Startup Program.
Il est développé pour un mémoire de Master en génie logiciel (Lomé Business
School) : le code doit produire des résultats mesurés, repris dans le mémoire.

## Ce que fait le produit

Pour chaque candidature, le système propose une **décision de présélection**
et les **raisons** qui l'appuient. Un évaluateur de MEST valide ou modifie
cette décision. **Le système ne décide jamais seul**, même pour un candidat
écarté par le guide : il propose, l'humain tranche, et les deux décisions sont
conservées.

- Décision (guide d'évaluation 2027) : trois valeurs, `Interview Invitation`,
  `Interview Reject`, `Waitlist`, et un booléen distinct,
  `request_further_review`. « Request Final Review » n'est plus une valeur.
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
| `src/eit_screening/screening/eligibility.py` | Fait. Constats d'éligibilité (âge, zone, diplôme), paramètres dans `eligibility.toml` |
| `src/eit_screening/screening/assessment_match.py` | Fait. Appariement avec l'export du test, paramètres dans `assessment.toml` |
| `src/eit_screening/privacy/anonymize.py` | Fait. Anonymisation en trois couches, pseudonymes, paramètres dans `anonymize.toml` |
| `src/eit_screening/media/` | Fait. Pièces jointes (Docling, OCR) et vidéos (FFmpeg, faster-whisper), paramètres dans `media.toml` |
| `src/eit_screening/search/` | Fait (indexation). Découpage, bge-m3, Qdrant ; paramètres dans `search.toml` |
| `src/eit_screening/search/retrieve.py` | Construit et mesuré, critère non atteint ; chaîne par défaut : dense (voir feuille de route, étape 6) |
| `src/eit_screening/grille.toml`, `grid.py` | Critères provisoires (mémoire) ; les 8 Concerns sont ceux du tableau de bord 2027 |
| `src/eit_screening/verdict/` | Écrit et testé (faux serveur) ; aucun verdict produit sur la cohorte 2027. Décision à trois valeurs + revue complémentaire ; paramètres dans `verdict.toml` |
| `src/eit_screening/api/` | Écrit et testé (SQLite) ; jamais lancé contre PostgreSQL avec de vrais verdicts |
| `ui/` | Écrit, types et lint vérifiés ; jamais ouvert dans un navigateur |
| `src/eit_screening/evaluation/` | Écrit et testé (outils) ; `eit-evaluate` et `eit-counterfactual` jamais exécutés |

Le détail des étapes et leurs critères d'acceptation sont dans
`docs/feuille-de-route.md`. Les décisions déjà prises et les points à confirmer
avec MEST sont dans `docs/cadrage.md`. Lire ces deux fichiers avant de commencer
une nouvelle étape.

## Commandes

```bash
pip install -e ".[dev]" --extra-index-url https://download.pytorch.org/whl/cpu   # installation (PyTorch CPU)
pytest                                              # tests (environ 4 min)
eit-generate -n 40 --graine 2026 -o data/fictifs    # cohorte fictive de référence
eit-import data/fictifs/dossiers/EIT-2027-001007/application.pdf -o dossier.json
eit-eligibility data/fictifs/dossiers --scenarios data/fictifs/scenarios.csv -o data/resultats/eligibilite.json
eit-assessment data/fictifs/dossiers data/fictifs/assessment_results.csv --scenarios data/fictifs/scenarios.csv -o data/resultats/appariement.json
eit-media data/fictifs/dossiers -o data/resultats/extraction.json            # OCR et transcriptions (environ 10 min)
eit-anonymize data/fictifs/dossiers -o data/anonymises --table ~/.local/share/eit-screening/pseudonymes-fictifs-2027.json
eit-leak-check data/fictifs/dossiers data/anonymises --table ~/.local/share/eit-screening/pseudonymes-fictifs-2027.json
docker compose up -d qdrant                                                   # base vectorielle
eit-index data/anonymises --qdrant-url http://127.0.0.1:6333 -o data/resultats/indexation.json
eit-search-eval --qdrant-url http://127.0.0.1:6333 -o data/resultats/recherche.json   # environ 40 min
eit-verdict data/anonymises --qdrant-url http://127.0.0.1:6333 --table ~/.local/share/eit-screening/pseudonymes-fictifs-2027.json   # Ollama local, environ 1 h
eit-verdict data/anonymises --qdrant-url http://127.0.0.1:6333 --table ~/.local/share/eit-screening/pseudonymes-fictifs-2027.json --dossier-entier -o data/verdicts-dossier-entier
docker compose up -d postgres && eit-api-load && eit-api                   # API sur http://127.0.0.1:8000
cd ui && pnpm install && pnpm dev --port 3100                                 # interface
eit-evaluate --table ~/.local/share/eit-screening/pseudonymes-fictifs-2027.json   # export unique des mesures
```

## Ressources de la machine de développement

Environ 3 à 5 Go de mémoire libre et 2 Go de disque. Docling, Whisper, bge-m3,
le re-ranking et Ollama prennent chacun environ 2 Go : ne lancer qu'un travail
lourd à la fois. Le 22 novembre 2026, deux travaux simultanés ont déclenché le
tueur de processus du noyau, qui a fermé l'application Claude.

## Règles sur les données

- Ne jamais versionner `data/` ni aucun dossier de candidature, réel ou fictif.
- Les dossiers réels restent sur la machine de la personne autorisée. Ne pas les
  copier dans le dépôt, dans un test, dans un message de commit ou dans un
  exemple de documentation.
- Seul du texte **anonymisé** peut partir vers un modèle de langage hébergé.
  Tout le reste (lecture des PDF, transcription, embeddings, recherche) tourne
  en local.
- Le genre, l'âge et la nationalité servent aux contrôles d'éligibilité et aux
  filtres, jamais au texte envoyé au modèle de langage. Pour la même raison, les
  pays, villes, nationalités et langues locales sont masqués dans ce texte
  (`[PAYS]`, `[VILLE]`…) ; seuls les noms d'établissements et d'employeurs du
  dossier sont gardés tels quels.
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

- La grille sur 40 points vient du mémoire, pas d'un document de MEST. Elle est
  dans `src/eit_screening/grille.toml`, jamais codée en dur.
- Les **huit Concerns sont connus** : ce sont les drapeaux du tableau de bord de
  revue de la cohorte 2027, repris dans `grille.toml` avec leur libellé exact.
  Chacun porte un champ `detection` : `controle`, `modele` ou `manuel`. Trois
  seulement sont produits automatiquement ; ne jamais inventer de détection pour
  un drapeau `manuel`, le test `test_no_concern_is_detected_unless_the_grid_says_so`
  le vérifie.
- Le guide d'évaluation 2027 de MEST est la référence (voir
  `docs/cadrage.md`) : âge 21-35 au 1er janvier 2027, Afrique de l'Ouest ou de
  l'Est, diplôme avant 2028, test ClassMarker (date limite 20 juillet 23 h 59
  GMT), identifiants `EIT-2027-XXXXXX`. Ce qu'il ne précise pas (dates du
  programme, liste des pays d'Afrique de l'Est, année et durée du test) est en
  configuration et marqué HYPOTHÈSE.
- Les domaines de la grille du guide ne sont pas encore reportés :
  `grille.toml` garde la grille provisoire du mémoire. Ne pas inventer de noms
  ni de pondération.
- Le format des **valeurs** de ClassMarker est connu (fiche de résultat 2027
  observée le 22 novembre 2026) : points sur 50, durée `hh:mm:ss`, date
  `Tue 21 Jul '26 5:52pm`, 50 questions en quatre catégories. Les **noms de
  colonnes** de l'export groupé restent inconnus : ceux de
  `assessment_results.csv` sont une supposition.
- La durée prévue du test (70 minutes) et le seuil « trop rapide » (20 minutes)
  n'ont aucun fondement pour ClassMarker. Ne pas les présenter comme mesurés.
