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
- **3. Anonymisation** (`privacy/anonymize.py`) : voir ci-dessous.
- **4. Pièces jointes et vidéos** (`media/`) : voir ci-dessous.
- **5. Découpage et indexation** (`search/`) : voir ci-dessous.

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

**Fait.** Test de fuite (`test_no_leak_in_reference_cohort`) : aucun nom, e-mail,
téléphone ni lien LinkedIn de `reference.json` dans les 40 dossiers anonymisés,
noms de fichiers compris. Le détecteur est écrit à part du module ; il trouve une
fuite dans chacun des 40 dossiers bruts (`test_detector_finds_leaks_in_raw_dossiers`).
Commande :

```bash
eit-anonymize data/fictifs/dossiers -o data/anonymises --table ~/.local/share/eit-screening/pseudonymes-fictifs.json
```

Masquage en quatre couches : identifiants donnés par le dossier (candidat,
parrain, références), motifs (e-mail, téléphone, lien), lieux (pays, villes,
nationalités, langues locales), reconnaissance des noms de personnes et des
lieux inconnus (Presidio, modèle spaCy `en_core_web_md` 3.8.0). Sur la cohorte :
134 mentions du candidat, 5 de tiers, 39 e-mails, 39 téléphones, 39 liens,
238 pays, 39 villes et 3 langues masqués ; la reconnaissance d'entités ne
masque rien (la cohorte ne cite ni tiers ni lieu inconnus du dossier).

Lieux (décision du 22 novembre 2026) : le modèle ne doit pas pouvoir déduire la
nationalité. Pays, villes, nationalités et langues locales deviennent `[PAYS]`,
`[VILLE]`, `[NATIONALITÉ]`, `[LANGUE]` ; un lieu repéré par la reconnaissance
d'entités devient `[LIEU]`. Le modèle voit toujours qu'un lieu précis est cité,
ce qui distingue une réponse personnelle d'une réponse générique. Les noms
d'établissements et d'employeurs déclarés dans le dossier sont gardés (option
`keep_organisations`) : sur la cohorte, aucun lieu déclaré ne reste dans le
texte libre (`test_no_declared_place_outside_kept_organisations`), mais 10
dossiers sur 40 le laissent lire dans un nom d'établissement (« University of
Ghana », « University of Lagos »). Le biais résiduel est à mesurer à l'étape 10
par un test contrefactuel : changer le pays d'un dossier et vérifier que le
verdict ne bouge pas.

Limites :

- **Faux positifs de la reconnaissance d'entités.** Sans filtre, elle masquait
  83 passages sur la cohorte, tous à tort (entreprises, universités, pays). Elle
  écarte désormais ce que le dossier nomme comme lieu, organisation, poste ou
  formation, et une liste de mots techniques (`allow_list`). Elle n'est vérifiée
  que sur des cas construits à la main : son rappel sur de vrais CV reste à
  mesurer.
- **Masquage par excès.** Un mot du nom d'une personne est masqué partout :
  « Kwame Nkrumah University » devient « [PERSONNE_2] Nkrumah University » si
  une référence s'appelle Kwame.
- **Langue.** Le modèle est anglais ; un CV en français serait moins bien
  traité par la troisième couche.
- **Liste des lieux.** Les pays, villes et langues masqués sans la
  reconnaissance d'entités viennent d'une liste (`anonymize.toml`) et des lieux
  déclarés dans le dossier. Une petite ville absente de la liste dépend de la
  reconnaissance d'entités, dont le rappel n'est pas mesuré.

## 4. Pièces jointes et vidéos

- Lire les pièces jointes avec Docling, OCR compris pour les pages marquées
  `needs_ocr`.
- Transcrire les vidéos avec faster-whisper après extraction audio par FFmpeg.
  Pour les dossiers fictifs, lire les fichiers `.txt` à la place.

Acceptation : le texte des certificats en image est récupéré ; la transcription
garde l'horodatage des segments.

**Fait.** Commande :

```bash
eit-media data/fictifs/dossiers -o data/resultats/extraction.json
```

Pièces jointes, sur la cohorte de référence (Docling, OCR RapidOCR, processeur) :
40 certificats en image, similarité moyenne 97,6/100 avec le texte attendu
(`pieces_jointes.json`, écrit par le générateur) ; 149 lignes sur 200 lues à
l'identique ; le nom du candidat est lu à l'identique dans 35 certificats sur
40, et chacun de ses mots, dans n'importe quel ordre, dans 39 sur 40 (l'OCR
inverse parfois prénom et nom ; le 40e lit « iOuattara »). Les 21 certificats en texte sont lus à 100/100.
Environ 11 s par dossier. Les images sont propres et générées : ce taux est
acquis en bonne partie par construction et ne dit rien des scans réels.

