# Feuille de route

Chaque étape se termine par des tests et par un critère d'acceptation mesuré sur
la cohorte fictive de référence :

```bash
eit-generate -n 40 --graine 2026 -o data/fictifs
```

Cette cohorte contient 40 dossiers, dont 16 avec une anomalie : 2 noms inversés
dans l'export du test, 2 tests introuvables, 2 tests en retard, 2 tests trop
rapides, 3 séries de réponses génériques, 2 âges hors tranche, 1 nationalité
hors zone, 1 CV manquant, 1 vidéo inaudible. L'export du test compte 38 lignes.

Les étapes 1 à 3 n'utilisent aucun modèle de langage. Elles se font en premier.

## Étapes terminées

- **Import** (`ingestion/smapply_pdf.py`) : export PDF vers `Application`.
- **Dossiers fictifs** (`synthetic/`) : PDF au format réel, transcriptions,
  export du test, scénarios.
- **1. Contrôles d'éligibilité** (`screening/eligibility.py`) : voir ci-dessous.
- **2. Appariement avec l'export du test** (`screening/assessment_match.py`) : voir ci-dessous.

## 1. Contrôles d'éligibilité

Module proposé : `screening/eligibility.py`.

- Calculer l'âge à la date de référence à partir de la date de naissance et le
  comparer à la tranche autorisée.
- Vérifier que la nationalité appartient à la zone autorisée.
- Signaler toute réponse « No » aux questions d'éligibilité, et toute
  contradiction entre une réponse « Yes » et les données du dossier.
