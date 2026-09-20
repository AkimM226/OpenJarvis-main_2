# ADDENDUM 8 — RENDRE LA V1 RÉELLEMENT FONCTIONNELLE
## Câblage complet de l'Orbe, création du module de prospection, complétion des grilles tarifaires

**Constat de l'audit (vérifié par lecture directe du code livré, `OpenJarvis-main_1.zip`) :** la livraison actuelle est une coquille partiellement assemblée. Les briques nécessaires existent presque toutes déjà dans OpenJarvis, mais **rien n'est câblé ensemble**. Ce document liste, pour chaque manque, la brique existante à réutiliser (déjà vérifiée dans le code) et le câblage précis à faire — pour qu'Antigravity assemble plutôt que reconstruise.

---

## 1. CHANTIER CRITIQUE N°1 — CÂBLER L'ORBE À UNE VRAIE CONVERSATION

### 1.1 Constat exact
`frontend/src/pages/OrbePage.tsx`, ligne 42 : le texte transcrit de la voix d'Akim est envoyé à `console.log("Transcribed:", text)` — et s'arrête là. Aucun appel à un agent, aucune réponse, aucune synthèse vocale. C'est un enregistreur vocal sans destination, pas un assistant conversationnel.

### 1.2 Ce qui existe déjà et doit être réutilisé (vérifié dans le code)
- **`src/openjarvis/agents/orchestrator.py`** — `OrchestratorAgent`, boucle multi-tours avec function calling déjà fonctionnelle (mode `"function_calling"` par défaut), gère nativement les tours d'outils sans qu'il soit nécessaire de la réécrire
- **`src/openjarvis/agents/_stubs.py`**, classe `ToolUsingAgent` — expose déjà un mécanisme `interactive=True` + `confirm_callback` transmis à `ToolExecutor` (dans `src/openjarvis/tools/_stubs.py`, ligne 210-221) qui bloque l'exécution d'un outil tant qu'un callback de confirmation n'a pas renvoyé `True`. **C'est l'équivalent natif exact du protocole de confirmation de CERBERUS** — ne pas en recoder un autre
- **`src/openjarvis/server/routes.py`**, endpoint `POST /v1/chat/completions` (ligne 104), avec `_handle_agent` (ligne 442) qui route déjà vers un agent avec ses outils
- **`src/openjarvis/speech/`** — trois backends TTS déjà implémentés (`cartesia_tts.py`, `kokoro_tts.py`, `openai_tts.py`), mais **aucun n'est exposé par une route API** (seul `/v1/speech/transcribe` existe dans `server/api_routes.py`, aucun endpoint `/v1/speech/synthesize` ou équivalent)

### 1.3 Câblage précis à effectuer

**Backend :**
1. Ajouter une route `POST /v1/speech/synthesize` dans `server/api_routes.py`, sur le modèle exact de `transcribe_speech` (même fichier, lignes ~879-910) : reçoit un texte, appelle le backend TTS déjà configuré (`kokoro_tts.py` recommandé en premier choix — vérifier sa licence et sa qualité en français avant de trancher, sinon utiliser le backend déjà configuré par défaut dans le projet), renvoie l'audio généré
2. Créer un agent dédié à la conversation orale d'Akim — par exemple `cerberus_conversational` — basé sur `OrchestratorAgent`, avec `interactive=True` et un `confirm_callback` qui écrit une entrée dans `ApprovalStore` (au lieu de bloquer une boucle synchrone) pour rester cohérent avec le fonctionnement asynchrone déjà en place pour `proactive_agent.py`
3. Doter cet agent des outils suivants (déclarés comme `BaseTool`, format déjà utilisé ailleurs dans le projet) : consulter le briefing du jour, lister les alertes en attente, lister les brouillons en attente, voir le contexte d'un email (texte original), suggérer des variantes de réponse, éditer un brouillon selon une instruction, valider/rejeter une action en attente — repris directement du contenu déjà spécifié dans l'Addendum 6 pour CERBERUS, à réécrire sous la forme d'outils OpenJarvis plutôt que d'outils Gemini natifs (le principe reste identique, seul le format de déclaration change)

