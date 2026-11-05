# RSLM — Reproducible Small Language Model

Assistant documentaire local basé sur la génération augmentée par récupération
(RAG). RSLM assemble une API FastAPI, une interface Streamlit, Qdrant, des
modèles Sentence Transformers et Ollama. Le projet fournit un parcours
reproductible ; il n’entraîne pas ses propres poids de modèle de langage.

**Lire ce projet dans une autre langue :** [Français](README.md) ·
[English](README.en.md) · [21 autres langues](docs/readme/README.md)

Les présentations traduites sont synthétiques ; les guides détaillés et les
commandes de référence sont maintenus en français et en anglais.

**Site du projet :** un site bilingue français/anglais est fourni dans
[`site/`](site/). Après activation du workflow GitHub Pages, il sera accessible
à l’adresse `https://<propriétaire>.github.io/<dépôt>/`. Dans GitHub, choisir
**Settings → Pages → Build and deployment → GitHub Actions**.

Consultez aussi les consignes de contribution dans
[`instructions.md`](instructions.md) et les règles de sécurité dans
[`securite.instructions.md`](securite.instructions.md).

**Reproduire le projet pas à pas :** consultez le
[guide de reproduction](docs/guide-reproduction.md) et le
[schéma réaliste des étapes de réalisation](docs/project-stages.md).

## Fonctionnalités

- Recherche dans des PDF avec références de documents et de pages.
- Historique local des conversations et retours utilisateur.
- Import, réindexation, suppression et restauration de documents via l’interface d’administration.
- Sauvegardes du corpus et de l’historique.
- Traçabilité des candidats de recherche, du contexte transmis au modèle et des sources présentées.
- Jeux d’évaluation configurables pour mesurer la récupération et vérifier les réponses sur un corpus donné.

## Architecture

```text
Navigateur → Streamlit → FastAPI → Ollama
                         └→ Qdrant
PDF → extraction et découpage → embeddings → index vectoriel Qdrant
```

En mode local, Qdrant conserve son index dans `data/qdrant`. Avec Docker Compose, Qdrant utilise un volume Docker nommé. Les deux modes ont des index séparés.

## Langages et technologies

- **Python** : API, interface Streamlit, indexation et évaluations.
- **HTML, CSS et JavaScript** : site statique bilingue.
- **YAML** : Docker Compose et automatisations GitHub Actions.
- **Markdown** : documentation et README en 23 langues.
- **Dockerfile** : construction de l’image de l’API.

Le code applicatif est principalement écrit en Python ; les modèles et leurs
poids sont des dépendances tierces et ne sont pas inclus dans le dépôt.

## Prérequis

- Python 3.11 ou plus récent et les dépendances de `requirements.txt`.
- Ollama installé, démarré, et un modèle conversationnel disponible, par exemple `qwen2.5:1.5b`.
- Pour Compose : Docker Desktop (Windows/macOS) ou Docker Engine avec le
  plugin Compose (Linux).
- Au premier lancement, les modèles d’embedding et de reranking sont téléchargés depuis Hugging Face.

## Choisir un parcours d’installation

- **Local** — Streamlit, FastAPI, Qdrant et Ollama sur votre machine.
- **Docker Compose** — API et Qdrant en conteneurs, avec Ollama sur l’hôte.

Les instructions pas à pas incluent les commandes PowerShell ainsi que des
parcours Linux/macOS. La configuration multi-plateforme n’est pas encore
couverte par une matrice CI.

## Installation locale

Dans PowerShell, depuis le dossier du projet :

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
ollama pull qwen2.5:1.5b
```

Sous Linux/macOS avec Bash ou zsh :

```sh
python3 -m venv .venv
. .venv/bin/activate
python -m pip install -r requirements.txt
cp .env.example .env
ollama pull qwen2.5:1.5b
```

Configurez les valeurs nécessaires dans `.env`. Générez une longue valeur aléatoire pour `RSLM_ADMIN_KEY` afin d’activer l’administration du corpus. L’API et Streamlit doivent utiliser la même clé. Pour une instance locale, gardez les services liés à `127.0.0.1`.
`RSLM_ALLOWED_ORIGINS` limite les origines navigateur autorisées ; la valeur
par défaut est `http://localhost:5173`. N’ajoutez pas un site public ici pour
lui donner accès au corpus local : CORS n’authentifie pas les requêtes.

Démarrez l’API et l’interface dans deux terminaux :

