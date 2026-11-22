# Feuille de route

Chaque étape se termine par des tests et par un critère d'acceptation mesuré sur
la cohorte fictive de référence :

```bash
eit-generate -n 40 --graine 2026 -o data/fictifs
```

Depuis le guide d'évaluation 2027 (22 novembre 2026), la cohorte suit ses
règles : identifiants `EIT-2027-001001` à `EIT-2027-001040`, âge au 1er janvier
2027, Afrique de l'Ouest ou de l'Est, test ClassMarker à rendre le 20 juillet
2026 à 23 h 59 GMT. Elle contient 40 dossiers, dont 16 avec une anomalie :
2 noms inversés dans l'export du test, 1 test introuvable, 2 tests rendus après
la date limite (le 21 ou le 22 juillet), 2 tests trop rapides, 1 série de
réponses génériques, 2 âges hors tranche, 1 âge limite (20 ans au dépôt ou
35 ans au 1er janvier 2027), 1 nationalité hors zone, 1 diplôme en 2028,
1 diplôme en 2027, 1 CV manquant, 1 vidéo inaudible. L'export du test compte
39 lignes. Les dossiers réguliers ont entre 22 et 34 ans et un diplôme obtenu
au plus tard en 2026.

**Chiffres de l'ancienne cohorte.** Les résultats des étapes 3 à 6 ci-dessous
ont été mesurés sur la cohorte précédente (règles du formulaire 2026, 38 lignes
de test). Ils restent valables comme mesures de méthode, mais doivent être
relancés sur la nouvelle cohorte avant d'être cités. Les résultats d'alors sont
gardés dans `data/archives/cohorte-formulaire-2026/`. La collection Qdrant
`passages` de l'ancienne cohorte a été supprimée (488 points) : réindexer la
nouvelle cohorte la recrée, sans mélanger les deux.

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
- **6. Recherche hybride et re-ranking** (`search/retrieve.py`) : construit et mesuré ; critère non atteint, voir ci-dessous.

## 1. Contrôles d'éligibilité

Module proposé : `screening/eligibility.py`.

- Calculer l'âge à la date de référence à partir de la date de naissance et le
  comparer à la tranche autorisée.
- Vérifier que la nationalité appartient à la zone autorisée.
- Guide 2027 : vérifier l'année d'obtention du diplôme (2028 ou après :
  écarté ; 2027 : signalé) et signaler sans écarter les âges limites.
- Signaler toute réponse « No » aux questions d'éligibilité, et toute
  contradiction entre une réponse « Yes » et les données du dossier.
