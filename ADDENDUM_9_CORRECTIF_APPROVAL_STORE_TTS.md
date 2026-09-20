# ADDENDUM 9 — CORRECTIF CRITIQUE : API `ApprovalStore` INCORRECTE + BACKEND TTS NON BRANCHÉ

**Diagnostic confirmé par lecture directe et comparaison ligne à ligne avec le fichier réel `src/openjarvis/tools/approval_store.py` (vérifié : un seul fichier de ce nom dans tout le projet, pas d'ambiguïté possible).**

Les deux nouveaux fichiers livrés pour l'Addendum 8 (`cerberus_conversational.py`, `prospection_agent.py`) utilisent une API `ApprovalStore` qui **n'existe nulle part dans le code** — une classe `ApprovalRequest` inexistante, une méthode `.add()` inexistante, une méthode `.get(id)` inexistante, des champs `summary`/`action_id` inexistants. En l'état, tout appel à un outil de ces deux agents plantera silencieusement (capturé par un `try/except` qui masque l'erreur en façade de succès partiel), et l'Orbe restera muette pour tout ce qui touche aux alertes, brouillons, et prospects.

---

## 1. L'API RÉELLE À UTILISER (extraite de `approval_store.py`, vérifiée exacte)

```python
from openjarvis.tools.approval_store import ApprovalStore, PendingAction, TIER_HIGH, TIER_MEDIUM, TIER_LOW, TIER_TRIVIAL

store = ApprovalStore()

# Créer une action en attente — retourne un PendingAction avec son .id généré
action: PendingAction = store.queue_action(
    action_type="prospection_first_contact",   # str
    description="[PROSPECTION] Nom du prospect — contact",  # str, remplace 'summary'
    payload={"name": ..., "source_url": ..., ...},  # Dict[str, Any]
    permission_key="prospection_first_contact:url:<source_url>",  # str — voir section 2
    tier=TIER_HIGH,  # str
    ttl_hours=24,  # optionnel
)
# action.id est l'identifiant réel (pas 'action_id')

# Récupérer une action précise par son id
found = store.get_action(action_id)
# found.description (pas .summary), found.tier, found.payload, found.id

# Lister toutes les actions en attente
items = store.list_pending()
```

**Différences à corriger dans les deux fichiers, point par point :**

| Ce qui est écrit actuellement (incorrect) | Ce qu'il faut utiliser à la place |
|---|---|
| `from ... import ApprovalRequest` | Ne pas importer `ApprovalRequest` — n'existe pas |
| `req = ApprovalRequest(agent_id=..., action_type=..., tier=..., payload=..., summary=...)` puis `store.add(req)` | `store.queue_action(action_type=..., description=..., payload=..., permission_key=..., tier=...)` directement — pas d'objet intermédiaire à construire |
| `store.get(email_id)` | `store.get_action(email_id)` |
| `item.summary` | `item.description` |
| `item.action_id` | `item.id` |

---

## 2. POINT D'ATTENTION SUPPLÉMENTAIRE — `permission_key` EST OBLIGATOIRE ET N'ÉTAIT JAMAIS FOURNI

`queue_action` exige un `permission_key` (paramètre sans valeur par défaut) — un champ que ni `cerberus_conversational.py` ni `prospection_agent.py` ne fournissaient dans leur tentative précédente, parce que leur `ApprovalRequest` imaginaire n'en avait pas besoin. C'est ce champ qui permet la mémoire de permission au niveau du framework — à construire de façon cohérente pour qu'un même type d'action produise toujours la même clé :

- Pour `cerberus_conversational.py` : `permission_key=f"conversational_{tool_name}:target:{draft_id_ou_identifiant_concerne}"`
- Pour `prospection_agent.py`, contact trouvé : `permission_key=f"prospection_first_contact:url:{source_url}"`
- Pour `prospection_agent.py`, opportunité signalée : `permission_key=f"prospection_opportunity_flagged:url:{source_url}"`

Ce format est cohérent avec le commentaire d'en-tête du fichier `approval_store.py` lui-même (`"{action_type}:{fingerprint}"`, avec l'exemple `"email_delete:domain:noreply.github.com"`) — donc pas une convention inventée ici, mais celle déjà documentée dans le fichier source qu'il fallait simplement lire avant d'écrire le code.

---

## 3. CORRECTIF PRÉCIS POUR `cerberus_conversational.py`

### 3.1 `ListAlertsTool.execute()`
Remplacer :
```python
items = store.list_pending()
lines = [f"- [{i.tier.upper()}] {i.summary}" for i in items[:10]]
```
Par :
```python
items = store.list_pending()
lines = [f"- [{i.tier.upper()}] {i.description} (id: {i.id})" for i in items[:10]]
```

### 3.2 `ListDraftsTool.execute()`
Remplacer :
```python
items = [i for i in store.list_pending() if "draft" in (i.action_type or "")]
lines = [f"- {i.action_id}: {i.summary}" for i in items[:10]]
```
Par :
```python
items = [i for i in store.list_pending() if "draft" in (i.action_type or "")]
lines = [f"- {i.id}: {i.description}" for i in items[:10]]
```

### 3.3 `ViewEmailTool.execute()`
Remplacer :
```python
item = store.get(email_id)
```
Par :
```python
item = store.get_action(email_id)
```
(le reste de la méthode reste inchangé, `item.payload` existe bien tel quel)

