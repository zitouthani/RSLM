# Instructions de développement

Ces instructions s'appliquent aux contributions à RSLM. Lire aussi
[`securite.instructions.md`](securite.instructions.md) avant de modifier les
entrées utilisateur, l'API, le stockage, l'indexation ou la configuration.

## Présentation du projet

RSLM est un assistant documentaire local composé d'une interface
Streamlit, d'une API FastAPI, de Qdrant et d'Ollama. Le projet est structuré
ainsi :

- `src/app_stream.py` : interface Streamlit et appels à l'API.
- `src/api_stream3.py` : API, recherche documentaire, génération et
  administration du corpus.
- `src/retrieval.py`, `src/qdrant_connection.py` et
  `src/document_indexer.py` : recherche et indexation.
- `src/backup_store.py`, `src/chat_store.py` et `src/xai_trace.py` :
  persistance, sauvegardes et provenance.
- `tests/` : tests unitaires.
- `site/` : site statique de présentation en français et en anglais.

Les PDF, modèles téléchargés, journaux, conversations, sauvegardes et index
sont des données locales. Ils ne font pas partie des sources à versionner.

## Environnement local

Prérequis : Python 3.11 ou plus récent et Ollama installé. Depuis la racine du
projet, sous PowerShell :

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
Copy-Item .env.example .env
ollama pull qwen2.5:1.5b
```

Configurez les paramètres locaux dans `.env`. Ne copiez aucune valeur secrète
dans les sources, la documentation, les tests ou les journaux.

Démarrer l'API et Streamlit dans deux terminaux :

```powershell
python -m uvicorn src.api_stream3:app --host 127.0.0.1 --port 8080
```

```powershell
$env:RSLM_API_URL = "http://127.0.0.1:8080"
python -m streamlit run src\app_stream.py
```

## Modifications et style

- Garder les changements ciblés et respecter les structures et helpers déjà
  présents.
- Préférer des fonctions explicites et typées aux conversions ou valeurs de
  repli silencieuses.
- Conserver les messages destinés à l'utilisateur en français, sauf lorsque
  l'interface existante requiert une autre langue.
- Garder l'interface Streamlit accessible : libellés de widgets explicites,
  éléments natifs en priorité, clés stables pour les widgets persistants.
- Ne pas ajouter de PDF, jeu d'évaluation privé, modèle ou capture d'écran
  provenant de données réelles sans autorisation claire.
- Mettre à jour README et instructions si le lancement, la configuration ou
  les garanties de confidentialité changent.

## Tests

Avant de soumettre un changement :

```powershell
python -m unittest discover -s tests -v
python -m compileall -q src tests
docker compose config --quiet
```

Ajouter ou mettre à jour des tests pour tout changement de logique métier,
d'indexation, de stockage, de sauvegarde ou de provenance. Ne pas lancer les
tests de génération contre des services distants ou un corpus personnel par
défaut.

## Documentation et site

- Maintenir `README.md` en français et `README.en.md` en anglais ; ajouter un
  lien vers l'autre langue et vers l'index des 23 langues à chaque fichier.
- Garder les guides détaillés et le site en français et anglais. Les README
  traduits dans `docs/readme/` sont des résumés ; mettre à jour l'index des
  langues et les liens quand un fichier est ajouté ou renommé.
- Maintenir les pages `site/fr/index.html` et `site/en/index.html` cohérentes
  entre elles. Le sélecteur de langue doit mener à la page équivalente et la
  liste des README traduits doit correspondre à `docs/readme/README.md`.
- Le site décrit un projet local et expérimental, pas un service hébergé ou
  prêt pour la production.
- Le déploiement GitHub Pages se fait via
  `.github/workflows/pages.yml`. La branche de publication est `main`.
- Le site doit rester statique et ne doit pas intégrer de clés, de corpus, de
  journaux privés ou de configuration provenant de `.env`.

## Publications

- Ne créer ni commit ni dépôt distant sans demande explicite.
- Avant toute publication, examiner `git status` et `git diff --cached` :
  l'index Git peut contenir des changements préparés par l'utilisateur.
- Vérifier que `.env`, les PDF, `data/`, `models/`, `logs/`, `trash/` et les
  sauvegardes ne sont pas suivis par Git.
- Respecter les licences propres aux dépendances, modèles, logos et
  documents. La licence MIT du projet ne s'applique pas aux contenus tiers.