```powershell
.\.venv\Scripts\python.exe -m uvicorn src.api_stream3:app --host 127.0.0.1 --port 8080
```

```powershell
$env:RSLM_API_URL = "http://127.0.0.1:8080"
.\.venv\Scripts\python.exe -m streamlit run src\app_stream.py
```

L’interface est accessible à `http://localhost:8501`.

Sous Linux/macOS, avec l’environnement virtuel activé, démarrez l’API puis
Streamlit dans deux terminaux :

```sh
python -m uvicorn src.api_stream3:app --host 127.0.0.1 --port 8080
```

```sh
RSLM_API_URL=http://127.0.0.1:8080 python -m streamlit run src/app_stream.py
```

## Corpus documentaire

Le dépôt ne fournit **aucun PDF, modèle téléchargé, embedding ou autre corpus**. Ajoutez uniquement des documents que vous êtes autorisé à traiter et à redistribuer. Ces fichiers et leurs index restent locaux et sont exclus de Git et de l’image Docker.

Deux méthodes sont disponibles :

1. Configurez `RSLM_ADMIN_KEY`, démarrez l’API et ajoutez des PDF depuis la barre latérale de Streamlit. L’interface applique la limite d’import configurée par l’API.
2. Placez les PDF autorisés dans `documents`, puis exécutez les étapes de préparation depuis la racine du projet :

   ```powershell
   python -m src.prepare_documents
   python -m src.create_chunks
   python -m src.create_embeddings
   python -m src.create_vector_db
   ```

Sans corpus initial, l’API démarre avec une collection Qdrant vide et ne présente pas de réponse documentaire sans sources. Le démarrage de l’application ne télécharge pas de documents à votre place.

## Docker Compose

Configurez d’abord `.env`, démarrez Ollama sur l’hôte et récupérez le modèle conversationnel. Puis :

```powershell
docker compose up --build
```

Compose démarre l’API et Qdrant. Leurs ports publiés sont limités à
`127.0.0.1` ; Ollama doit être accessible par Docker via
`host.docker.internal:11434`. Pour utiliser l’interface Streamlit depuis
l’hôte, installez les dépendances Python et définissez
`RSLM_API_URL=http://127.0.0.1:8080` dans l’environnement avant de la lancer.

Docker ne copie ni les PDF, ni les modèles téléchargés, ni les embeddings locaux. Si vous avez préparé votre corpus localement, l’index de Compose reste distinct et devra être chargé séparément.

## Configuration et confidentialité

Les paramètres se trouvent dans `.env.example`. Ne publiez jamais `.env`, une clé d’administration, des journaux, des sauvegardes, des conversations ou des documents privés.

`XAI_TRACE_ENABLED` est désactivé par défaut dans `.env.example`. Activez-le seulement si nécessaire. Les traces stockées dans `logs/xai_trace.jsonl` peuvent contenir des questions, de l’historique de conversation, des extraits de documents et des réponses.

Les journaux d’audit (`AUDIT_LOG_ENABLED`) et les journaux de diagnostic contenant des questions, requêtes de recherche et extraits (`RSLM_DEBUG_CONTENT_LOGS`) sont également désactivés par défaut. Ne les activez que pour un diagnostic local nécessaire ; protégez et supprimez ensuite les fichiers ou sorties concernés.

La clé d’administration protège les opérations d’administration du corpus, mais ne rend pas à elle seule une instance publique sûre. L’API de conversation n’est pas conçue comme un service Internet prêt pour la production : ne l’exposez pas à un réseau non fiable sans mettre en place authentification, HTTPS, contrôles d’accès et limites de ressources.

## Tests et évaluations

Lancer les tests unitaires :

```powershell
python -m unittest discover -s tests -v
```

Les évaluations de recherche et de réponses attendent des jeux de données dans `data/retrieval_eval.json` et `data/answer_eval.json`. Ils ne sont pas inclus dans le dépôt : créez des annotations adaptées à votre corpus local. Les scripts écrivent leurs résultats dans `logs`, également ignoré par Git.

Les métriques de couverture lexicale et de présence des sources sont des aides à l’évaluation, pas des preuves automatiques de vérité ou de fidélité. Pour interpréter la provenance et les limites des traces, voir [xai.md](xai.md).

## Licence

Le code source de ce projet est publié sous licence MIT ; voir [LICENSE](LICENSE). Cette licence ne s’étend pas aux documents fournis par les utilisateurs, aux modèles tiers, à leurs poids ou à leurs licences respectives.