- Paramètres (tranche d'âge, date de référence, liste des pays) dans un fichier
  de configuration.
- Sortie : une liste de constats typés (code, gravité, message, élément du
  dossier qui le prouve). Aucun rejet automatique.

Acceptation (guide 2027) : les 2 âges hors tranche, l'âge limite, la nationalité
hors zone et les 2 diplômes (2028, 2027) sont signalés ; aucun constat sur les
34 autres dossiers.

**Fait.** Résultat sur la cohorte de référence, lue depuis les PDF : 6 anomalies
attendues, 6 retrouvées, 0 manquée, 0 constat en trop ; 34 dossiers sans aucun
constat. Commande :

```bash
eit-eligibility data/fictifs/dossiers --scenarios data/fictifs/scenarios.csv -o data/resultats/eligibilite.json
```

Règles du guide 2027 et choix faits pour les appliquer (à confirmer avec MEST,
voir `docs/cadrage.md`) :

- âge : 21 à 35 ans au 1er janvier 2027 (alerte hors tranche). Signalés sans
  être écartés (constat « à vérifier », `age_borderline`) : 20 ans au dépôt et
  21 ans au 1er janvier ; 35 ans au 1er janvier (tous, tant que la fin du
  programme n'est pas configurée) ; 20 ans au 1er janvier mais 21 au démarrage,
  si le démarrage est configuré ;
- zone : Afrique de l'Ouest (16 pays) et de l'Est (18 pays) au sens de l'ONU ;
- diplôme : date d'obtention la plus tardive des formations déclarées ; 2028 ou
  après, alerte `graduation_after_cutoff` ; 2027, constat « à vérifier »
  `graduation_review` qui cite le mois ;
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

Acceptation (cohorte 2027) : 39 lignes rattachées au bon candidat, dont les
2 noms inversés ; 1 test introuvable, 2 en retard et 2 trop rapides signalés ;
aucune erreur de rattachement.

**Fait.** Résultat sur la cohorte de référence, dossiers lus depuis les PDF :
39 lignes sur 39 rattachées au bon dossier (37 par l'e-mail, 2 par le nom
inversé), aucune erreur, aucune ligne laissée de côté ; 1 test introuvable,
2 en retard et 2 trop rapides retrouvés ; aucun constat en trop. Commande :

```bash
eit-assessment data/fictifs/dossiers data/fictifs/assessment_results.csv --scenarios data/fictifs/scenarios.csv -o data/resultats/appariement.json
```

**À relancer.** Ces chiffres ont été obtenus avant le passage au format réel de
ClassMarker (22 novembre 2026). Le contenu de la cohorte est inchangé — le
générateur ne tire aucun nombre aléatoire de plus — mais l'export porte
désormais des points sur 50, une durée `hh:mm:ss` et des dates
`Tue 21 Jul '26 5:14pm`. Régénérer la cohorte et relancer `eit-assessment`
avant de citer ces chiffres dans le mémoire : c'est rapide, aucun modèle n'est
chargé.

La vérité utilisée pour compter les erreurs de rattachement est la colonne
`email_test` de `scenarios.csv`, ajoutée au générateur pour cette étape.
Sur les graines 0 à 11 (468 lignes), 466 lignes sont rattachées, aucune au
mauvais dossier ; 2 sont refusées comme ambiguës (nom inversé d'un candidat qui
a un homonyme exact dans la cohorte). Chiffre vérifié par le test
`test_totals_over_twelve_seeds` (`tests/test_assessment_match.py`).

Le niveau 3 (nom ressemblant) ne sert pas sur la cohorte de référence : il
n'est couvert que par les cas construits à la main dans les tests.

Choix faits, à confirmer avec MEST :

- guide 2027 : date limite le 20 juillet à 23 h 59 GMT, plateforme ouverte
  jusqu'au 22 ; toute soumission après la date limite est signalée (constat
  « à vérifier » `assessment_late`, et non plus une alerte). Hypothèses : année 2026,
  dates de l'export en GMT (`assessment.toml`, `timezone`) ;
- durée anormalement courte : moins de 20 minutes sur 70. Ce constat est « à
  vérifier », pas une alerte : une durée courte n'est pas une preuve de fraude.
  Les deux valeurs sont des hypothèses sans fondement pour ClassMarker : les
  70 minutes viennent du test TestGorilla de 2026, et la seule durée réelle
  connue est 38 min 06 s pour les 50 questions, sur un candidat ;
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

**Construit et mesuré ; critère non atteint.** Commande :

```bash
eit-search-eval --qdrant-url http://127.0.0.1:6333 -o data/resultats/recherche.json
```

Jeu de questions (`search/questions.toml`, figé avant la première mesure) :
10 questions reformulées, posées dans chacun des 40 dossiers, 395 questions en
tout (5 dossiers sans certificat). Les passages pertinents se déduisent de la
structure du dossier : réponse libre visée, transcription, page du CV,
certificat. Les 5 questions sur les réponses libres n'ont qu'une réponse par
dossier : ce sont les questions « strictes ».

| Chaîne | Rang 1 | 3 premiers | MRR | 3 premiers, questions strictes |
|---|---|---|---|---|
| Dense (bge-m3) | 71,1 % | 94,9 % | 0,832 | 90,5 % |
| Lexicale (bge-m3, poids creux) | 48,1 % | 70,6 % | 0,618 | 50,0 % |
| Hybride (fusion RRF) | 66,1 % | 90,9 % | 0,787 | 83,5 % |
| Hybride + re-ranking (bge-reranker-v2-m3) | 57,7 % | 86,6 % | 0,725 | 74,0 % |
| Tirage au hasard | | 31,2 % | | 24,9 % |

Les passages pertinents figurent parmi les 10 candidats transmis au re-ranking
dans 99,8 % des cas ; un dossier compte environ 12 passages, si bien que le
re-ranking réordonne presque tout le dossier. 53 échecs pour la chaîne complète,
dont 25 sur la question « unconventional ». Les échecs touchent plus les
dossiers riches (20 % des questions des dossiers « fort ») que les réponses
génériques (0 %). Durée : 39 minutes sur processeur pour les 395 questions.

Constats :

- **Aucune chaîne n'atteint le critère** : la meilleure, la recherche dense
  seule, place un passage pertinent dans les 3 premiers pour 94,9 % des
  questions.
- **La fusion avec la recherche lexicale dégrade la recherche dense** sur ces
  questions reformulées, qui partagent peu de mots avec les réponses.
- **Le re-ranking dégrade encore.** Exemple : pour « Has the candidate solved a
  problem in an unusual or creative way? », il classe en tête les passages qui
  contiennent `[CANDIDAT]` (présentation, CV), avec des scores tous négatifs ;
  la réponse visée finit 8e. Le diagnostic ci-dessous désigne surtout la
  formulation de la question.
- **Le jeu de questions est strict** : une autre réponse libre peut répondre
  aussi (un récit de leadership décrit souvent une solution originale) ; elle
  compte ici comme un échec.

Diagnostic exploratoire, sur la seule question « unconventional », hors mesure
officielle (script ponctuel, à reprendre en commande si le mémoire le cite) :
la chaîne complète passe de 15 à 27 dossiers sur 40 avec une autre formulation
(« Solving a problem in an unusual or creative way. » : plus de « the
candidate », et une affirmation au lieu d'une question ; les candidats de la
fusion changent aussi), et seulement de 15 à 19 quand la marque `[CANDIDAT]` est
cachée au re-ranking. L'effet tient donc surtout à la formulation des
requêtes. La recherche dense seule en trouve 29 sur 40 avec la question
d'origine.

Ce qui est construit et reste à décider :

- `Retriever.for_criteria` : une requête par critère de la grille
  (`grille.toml`), limitée au dossier du candidat ; ces requêtes n'ont pas de
  vérité terrain et ne sont pas mesurées.
- **Décision prise le 22 novembre 2026, en l'absence de l'auteur** (il avait
  demandé de poursuivre sans attendre) : le verdict utilise la recherche dense
  seule (`search.toml`, `retrieval.mode = "dense"`), la meilleure chaîne
  mesurée. L'hybride et le re-ranking restent dans le code et dans la mesure ;
  remettre `mode = "hybrid_rerank"` pour suivre le cadrage d'origine.
- Les ex aequo de la fusion RRF revenaient dans un ordre arbitraire (deux
  mesures identiques donnaient 90,9 % et 91,1 %) : les candidats sont
  maintenant triés par score puis par identifiant.
- bge-m3 et le re-ranking ne tiennent pas ensemble en mémoire sur la machine de
  développement : les requêtes sont encodées d'abord, puis bge-m3 est libéré.

## 7. Verdict et raisons

- Client compatible OpenAI, adresse et modèle configurables.
- Sortie JSON conforme à un modèle Pydantic `Verdict` : note et raison par
  critère, citation exacte, alertes, décision proposée.
- Guide 2027 : la décision prend trois valeurs (`Interview Invitation`,
  `Interview Reject`, `Waitlist`) et un booléen distinct,
  `request_further_review`. Un constat qui écarte selon le guide (âge hors
  tranche, nationalité hors zone, diplôme en 2028 ou après) fait proposer
  `Interview Reject` ; tout autre constat, un Concern ou une citation
  introuvable demande la revue complémentaire sans changer la décision ; sans
  réponse exploitable du modèle, aucune décision n'est proposée.

**Écrit, non exécuté sur la cohorte 2027.** Le code est testé avec un faux
serveur compatible OpenAI. Deux verdicts d'essai seulement ont tourné, sur
l'ancienne cohorte et avec l'ancien modèle de décision ; le critère
d'acceptation (40 verdicts) n'est pas atteint. Substitut local : Ollama,
`llama3.2` (3B), environ 100 s par dossier sur processeur.
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

**Écrit, non exécuté de bout en bout** (`api/`, commandes `eit-api-load` et
`eit-api`) : testé sur SQLite en mémoire, jamais lancé contre PostgreSQL avec de
vrais verdicts. Une modification
exige la décision retenue et un commentaire ; une « modification » identique à
la proposition (décision et revue) est refusée (il faut « valider »). Guide
2027 : chaque décision garde les valeurs proposées et retenues de la décision
(trois valeurs) et de la demande de revue complémentaire ; sans décision
proposée, l'évaluateur en choisit une. Le journal n'est jamais réécrit : recharger les
verdicts ne touche pas aux décisions. PostgreSQL 16 tourne dans Docker sur
127.0.0.1:5433 ; les tests utilisent SQLite en mémoire. Pas d'authentification :
l'évaluateur saisit son nom (Keycloak relève de l'architecture cible).