- Paramètres (tranche d'âge, date de référence, liste des pays) dans un fichier
  de configuration.
- Sortie : une liste de constats typés (code, gravité, message, élément du
  dossier qui le prouve). Aucun rejet automatique.

Acceptation : les 2 âges hors tranche et la nationalité hors zone sont signalés ;
aucun constat sur les 37 autres dossiers.

**Fait.** Résultat sur la cohorte de référence, lue depuis les PDF : 3 anomalies
attendues, 3 retrouvées, 0 manquée, 0 constat en trop ; 37 dossiers sans aucun
constat. Commande :

```bash
eit-eligibility data/fictifs/dossiers --scenarios data/fictifs/scenarios.csv -o data/resultats/eligibilite.json
```

Choix faits, à confirmer avec MEST :

- âge calculé au 1er janvier 2026 (début du programme) ;
- « Afrique de l'Ouest » au sens de l'ONU (16 pays, dont Mali, Burkina Faso,
  Niger et Mauritanie) ;
- nationalité hors zone avec double nationalité déclarée : constat « à
  vérifier », car le formulaire ne donne pas la seconde nationalité ;
- seuls l'âge et la nationalité sont confrontés aux données ; pour les huit
  autres questions, aucune donnée structurée ne permet de contredire un « Yes »
  (« degree… or equivalent experience »), on relève donc seulement les « No »
  et les réponses illisibles.

## 2. Appariement avec l'export du test

Module proposé : `screening/assessment_match.py`. Dépendance : RapidFuzz.

- Niveau 1 : adresse e-mail identique.
- Niveau 2 : nom et prénom inversés.
- Niveau 3 : ressemblance du nom complet au-dessus d'un seuil, sans tenir compte
  de la casse ni des accents.
- Refuser un appariement ambigu (deux candidats possibles) plutôt que deviner.
- Constats : test introuvable, test après la date limite, durée anormalement
  courte.

Acceptation : 38 lignes rattachées au bon candidat, dont les 2 noms inversés ;
2 tests introuvables, 2 en retard et 2 trop rapides signalés ; aucune erreur de
rattachement.

**Fait.** Résultat sur la cohorte de référence, dossiers lus depuis les PDF :
38 lignes sur 38 rattachées au bon dossier (36 par l'e-mail, 2 par le nom
inversé), aucune erreur, aucune ligne laissée de côté ; 2 tests introuvables,
2 en retard et 2 trop rapides retrouvés ; aucun constat en trop. Commande :

```bash
eit-assessment data/fictifs/dossiers data/fictifs/assessment_results.csv --scenarios data/fictifs/scenarios.csv -o data/resultats/appariement.json
```

La vérité utilisée pour compter les erreurs de rattachement est la colonne
`email_test` de `scenarios.csv`, ajoutée au générateur pour cette étape.
Sur les graines 0 à 11 (456 lignes), 453 lignes sont rattachées, aucune au
mauvais dossier ; 3 sont refusées comme ambiguës (nom inversé d'un candidat qui
a un homonyme exact dans la cohorte). Chiffre vérifié par le test
`test_totals_over_twelve_seeds` (`tests/test_assessment_match.py`).

Le niveau 3 (nom ressemblant) ne sert pas sur la cohorte de référence : il
n'est couvert que par les cas construits à la main dans les tests.

Choix faits, à confirmer avec MEST :

- date limite au 10 août 2025, jour compris (hypothèse du générateur) ;
- durée anormalement courte : moins de 20 minutes sur 70. Ce constat est « à
  vérifier », pas une alerte : une durée courte n'est pas une preuve de fraude ;
- seuil de ressemblance des noms à 90/100. Deux personnes différentes peuvent
  l'atteindre (« Femi » et « Temi » Balogun : 92) ; dans ce cas la ligne n'est
  rattachée à personne et les deux dossiers reçoivent un constat « à vérifier » ;
- si plusieurs lignes vont au même dossier, la plus ancienne sert aux contrôles
  et un constat « à vérifier » le signale.

Le seuil de durée et la date limite sont calés sur le générateur (7 à 13
minutes pour les tests trop rapides, 38 à 70 pour les autres) : le 2 sur 2 est
acquis par construction et ne dit rien de la tenue sur un vrai export.

## 3. Anonymisation

Module proposé : `privacy/anonymize.py`. Dépendances : Microsoft Presidio, spaCy.

- Masquer dans tout texte destiné au modèle : nom, prénom, e-mail, téléphone et
  liens du candidat, mais aussi ceux des tiers (parrain, références, personnes
  citées dans le CV), et les noms présents dans les noms de fichiers.
- Attribuer un pseudonyme aléatoire. Écrire la table de correspondance dans un
  fichier séparé, hors du dépôt.
- Garder le genre, l'âge et la nationalité comme métadonnées, hors du texte.

Acceptation : un test de fuite parcourt les 40 dossiers anonymisés et ne trouve
aucun nom, e-mail ni téléphone figurant dans les `reference.json`.

## 4. Pièces jointes et vidéos

- Lire les pièces jointes avec Docling, OCR compris pour les pages marquées
  `needs_ocr`.
- Transcrire les vidéos avec faster-whisper après extraction audio par FFmpeg.
  Pour les dossiers fictifs, lire les fichiers `.txt` à la place.

Acceptation : le texte des certificats en image est récupéré ; la transcription
garde l'horodatage des segments.

## 5. Découpage et indexation

- Découper chaque dossier par section : réponses libres, CV, pièces jointes,
  transcriptions. Chaque passage garde sa provenance (section, page, horodatage).
- Embeddings denses et creux avec bge-m3, stockés dans Qdrant (Docker Compose).

Acceptation : chaque passage indexé permet de retrouver son emplacement exact
dans le dossier.

## 6. Recherche hybride et re-ranking

- Recherche dense et creuse dans Qdrant, fusion par Reciprocal Rank Fusion,
  re-ranking avec bge-reranker-v2-m3.
- Une requête par critère de la grille, limitée au dossier du candidat.

Acceptation : pour un jeu de questions dont la réponse est connue par
construction, le bon passage figure parmi les trois premiers.

## 7. Verdict et raisons

- Client compatible OpenAI, adresse et modèle configurables.
- Sortie JSON conforme à un modèle Pydantic `Verdict` : note et raison par
  critère, citation exacte, alertes, verdict proposé.
- Vérifier chaque citation dans le dossier ; signaler celles qui ne s'y trouvent
  pas mot pour mot.
- Règle de décision explicite et paramétrable entre notes, alertes et verdict.
- Conserver pour chaque appel le prompt, les passages fournis et la réponse.

Acceptation : 40 verdicts produits, tous conformes au schéma ; taux de citations
vérifiées mesuré et exporté.

## 8. API et base de données

- FastAPI et PostgreSQL : liste des candidats, détail d'un dossier, verdict
  proposé, décision de l'évaluateur (valider ou modifier, avec commentaire).
- Journal de chaque décision : qui, quand, verdict proposé, verdict retenu.

## 9. Interface

- Next.js, TypeScript, Tailwind CSS, shadcn/ui.
- Écran 1 : tableau des candidatures, triable et filtrable.
- Écran 2 : verdict et raisons à gauche, dossier à droite avec les citations
  surlignées ; boutons pour valider ou modifier.

## 10. Évaluation

- Mesures décrites dans `docs/cadrage.md`, lancées par une commande unique.
- Export des résultats avec date, version du code, modèle et graine.

## Amélioration à prévoir avant le test avec les évaluateurs

La banque de textes de `synthetic/content.py` est trop petite : sur 40 dossiers,
un même texte revient jusqu'à quatre fois. L'enrichir, ou faire écrire les
réponses par un modèle de langage, avant de faire noter les dossiers.
