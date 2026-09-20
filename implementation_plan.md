# ADDENDUM TECHNIQUE — CERBERUS V1

Ce document détaille le plan technique pour l'implémentation complète et la validation end-to-end de CERBERUS V1, conformément à tes instructions de l'Addendum 10. L'objectif est d'assurer que toutes les briques fonctionnent de manière interconnectée et fiable.

## Open Questions

> [!WARNING]
> **Scopes Gmail OAuth**
> Actuellement, `gmail.py` utilise `https://www.googleapis.com/auth/gmail.readonly`. Pour pouvoir envoyer des réponses et modifier des brouillons, nous devons passer à `https://www.googleapis.com/auth/gmail.modify` ou `https://mail.google.com/`. Es-tu d'accord pour que je modifie les scopes par défaut et que cela nécessite une re-validation OAuth de ta part après le déploiement ?

> [!WARNING]
> **Base de données de Mémoire Relationnelle & Journal**
> Le plan prévoit d'ajouter les tables de `RelationalMemory` (pour les prospects et la confiance) et `DecisionJournal` directement dans `approvals.db` pour simplifier les requêtes, ou dans un nouveau `cerberus.db`. Es-tu d'accord avec l'utilisation de SQLite via l'existant ou préfères-tu un fichier séparé ? (Je propose de tout centraliser dans `approvals.db`).

## Proposed Changes

---

### 1. Architecture & Routage (Priorités 1, 3, 4)

#### [MODIFY] `src/openjarvis/server/routes.py`
- **Routing d'Agent** : Modification de la route `/v1/chat/completions` (et des flux streamés) pour résoudre dynamiquement l'agent. Si `request_body.model` correspond à un agent enregistré (ex. `cerberus_conversational`), instancier ou récupérer cet agent au lieu d'utiliser l'agent par défaut de `app.state`.
- **Mémoire de Conversation** : S'assurer que le `conversation_id` est correctement passé ou que l'historique est reconstruit via les `messages` envoyés par le frontend, afin que les références ("Il" / "Ce client") fonctionnent sans perdre le contexte.

---

### 2. Connecteur Gmail & Envoi (Priorités 3, 6, 7, 26)

#### [MODIFY] `src/openjarvis/connectors/gmail.py`
- Mise à jour du `_GMAIL_SCOPE` pour inclure les droits d'écriture/envoi.
- Ajout de `_gmail_api_send_message` et `_gmail_api_reply_to_thread` via l'endpoint `messages.send`.
- Intégration de l'encodage base64 MIME pour l'envoi de messages.
- Gestion propre de l'idempotence et des erreurs (timeout, auth, rate limit) lors de l'envoi.

---

### 3. Système d'Approbation & Exécuteur (Priorités 4, 8, 19, 30)

#### [MODIFY] `src/openjarvis/tools/approval_store.py`
- Mise à jour des statuts pour supporter `approved`, `rejected`, `failed`.
- Ajout de la table `decision_journal` pour enregistrer l'historique complet des actions avec les raisons (`RULE_PRICE_NEGOTIATION`, etc.).
- Création d'une fonction `execute_action(action)` qui fera office de routeur/executor (appel de `gmail.send`, etc.) et gérera l'idempotence pour éviter les envois en double.

#### [MODIFY] `src/openjarvis/agents/cerberus_conversational.py`
- Modification de `ValidateActionTool` et `EditDraftTool` : ces outils ne seront plus interceptés et "bloqués" par `_cerberus_confirm`. Ils appelleront **réellement** `store.update_status(id, "approved")` (ce qui déclenchera l'Executor) ou modifieront le champ `payload['draft']` du brouillon dans la DB.

---

### 4. Moteur de Règles & Mémoire Relationnelle (Priorités 5, 9-16)

#### [NEW] `src/openjarvis/core/cerberus_rules.py`
- **RelationalMemory** : Nouvelle abstraction (SQLite) pour gérer la base de contacts (id, statut liste rouge/grise/blanche, compteur d'échanges validés).
- **RulesEngine** : Un module vérifiant le contenu de l'action contre les mots-clés bloquants (contrat, urgent, exclusivité), les grilles tarifaires strictes (Arduino, IA), et l'état relationnel du contact.
- Retourne `AUTO_EXECUTE`, `REQUIRES_APPROVAL`, ou `BLOCKED`. Les actions non-autorisées finissent dans l'`ApprovalStore` avec `tier=HIGH` ou `MEDIUM`.

---

### 5. Prospection Autonome & Briefing (Priorités 6, 7, 17, 20-23)

#### [MODIFY] `src/openjarvis/agents/prospection_agent.py`
- Vérification de l'enregistrement correct (`AgentRegistry.register`).
- Ajout du suivi complet du statut (NEW, CONTACT_PENDING, etc.) dans une table SQLite.
- S'assurer que le premier contact passe par l'Executor (via `prospection_first_contact`) et n'invente jamais d'informations (déjà partiellement cadré par Addendum 8).

#### [NEW] `src/openjarvis/tools/cerberus_briefing.py`
- Création de l'outil `GetBriefingTool` accessible par `cerberus_conversational`.
- Interrogation de `ApprovalStore` (statistiques pending/approved/failed) et `RelationalMemory` pour générer un résumé de l'absence d'Akim.

---

### 6. Tests End-to-End (Priorités 8, 31, 32)

#### [NEW] `tests/agents/test_cerberus_e2e.py`
- Implémentation des Tests A à G décrits dans l'Addendum 10 :
  - **A** : Conversation vocale.
  - **B** : Email simple autorisé (auto-send Mock).
  - **C** : Email nécessitant validation (prix hors grille).
  - **D** : Institution (reste en validation).
  - **E** : Urgence (bloque l'autonomie).
  - **F** : Prospection (recherche → validation → envoi).
  - **G** : Briefing complet.

---

## Verification Plan

1. **Automated Tests** : Exécution de `pytest` sur les tests E2E et unitaires pour prouver que les règles de tarification, d'urgence et les listes (rouge/grise/blanche) fonctionnent.
2. **Manual Verification** : On vérifiera la boucle complète sur une instance de test `openjarvis serve` pour garantir que Gmail s'authentifie, qu'un mail PENDING passe à APPROVED via l'UI ou la voix, et qu'il est réellement envoyé. Un rapport de validation final sera rempli selon tes critères de la section 37.