## 9. Interface

- Next.js, TypeScript, Tailwind CSS, shadcn/ui.
- Écran 1 : tableau des candidatures, triable et filtrable.
- Écran 2 : verdict et raisons à gauche, dossier à droite avec les citations
  surlignées ; boutons pour valider ou modifier.

**Écrit, non exécuté de bout en bout** (`ui/`, Next.js 16, shadcn/ui) : types
et lint vérifiés, jamais ouvert dans un navigateur. Ce qui suit décrit le
comportement prévu. Le tableau se trie par total, alertes,
Concerns et âge, et se filtre par verdict, statut et genre. L'écran du dossier
montre la règle appliquée, les constats et Concerns, puis chaque critère avec sa
note, sa raison et sa citation : « voir dans le dossier » fait défiler le
dossier anonymisé jusqu'à la citation surlignée ; une citation introuvable est
marquée comme telle et n'est pas surlignée. L'historique des décisions est
affiché sous les boutons.

## 10. Évaluation

- Mesures décrites dans `docs/cadrage.md`, lancées par une commande unique.
- Test contrefactuel de biais : changer le pays (et les lieux) d'un même dossier
  et vérifier que le verdict proposé ne change pas.
- Export des résultats avec date, version du code, modèle et graine.

**Écrit, non exécuté** (`evaluation/report.py`, `eit-evaluate` ;
`evaluation/counterfactual.py`, `eit-counterfactual`) : les outils statistiques
sont testés, mais les deux commandes n'ont jamais tourné, faute de verdicts.

## Amélioration à prévoir avant le test avec les évaluateurs

La banque de textes de `synthetic/content.py` est trop petite : sur 40 dossiers,
un même texte revient jusqu'à quatre fois. L'enrichir, ou faire écrire les
réponses par un modèle de langage, avant de faire noter les dossiers.