### 3.4 `_cerberus_confirm()`
Remplacer entièrement le bloc :
```python
from openjarvis.tools.approval_store import ApprovalRequest, ApprovalStore, TIER_HIGH
req = ApprovalRequest(
    agent_id=self.agent_id,
    action_type=f"conversational_{tool_name}",
    tier=TIER_HIGH,
    payload=args_dict,
    summary=f"[CERBERUS] {tool_name}: {json.dumps(args_dict, ensure_ascii=False)[:120]}",
)
store = ApprovalStore()
store.add(req)
logger.info("Queued conversational action %s.", req.action_id)
```
Par :
```python
from openjarvis.tools.approval_store import ApprovalStore, TIER_HIGH
store = ApprovalStore()
fingerprint = args_dict.get("draft_id") or args_dict.get("action_id") or "unspecified"
action = store.queue_action(
    action_type=f"conversational_{tool_name}",
    description=f"[CERBERUS] {tool_name}: {json.dumps(args_dict, ensure_ascii=False)[:120]}",
    payload=args_dict,
    permission_key=f"conversational_{tool_name}:target:{fingerprint}",
    tier=TIER_HIGH,
)
logger.info("Queued conversational action %s.", action.id)
```

---

## 4. CORRECTIF PRÉCIS POUR `prospection_agent.py`

### 4.1 `LogAndQueueProspectTool.execute()`
Remplacer :
```python
from openjarvis.tools.approval_store import ApprovalRequest, ApprovalStore, TIER_HIGH
req = ApprovalRequest(
    agent_id="prospection_agent",
    action_type="prospection_first_contact",
    tier=TIER_HIGH,
    payload={...},
    summary=f"[PROSPECTION] {name} — {contact}",
)
store = ApprovalStore()
store.add(req)
```
Par :
```python
from openjarvis.tools.approval_store import ApprovalStore, TIER_HIGH
store = ApprovalStore()
action = store.queue_action(
    action_type="prospection_first_contact",
    description=f"[PROSPECTION] {name} — {contact}",
    payload={
        "name": name,
        "source_url": source_url,
        "source_excerpt": source_excerpt,
        "contact": contact,
        "draft_message": draft_message,
    },
    permission_key=f"prospection_first_contact:url:{source_url}",
    tier=TIER_HIGH,
)
```
(le message de retour de la fonction peut mentionner `action.id` si utile pour Akim)

### 4.2 `FlagOpportunityWithoutContactTool.execute()`
Même correction, avec `action_type="prospection_opportunity_flagged"`, `tier=TIER_MEDIUM`, et `permission_key=f"prospection_opportunity_flagged:url:{source_url}"`.

---

## 5. SECOND PROBLÈME CONFIRMÉ, INDÉPENDANT DU PREMIER — BACKEND TTS JAMAIS INSTANCIÉ

### 5.1 Constat exact
`src/openjarvis/speech/_discovery.py` ne connaît que des backends de **transcription** (`faster-whisper`, `openai`, `deepgram` — son propre docstring le confirme : "Auto-discover available speech-**to-text** backends"). `KokoroTTSBackend` (dans `speech/kokoro_tts.py`, qui expose bien une méthode `.synthesize()`) n'apparaît nulle part dans ce fichier de découverte.

Or `src/openjarvis/cli/serve.py` (ligne ~475) appelle `get_speech_backend(config)` et passe le résultat **unique** à `create_app(..., speech_backend=speech_backend, ...)`, qui stocke cet objet unique dans `app.state.speech_backend` (`server/app.py` ligne 226) — objet utilisé à la fois par la route `/v1/speech/transcribe` **et** par la route `/v1/speech/synthesize` (`server/api_routes.py` ligne 934, `backend.synthesize(...)`). Un objet `FasterWhisperBackend` n'a pas de méthode `.synthesize()` → `AttributeError` immédiate dès le premier appel de synthèse vocale.

### 5.2 Correctif requis
Le serveur a besoin de **deux objets backend distincts** stockés séparément (par exemple `app.state.stt_backend` et `app.state.tts_backend`), pas un seul `speech_backend` partagé :

1. Dans `src/openjarvis/speech/_discovery.py`, ajouter une fonction séparée `get_tts_backend(config)` qui découvre/instancie un backend TTS (`kokoro` en priorité, cohérent avec le choix déjà fait dans `morning_digest.py` qui utilise `"cartesia"` par défaut — à clarifier avec Akim si `kokoro` ou `cartesia` est préféré, les deux backends existent déjà dans `src/openjarvis/speech/`)
2. Dans `src/openjarvis/cli/serve.py`, appeler cette nouvelle fonction en plus de `get_speech_backend`, et passer les deux résultats séparément à `create_app`
3. Dans `src/openjarvis/server/app.py`, stocker les deux objets sous des noms distincts (`app.state.stt_backend`, `app.state.tts_backend`) plutôt qu'un seul `speech_backend` ambigu
4. Mettre à jour les deux routes (`transcribe_speech` et `synthesize_speech` dans `server/api_routes.py`) pour lire chacune le bon attribut (`request.app.state.stt_backend` pour la transcription, `request.app.state.tts_backend` pour la synthèse)

---

## 6. VÉRIFICATION À FAIRE APRÈS CORRECTION (obligatoire avant nouvelle livraison)

Cette fois, demander explicitement à Antigravity de fournir la preuve d'exécution, pas seulement l'affirmation que c'est corrigé :
1. Écrire un test unitaire minimal pour chacun des deux agents (`test_cerberus_conversational.py`, `test_prospection_agent.py`) qui instancie réellement `ApprovalStore` (base SQLite temporaire) et vérifie qu'un appel à chaque outil ne lève aucune exception
2. Lancer `pytest` sur ces nouveaux tests et coller la sortie complète dans la réponse, pas juste "les tests passent"
3. Vérifier manuellement, en lançant le serveur localement, qu'un appel à `POST /v1/speech/synthesize` avec un texte simple renvoie bien un flux audio et non une erreur 500
