# Traçabilité et évaluation des citations

## Ce que conserve une trace

Lorsque `XAI_TRACE_ENABLED=true`, l’API écrit une trace JSONL locale par requête. Selon le résultat du traitement, elle peut contenir :

- la question, sa reformulation éventuelle et un historique conversationnel limité ;
- les passages candidats de Qdrant et leurs scores de similarité ;
- les scores de reranking ;
- le contexte documentaire sélectionné et transmis au modèle ;
- les références affichées et leur présence dans le contexte sélectionné ;
- la réponse et le statut du traitement.

La trace documente le parcours de recherche utilisé pour produire une réponse. Le pipeline actuel ne contient pas de graphe de connaissances ; il n’existe donc aucune provenance de parcours de graphe à enregistrer.

L'API renvoie aussi, indépendamment de l'enregistrement de traces XAI, un graphe de recherche pour chaque nouvelle réponse. Les interfaces React et Streamlit présentent les rangs et scores des candidats autorisés, les passages préparés pour le modèle et les termes du contrôle lexical. Pour un passage retenu, le graphe et les sources affichent le texte préparé pour le modèle ; les autres candidats restent des aperçus. Ce contrôle lexical utilise les textes retenus après application des limites de contexte ; la recherche Qdrant elle-même utilise des vecteurs. Le graphe ne montre pas le contenu des documents exclus ni des candidats d'une recherche refusée. Les extraits affichés sont stockés dans l'historique React non chiffré du navigateur et inclus dans l'export de conversation, ou dans l'historique local Streamlit. Les réponses antérieures restent inchangées.

## Ce que la trace ne prouve pas

La présence d’une source dans le contexte ne prouve pas que chaque affirmation de la réponse est étayée par cette source. Les références sont associées à la réponse, et non alignées automatiquement sur chacune de ses affirmations. Les scores de similarité et de reranking mesurent le classement des passages ; ils ne sont pas des probabilités de vérité.

Les scripts d’évaluation peuvent vérifier des faits et des références attendus à l’aide de règles lexicales et d’annotations propres à un corpus. Ces contrôles aident à suivre les régressions, mais ne remplacent ni une vérification humaine ni une évaluation sémantique de l’étayage.

## Méthode de revue recommandée

Pour évaluer la fidélité des citations sur un jeu de données autorisé :

1. Définir des questions représentatives et annoter les passages/pages attendus.
2. Vérifier si les sources affichées étaient réellement présentes dans le contexte transmis au modèle.
3. Relier manuellement chaque affirmation importante à l’extrait pertinent.
4. Classer l’extrait comme étayant, contredisant ou ne permettant pas de conclure.
5. Présenter séparément les résultats de récupération, de provenance, de couverture des affirmations et de fidélité revue.

Les jeux de données d’évaluation, les journaux et les traces ne sont pas fournis dans le dépôt. Ils peuvent révéler le contenu du corpus ou des conversations et doivent rester protégés.