**Frontend :**
4. Ajouter une fonction `sendChatMessage(text: string)` dans `frontend/src/lib/api.ts`, qui appelle `POST /v1/chat/completions` en pointant vers l'agent `cerberus_conversational` — cette fonction n'existe pas actuellement, à créer entièrement
5. Ajouter une fonction `synthesizeSpeech(text: string)` dans le même fichier, qui appelle la nouvelle route backend du point 1
6. Dans `OrbePage.tsx`, remplacer `console.log("Transcribed:", text)` (ligne 42) par : appel à `sendChatMessage(text)` → réception de la réponse → appel à `synthesizeSpeech(response)` → lecture audio de la réponse dans le navigateur (`Audio` API standard) → mise à jour visuelle de l'orbe vers l'état "réponse" pendant la lecture

### 1.4 Garde-fou impératif pour ce chantier
Le `confirm_callback` de l'agent conversationnel ne doit **jamais** être configuré pour auto-approuver — toute action proposée par cet agent en conversation avec Akim (valider un brouillon, résoudre une alerte) doit repasser par le mécanisme d'attente déjà utilisé pour les notifications du `proactive_agent.py`, exactement comme demandé dans les addendums précédents pour CERBERUS. La conversation peut *proposer* une action, jamais l'*exécuter* sans confirmation distincte.

---

## 2. CHANTIER CRITIQUE N°2 — CRÉER LE MODULE DE PROSPECTION (INEXISTANT)

### 2.1 Constat exact
Aucun fichier, aucune mention, aucune trace du mot "prospection" ou "prospect" dans l'ensemble du code livré. C'est une fonctionnalité demandée dès le tout premier message de cette conversation ("aller à la recherche d'opportunités"/"recherche de clients de manière autonome") et elle n'a jamais été construite, dans aucune des versions précédentes (CERBERUS ou OpenJarvis).

### 2.2 Décision actée par Akim : recherche web réelle et autonome
Pour rappel (Addendum 1, section sur le module de prospection de CERBERUS) : un audit antérieur avait révélé que la première tentative de CERBERUS générait des prospects **fictifs et inventés** — un risque réel de contacter des adresses inexistantes ou des tiers sans rapport. Akim a choisi de viser malgré tout la recherche web réelle et autonome, plus proche de l'ambition initiale, en acceptant que ce soit le mode le plus long à sécuriser correctement.

**Ce que "recherche web réelle" règle, et ce que ça ne règle pas.** Utiliser un vrai outil de recherche web garantit que les résultats consultés existent réellement — mais ne garantit **rien** sur ce que le LLM en déduit ensuite. Le risque résiduel n'est plus "le LLM invente une recherche", mais "le LLM lit un résultat vague (ex: mention d'une institution sans email affiché) et complète ou déduit une adresse plausible qu'il n'a jamais réellement vue". C'est le même mécanisme d'hallucination que celui déjà rencontré et corrigé pour la transcription vocale (Addendum 4) — un modèle génératif complète toujours quelque chose plutôt que de renvoyer une absence de résultat.

**Architecture retenue :** créer un nouvel agent `prospection_agent.py` dans `src/openjarvis/agents/`, sur le modèle de `proactive_agent.py`, utilisant l'outil de recherche web déjà disponible dans le framework (repéré dans l'audit : `build_web_search_tool`, présent dans plusieurs agents existants, par exemple `src/openjarvis/agents/hybrid/toolorchestra.py`) pour chercher des opportunités réelles (annuaires d'entreprises à Bobo-Dioulasso/Ouagadougou, appels à projets, hackathons, institutions éducatives).

### 2.3 Garde-fou non négociable — aucune coordonnée sans preuve d'extraction directe
Le point le plus critique de ce chantier : **toute adresse email, numéro de téléphone, ou coordonnée de contact proposée par l'agent doit être accompagnée du passage exact du résultat de recherche d'où elle a été extraite** (citation directe du texte source, pas un résumé ni une reformulation). Concrètement :
- Le prompt système de cet agent doit interdire explicitement au LLM de déduire, compléter, ou construire une adresse à partir d'un nom d'organisation ou d'un domaine probable — seule une coordonnée qui apparaît textuellement dans un résultat de recherche est utilisable
- Chaque prospect proposé dans la file d'attente doit inclure un champ `source_excerpt` (l'extrait exact contenant la coordonnée) et `source_url`, pour qu'Akim puisse vérifier lui-même avant tout envoi — jamais de prospect sans ces deux champs remplis
- Si aucune coordonnée directement citée n'est trouvée pour une opportunité par ailleurs intéressante (ex: un hackathon repéré mais sans email de contact affiché), l'agent doit la signaler comme "opportunité identifiée, contact à trouver manuellement" plutôt que de risquer d'inventer un contact

