# Instructions de sécurité

Ces règles s'appliquent à toute contribution. En cas de conflit, privilégier
la protection des données et ne pas assouplir un contrôle sans justification
et tests explicites.

## Secrets et configuration

- Ne jamais écrire, afficher, journaliser, committer ou intégrer une clé,
  un mot de passe, un jeton, une clé privée ou une valeur réelle de `.env`.
- Lire les noms des variables de configuration sans imprimer leurs valeurs.
- Utiliser `.env.example` uniquement avec des valeurs vides ou manifestement
  fictives ; `.env` reste local.
- Ne jamais ajouter de secret dans le code HTML du site, le workflow Pages,
  les images Docker ou les tests.

## Données documentaires et conversations

- Les PDF, extraits de texte, embeddings, index vectoriels, jeux d'évaluation,
  conversations, retours, journaux, traces XAI et sauvegardes peuvent être
  sensibles ou protégés par le droit d'auteur.
- Les données réelles restent hors de Git et des images Docker par défaut.
- Ne pas utiliser un corpus local pour produire des exemples, des captures,
  des rapports ou des métriques publics sans autorisation.
- Toute publication d'un corpus de démonstration doit confirmer les droits de
  redistribution et documenter sa provenance.
- Les traces XAI peuvent contenir les questions, l'historique, les passages
  retrouvés et les réponses ; leur collecte est désactivée par défaut.
- Les journaux d'audit (`AUDIT_LOG_ENABLED`) et les diagnostics contenant des
  questions, des requêtes ou des extraits (`RSLM_DEBUG_CONTENT_LOGS`) sont
  désactivés par défaut ; toute activation doit être temporaire et locale.

## API et interface

- Considérer les entrées de l'API et les noms de fichiers comme non fiables.
- Valider types, tailles, formats et chemins côté serveur. Les contrôles
  d'interface ne remplacent pas la validation de l'API.
- Utiliser des requêtes paramétrées pour les accès SQL et des comparaisons
  sûres pour les clés d'administration.
- Éviter d'afficher du HTML non assaini ou d'exécuter du contenu fourni par
  les utilisateurs ou les documents.
- Ne pas exposer l'API, Qdrant ou leurs routes d'administration sur un réseau
  public sans authentification, autorisation, HTTPS, limites de débit et
  configuration de déploiement adaptée.
- CORS n'est pas un contrôle d'accès. Garder `RSLM_ALLOWED_ORIGINS` limité
  aux origines locales ; n'autoriser une origine publique qu'avec une
  authentification et une autorisation côté serveur.
- Une clé d'administration ne protège pas automatiquement les routes de chat,
  les journaux, les fichiers PDF servis ou le serveur lui-même.

## Stockage, sauvegardes et erreurs

- Ne pas supprimer ni remplacer un document, un vecteur ou une sauvegarde sans
  vérifier l'identité de la ressource et le comportement de restauration.
- Ne pas masquer les erreurs par des résultats vides ou un succès apparent.
- Ne jamais inclure dans les exceptions renvoyées au client des chemins
  internes, des secrets ou le contenu privé du corpus.
- Garder les fichiers de sauvegarde et les journaux hors de Git et appliquer
  une conservation appropriée aux données.

## Vérification avant publication

Avant toute publication, vérifier le dépôt et l'archive :

1. Examiner `git status`, `git diff --cached` et la liste des fichiers suivis.
2. Confirmer l'exclusion de `.env`, PDF, `data/`, `models/`, `logs/`,
   `trash/`, environnements et sauvegardes.
3. Vérifier l'absence de clés, d'informations personnelles, de données
   utilisateur, de documents tiers et de journaux dans les fichiers ajoutés.
4. Tester les règles `.gitignore` et `.dockerignore`, puis les tests du projet.

Si un secret a été publié, le révoquer ou le renouveler immédiatement ; retirer
le fichier dans un commit ultérieur ne rend pas le secret sûr.

## Signalement responsable

Ne pas publier de détails exploitables d'une vulnérabilité non corrigée dans
une issue publique. Préparer d'abord un rapport privé avec le composant
concerné, l'impact et les étapes minimales de reproduction, sans joindre de
secrets ni de données réelles. En l'absence de canal privé configuré pour ce
projet, contacter le mainteneur avant toute divulgation publique.
