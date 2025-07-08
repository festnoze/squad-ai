# Documentation des endpoints RAG (Retrieval-Augmented Generation)

## Endpoints stateless (sans gestion de conversation)

### 1. `POST /no-conversation/ask-question`
- **Nom interne :** `rag_query_no_conversation_async`
- **Description :**
  Ce endpoint permet de soumettre une question à l'IA sans gestion d'historique ou de contexte conversationnel. Il est conçu pour des appels directs, indépendants, où chaque requête est traitée comme isolée.
- **Corps de la requête :**

```json
{
  "query": "Quel est le capital de la France ?",
  "type": "web",
  "user_name": "visiteur_anon"
}
```
- **Schéma attendu :**
  - `query` *(str)* : La question à poser.
  - `type` *(str)* : Type de device ou plateforme (ex : "web", "mobile", etc.).
  - `user_name` *(str)* : Nom d'utilisateur (peut être générique ou anonyme).

- **Exemple d’appel HTTP :**

```http
POST /no-conversation/ask-question HTTP/1.1
Content-Type: application/json

{
  "query": "Quels sont les avantages du machine learning ?",
  "type": "web",
  "user_name": "demo_user"
}
```

- **Réponse :**
  - Statut : `200 OK`
  - Corps : Réponse générée par l’IA (JSON)

---

### 2. `POST /no-conversation/ask-question/stream`
- **Nom interne :** `rag_query_no_conversation_streaming_async`
- **Description :**
  Identique au endpoint précédent, mais la réponse est renvoyée en streaming (SSE `text/event-stream`).
  Utile pour afficher la réponse au fur et à mesure de sa génération.

- **Corps de la requête :**
  Identique à `/no-conversation/ask-question` :

```json
{
  "query": "Explique le concept de RAG en IA.",
  "type": "web",
  "user_name": "stream_user"
}
```

- **Réponse :**
  - Statut : `200 OK`
  - Corps : Flux d’événements texte (SSE) avec la réponse générée en temps réel.

---

## Mode stateful (gestion de conversation)
Pour prendre en charge l’historique conversationnel et un suivi utilisateur, il faut utiliser le workflow suivant :

1. **Créer ou retrouver l’utilisateur :**
   - Endpoint : `create_or_retrieve_user`
   - Permet d’obtenir un `user_id` unique.
2. **Créer une nouvelle conversation :**
   - Endpoint : `create_new_conversation`
   - Nécessite le `user_id` obtenu précédemment.
   - Retourne un `conversation_id`.
3. **Soumettre une requête dans la conversation :**
   - Endpoint : `rag_query_stream_async`
   - Le body doit inclure le `conversation_id` (voir modèle `QueryAskingRequestModel`).

### Exemple de body pour `rag_query_stream_async` :

```json
{
  "conversation_id": "123e4567-e89b-12d3-a456-426614174000",
  "user_query_content": "Peux-tu me rappeler le sujet précédent ?",
  "display_waiting_message": true
}
```
- **Schéma attendu :**
  - `conversation_id` *(UUID)* : Identifiant de la conversation.
  - `user_query_content` *(str)* : Question à poser.
  - `display_waiting_message` *(bool)* : Afficher un message d’attente (optionnel).

---

## Résumé
- Utilisez les endpoints `/no-conversation/ask-question` et `/no-conversation/ask-question/stream` pour des appels directs, sans gestion d’historique (stateless).
- Pour une expérience conversationnelle avec historique, passez par la séquence : `create_or_retrieve_user` → `create_new_conversation` → `rag_query_stream_async`.
- Les modèles de requête sont documentés dans le code source, notamment dans `src/facade/request_models/query_asking_request_model.py`.

---

*Dernière mise à jour : 07/07/2025*