Transcription : FFmpeg extrait l'audio, faster-whisper (modèle « small »,
processeur) le transcrit ; chaque segment garde son début, sa fin et les valeurs
de confiance de Whisper. Vérifié sur une vidéo dont la voix est synthétisée par
FFmpeg (`test_transcription_keeps_timestamps`) : deux phrases séparées par un
silence donnent au moins deux segments horodatés, dans l'ordre. Les
dossiers fictifs n'ont pas de vidéo : leurs transcriptions sont lues dans les
fichiers `.txt`, sans horodatage (aucun n'est inventé). L'horodatage n'est donc
démontré que sur la vidéo synthétique.

Anonymisation du texte obtenu : `eit-anonymize` lit `extraction.json`. Le texte
issu de l'OCR ou de la voix passe par une couche de plus, qui masque les mots
proches d'un nom du dossier, ou d'un pays ou d'une ville (seuil 85/100). Les
nationalités et langues n'y passent pas, trop proches de mots courants
(« librarian » et « Liberian »). Contrôle sur la cohorte relue par l'OCR, avec un
code indépendant du module d'anonymisation :

```bash
eit-leak-check data/fictifs/dossiers data/anonymises --table ~/.local/share/eit-screening/pseudonymes-fictifs.json
```

Résultat : aucune fuite de nom, e-mail, téléphone ou lien (0/40), aucun lieu
déclaré dans le texte libre (0/40). Le contrôle liste aussi les mots « suspects »
du texte OCR ou transcrit, proches d'un nom ou d'un lieu (seuil 75) : 6 dossiers,
dont 2 vrais (« Lomø ») et 4 faux (« hello », « name », « seen »…).

Limites :

- **Lieu mal lu.** L'OCR lit « Lomø » pour « Lomé » dans 2 dossiers ; le mot est
  trop éloigné (75/100) pour être masqué et le détecteur exact ne le voit pas.
- **Nom mal entendu.** Avec le modèle « tiny », Whisper entend « Gofima » pour
  « Kofi Mensah » : aucune comparaison ne le rattache au nom. La reconnaissance
  d'entités l'a masqué par chance. Avec « small », il entend « Kofi Mensa »,
  masqué par la couche approchée. Le taux de noms mal entendus n'est pas mesuré.
- **Vidéos réelles.** L'export ne contient que des liens protégés ; le module ne
  les télécharge pas et attend la vidéo à côté du PDF (`personal_statement.mp4`).
- **Incompatibilité contournée.** faster-whisper 1.2.1 ne lit pas l'audio avec
  PyAV 19 ; le module lit lui-même le WAV produit par FFmpeg.

## 5. Découpage et indexation

- Découper chaque dossier par section : réponses libres, CV, pièces jointes,
  transcriptions. Chaque passage garde sa provenance (section, page, horodatage).
- Embeddings denses et creux avec bge-m3, stockés dans Qdrant (Docker Compose).

Acceptation : chaque passage indexé permet de retrouver son emplacement exact
dans le dossier.

**Fait.** Commandes :

```bash
docker compose up -d qdrant
eit-index data/anonymises --qdrant-url http://127.0.0.1:6333 -o data/resultats/indexation.json
```

Résultat sur la cohorte de référence (serveur Qdrant 1.20.0, bge-m3 sur
processeur) : 488 passages (réponses libres 200, pièces jointes 101,
expériences 61, transcription de présentation 46, formation 40, réflexion 40) ;
chacun relu dans Qdrant redonne exactement son texte, sa section, sa page et
son horodatage (488/488), et tout le texte indexable est couvert. Aucun passage
tronqué (204 jetons au plus, limite 512). 3 min 45 s pour la cohorte, soit
0,46 s par passage ; 2,2 Go de mémoire au plus.

Choix faits :

- **Entrée** : seuls les dossiers anonymisés sont indexés, sous leur
  pseudonyme. Ni PDF, ni table de correspondance, ni numéro de candidature.
- **Passages** : 120 mots au plus, 20 mots de recouvrement ; une tranche exacte
  du texte anonymisé, avec section, question, page et positions. Les segments
  horodatés consécutifs d'une vidéo sont regroupés et gardent le début du
  premier et la fin du dernier. Les noms de fichiers ne sont pas indexés.
- **Embeddings** : bge-m3 (révision `5617a9f`), vecteur dense et poids lexicaux,
  calculés avec transformers sans la bibliothèque FlagEmbedding. Le test
  `test_bge_m3_matches_model_card` retrouve les valeurs publiées dans la fiche du
  modèle à 0,001 près (tolérance du test : 0,002).
- **Qdrant** : une collection, un index sur le pseudonyme ; réindexer un dossier
  remplace ses passages. Les tests utilisent Qdrant en mode local, sans serveur.

Limites :

- Les positions se rapportent au texte anonymisé. Dans le dossier d'origine,
  l'emplacement est exact à la question, à la page ou au segment près.
- La cohorte n'a pas de transcription horodatée (fichiers `.txt`) : le
  regroupement des segments n'est vérifié que sur un cas construit à la main.
- La suite de tests charge Docling, Whisper, spaCy et bge-m3 dans le même
  processus : 3,1 Go de mémoire au plus.

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
- Test contrefactuel de biais : changer le pays (et les lieux) d'un même dossier
  et vérifier que le verdict proposé ne change pas.
- Export des résultats avec date, version du code, modèle et graine.

## Amélioration à prévoir avant le test avec les évaluateurs

La banque de textes de `synthetic/content.py` est trop petite : sur 40 dossiers,
un même texte revient jusqu'à quatre fois. L'enrichir, ou faire écrire les
réponses par un modèle de langage, avant de faire noter les dossiers.