### 2.3 Garde-fous non négociables pour ce nouvel agent
- Toute action de premier contact générée par cet agent est **toujours** en tier `high` — jamais d'auto-approbation, quel que soit ce que le LLM propose (repasse par `apply_commercial_rules` avec un nouvel `action_type` dédié, par exemple `prospection_first_contact`)
- Le message de premier contact ne doit jamais contenir de prix ferme (reprise du principe déjà acté dans l'Addendum 7 pour CERBERUS) — la grille tarifaire n'intervient qu'une fois le besoin qualifié par un échange réel
- Chaque prospect contacté est journalisé (source, date, contenu du message) pour éviter les contacts en double

---

## 3. CHANTIER CRITIQUE N°3 — COMPLÉTER `commercial_rules.py` AVEC LES VRAIES GRILLES TARIFAIRES

### 3.1 Constat exact
Le fichier `src/openjarvis/security/commercial_rules.py` livré ne contient que des mots-clés d'alerte génériques et une logique "si trivial/low alors forcer high" pour les catégories de prix — **aucun des seuils numériques déjà validés n'a été porté**.

### 3.2 Grilles à intégrer, rappel exact (déjà verrouillées dans les tout premiers échanges de cette conversation)

**Formation Arduino :**
- Prix de référence : 30 000 FCFA/participant — Prix plancher absolu : 15 000 FCFA/participant
- Seuil "groupe important" : ≥ 20 participants → dégressivité vers le plancher
- Critères de réduction cumulables : structure vient à nous / institution partenaire ou client récurrent

**Formations IA :**
| Pack | Prix référence | Prix réduit (≥10 pers.) | Séances max incluses |
|---|---|---|---|
| Initiation | 15 000 FCFA | Inchangé, aucune réduction | 2 séances × 2h |
| Professionnel | 30 000 FCFA | 25 000 FCFA | 3 séances max |
| Dev (vibe coding) | 30 000 FCFA | 27 000 FCFA | 3 séances max |

### 3.3 Fonction à ajouter dans `commercial_rules.py`
Une nouvelle fonction, par exemple `validate_price_in_payload(action_type, payload) -> bool`, appelée par `apply_commercial_rules` avant de renvoyer le tier final : si le `payload` contient un prix explicite proposé par le brouillon généré, cette fonction vérifie qu'il respecte la grille ci-dessus (selon le service détecté et les critères de modulation présents dans le texte). Si le prix est en dehors des bornes autorisées, **forcer le tier à `high` sans exception**, quelle que soit la décision du LLM — reprise exacte du principe déjà établi dans les tout premiers addendums de CERBERUS (`rules.py`), jamais affaibli par le changement de framework.

---

## 4. RÉCAPITULATIF ET ORDRE DE TRAITEMENT

1. **Chantier 1 (Orbe conversationnelle)** — le plus visible et le plus attendu par Akim, à traiter en premier
2. **Chantier 3 (grilles tarifaires)** — critique pour la sécurité commerciale, peut être traité en parallèle du chantier 1 car il touche un fichier différent
3. **Chantier 2 (prospection en recherche web réelle)** — le plus long à sécuriser correctement du fait du garde-fou anti-hallucination (section 2.3), à traiter en dernier ou en parallèle si les ressources le permettent
