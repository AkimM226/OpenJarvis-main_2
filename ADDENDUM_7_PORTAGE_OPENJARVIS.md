# ADDENDUM 7 — PORTAGE COMPLET DE CERBERUS VERS OPENJARVIS

**Décision actée par Akim :** abandonner l'itération continue sur la base de code custom (CERBERUS/Antigravity) et reconstruire le projet sur le framework **OpenJarvis** (Stanford Hazy Research / Scaling Intelligence Lab, licence Apache 2.0), qui offre déjà une architecture mature d'agent personnel local-first : approbations à plusieurs niveaux, agent proactif planifié, connecteurs Gmail, app desktop Tauri, agents de surveillance continue et de briefing vocal.

**Principe directeur du portage :** ne pas réécrire ce qu'OpenJarvis fournit déjà correctement. Documenter précisément ce qui doit être ajouté, adapté, ou verrouillé pour que le comportement spécifique et les garde-fous de CERBERUS (grilles tarifaires, mots-clés d'alerte, règle méta de prudence) survivent au changement de fondation.

---

## 1. CE QU'OPENJARVIS FOURNIT DÉJÀ (vérifié par lecture directe du code, pas supposé)

| Composant CERBERUS (à construire à la main) | Équivalent OpenJarvis (déjà existant) | Fichier vérifié |
|---|---|---|
| Liste rouge/grise/blanche par contact | Système de tiers (`trivial/low/medium/high`) + `permission_key` par pattern + mémoire des décisions (`ApprovalStore`) | `src/openjarvis/tools/approval_store.py` |
| Boucle de traitement mail ponctuelle / daemon à construire | `proactive_agent.py` — cron quotidien natif (5h du matin par défaut, configurable), déjà conçu pour tourner sans intervention | `src/openjarvis/agents/proactive_agent.py` |
| Dashboard web fait maison + PyWebView à stabiliser | Application desktop **Tauri**, plus mature et plus robuste que PyWebView pour la gestion de fenêtre | `desktop/src-tauri/`, `frontend/` |
| VOX (briefing vocal) à construire de zéro | Agent `morning_digest` avec sortie TTS déjà prévue dans l'architecture | `src/openjarvis/agents/morning_digest.py` |
| Agent de surveillance continue à spécifier | `monitor_operative.py` — agent continu avec mémoire, compression, récupération | `src/openjarvis/agents/monitor_operative.py` |
| Connecteur Gmail (lecture) à maintenir | `connectors/gmail.py` — lecture, archivage, suppression, OAuth | `src/openjarvis/connectors/gmail.py` |
| Envoi de réponse par mail | `channels/gmail.py`, méthode `send()` — canal distinct du connecteur, orienté échange actif | `src/openjarvis/channels/gmail.py` |
| Scanner de sécurité (PII, secrets) — n'existait pas dans CERBERUS | `GuardrailsEngine` — scanne les échanges pour des fuites de données sensibles, en plus de la logique métier à ajouter | `src/openjarvis/security/guardrails.py` |
| Cascade de modèles (à coder à la main, erreurs vues chez Antigravity) | Support LiteLLM déjà présent — accès unifié à de nombreux fournisseurs de modèles, potentiellement simplificateur pour la cascade Gemini | `src/openjarvis/engine/litellm.py` |

**Conclusion de cette comparaison :** le portage n'est pas un "retour à zéro" — une bonne partie du travail des Addendums 1 à 6 est déjà couverte, en plus robuste, par ce framework.

---

## 2. LE POINT NON NÉGOCIABLE DU PORTAGE — CE QU'OPENJARVIS NE FAIT PAS ET QU'IL FAUT AJOUTER

### 2.1 Constat précis après lecture de `proactive_agent.py`
Le prompt système de l'agent proactif (lignes 59-133 du fichier) délègue **entièrement** au LLM la décision du `tier` (trivial/low/medium/high) de chaque action — sans aucune règle déterministe qui vérifie ou corrige cette décision avant mise en file d'attente. Le prompt encourage même explicitement le LLM à être "généreux" sur les tiers bas pour les emails routiniers (ligne 128). Pour un usage de triage de newsletters, c'est un choix raisonnable. **Pour l'usage commercial d'Akim (négociation de prix, engagement contractuel), c'est exactement le point que la règle méta de CERBERUS interdit** : "en cas de doute, alerte, jamais d'improvisation par le modèle".

### 2.2 Action requise — insérer une couche de validation déterministe
Entre l'étape où le LLM propose une liste d'actions (variable `proposed` dans `proactive_agent.py`, autour de la ligne 411) et l'étape où chaque action est mise en file (`store.queue_action`, ligne 453), il faut insérer un appel à une fonction équivalente à `rules.py` de CERBERUS, qui :
- Reçoit chaque action proposée par le LLM (`action_type`, `payload`, `tier` proposé)
- Si l'action concerne un email de type commercial (détectable par la présence de mots-clés définis par Akim, ou par un `action_type` personnalisé du type `email_reply_pricing`, `email_reply_new_client`), **recalcule le `tier` lui-même** selon les règles strictes déjà définies dans les addendums précédents (grilles tarifaires Arduino/Formations IA, mots-clés d'alerte, seuils de participants/séances) — sans jamais faire confiance au tier proposé par le LLM pour ces catégories
- Peut **surclasser** un tier proposé par le LLM vers `high` (jamais l'inverse) si une règle stricte le justifie — par exemple, si le LLM propose `tier: low` pour une réponse mentionnant un prix, la fonction doit forcer `tier: high` avant mise en file

**Ce module doit être écrit comme un nouveau fichier, par exemple `src/openjarvis/security/commercial_rules.py`**, plutôt que modifié dans le cœur du framework — pour rester compatible avec les futures mises à jour d'OpenJarvis en amont (upstream) sans conflit de fusion.

### 2.3 Nouveaux `action_type` à définir pour le domaine d'Akim
Le prompt générique actuel ne connaît que `email_delete | email_archive | sms_send | sms_draft_reply | calendar_decline | calendar_accept | no_action`. Il faut étendre cette liste (dans une version personnalisée du prompt système, pas en modifiant le fichier générique directement) avec des types propres au métier d'Akim :
- `email_reply_arduino_pricing`
- `email_reply_ai_training_pricing`
- `email_reply_generic_inquiry`
- `email_reply_institutional` (toujours forcé à `tier: high`, jamais d'exception, cf. règle liste rouge des addendums précédents)

### 2.4 Grilles tarifaires et mots-clés d'alerte — portage direct
Le contenu métier construit dans les échanges précédents (grille Arduino 15k-30k FCFA, grille Formations IA avec les 3 packs, mots-clés "contrat/urgent/exclusivité/partenariat/investissement") ne change pas de logique — il change de **conteneur**. Il doit être encodé dans `commercial_rules.py` (section 2.2) exactement comme il l'était dans `cerberus/config.py` et `cerberus/engine/rules.py`, avec la même structure de seuils et de critères de modulation déjà validés.

---

## 3. ADAPTATION DE L'AGENT PROACTIF POUR LE CAS D'AKIM

### 3.1 Fréquence d'exécution
Le cron par défaut est quotidien à 5h du matin (`"0 5 * * *"`, configurable dans `config.toml [proactive]`). C'est cohérent avec un usage "briefing du matin", mais insuffisant pour la réactivité commerciale attendue (un prospect qui écrit à 14h ne doit pas attendre le lendemain 5h). **Action requise :** soit réduire l'intervalle du cron à quelques minutes/heures pour un usage quasi temps réel (le mécanisme cron le permet nativement, il suffit de changer `cron_expr`), soit combiner avec `monitor_operative.py` pour une surveillance continue plutôt que planifiée — à trancher avec Akim selon la charge qu'il souhaite imposer aux quotas d'API.

### 3.2 Canal de notification et d'approbation
Le système répond nativement à des messages comme `"{action_id} yes"` ou `"always yes {action_id}"` sur un canal de notification (Telegram, Slack, iMessage supportés nativement). **Ce mécanisme de conversation par approbation doit être le point d'ancrage de l'interface Orbe** : au lieu de construire un système de confirmation orale/textuelle CERBERUS from scratch (comme le faisait `VoxAssistant.pending_confirmation`), l'Orbe doit se brancher sur ce protocole d'approbation déjà existant, en l'adaptant pour accepter aussi une confirmation vocale/textuelle en langage naturel plutôt que la syntaxe stricte `{id} yes/no` (garder cette syntaxe comme fallback fiable, mais laisser Gemini/le LLM traduire "oui, envoie" ou "vas-y" vers cette syntaxe en interne).

### 3.3 Constat vérifié sur le frontend existant — l'Orbe doit être une nouvelle page, pas une adaptation
Le frontend Tauri d'OpenJarvis a été inspecté fichier par fichier (`frontend/src/App.tsx`, `ChatPage.tsx`, `SystemPulse.tsx`, `useSpeech.ts`). Confirmé : c'est une architecture **dashboard classique par onglets/routes séparées** (`ChatPage`, `DashboardPage`, `AgentsPage`, `DataSourcesPage`, `LogsPage`), sans aucune notion de présence conversationnelle unique. Ce n'est pas une hypothèse — c'est vérifié par lecture directe du routeur (`App.tsx`, lignes 186-195).

**Décision actée : ne pas bricoler l'existant, créer une nouvelle page dédiée.** Adapter `ChatPage` en place produirait un résultat hybride bancal (une conversation encastrée dans une mise en page deux-colonnes fixe, pas une orbe qui se réduit en bulle flottante). La bonne approche :

- **Créer une nouvelle route/page `OrbePage.tsx`**, qui devient la page d'accueil par défaut (remplace `ChatPage` comme route `index` dans `App.tsx`)
- **Réutiliser `SystemPulse.tsx` comme moteur d'état, pas comme habillage visuel.** Sa logique à trois états (`idle / inferencing / agent-active`, fichier `frontend/src/components/SystemPulse.tsx`) est exactement la bonne base logique pour piloter les animations de l'Orbe (veille / réflexion / réponse de l'Addendum 2, section 3.1) — mais son rendu actuel (une barre de 3px en haut d'écran) doit être entièrement remplacé par le rendu visuel de l'orbe centrale
- **Réutiliser `useSpeech.ts` pour la capture vocale, après correction.** Le hook existe déjà (`frontend/src/hooks/useSpeech.ts`) et gère `MediaRecorder` + un appel à `transcribeAudio()` côté backend — mais il partage exactement les mêmes lacunes déjà corrigées dans l'Addendum 4 pour CERBERUS : aucune contrainte de durée minimale d'enregistrement, aucun type MIME explicite. Ces corrections doivent être réappliquées ici, pas supposées déjà résolues par le changement de framework.
- **Vérification faite côté backend (`src/openjarvis/speech/faster_whisper.py`) :** le modèle par défaut est `"base"` (ligne 34) — un cran au-dessus du `"tiny"` qu'Antigravity avait utilisé pour CERBERUS, donc un peu plus fiable nativement, mais **sans** `no_speech_threshold` ni `vad_filter` configurés. Le risque d'hallucination documenté dans l'Addendum 4 reste réel ici et doit être corrigé de la même façon (ajout explicite de ces paramètres à l'appel de transcription).
- **Le mode manuel (dashboard classique)** reste accessible via les pages existantes (`DashboardPage`, `LogsPage`, `AgentsPage`), non supprimées — conforme au principe déjà posé dans l'Addendum 2 (mode secours activable sur demande, jamais affiché par défaut)
- **Tauri gère nativement les fenêtres "always on top" et le redimensionnement**, avec une réputation de robustesse supérieure à PyWebView pour ce type d'usage — le mécanisme de bascule fenêtre complète / mode omniprésent (Addendum 2, section 2.2) devra être implémenté via l'API fenêtre de Tauri plutôt que réinventé

---

## 4. CE QUI NE CHANGE PAS DANS LA VISION D'ENSEMBLE

- La règle méta ("en cas de doute, alerte, jamais d'action automatique") reste le principe fondateur absolu — elle se traduit maintenant par : le `tier` proposé par le LLM ne fait jamais foi seul pour une action commerciale, `commercial_rules.py` a toujours le dernier mot
- Les grilles tarifaires et mots-clés d'alerte restent exactement ceux déjà validés dans les échanges précédents
- Le principe de confiance progressive (liste rouge/grise/blanche) devient le système `permission_key` + tiers d'OpenJarvis, sans perte de logique
- Aucune institution/client sensible ne doit jamais atteindre un tier auto-approuvé, quelle que soit la décision du LLM

---

## 5. PROCHAINES ÉTAPES (à mener dans cet ordre)

1. Installer et faire tourner OpenJarvis tel quel (sans modification) pour valider l'environnement de base sur le PC Windows d'Akim, avec le connecteur Gmail réel connecté
2. Écrire `commercial_rules.py` avec les grilles tarifaires et mots-clés déjà validés (section 2.4), et l'intégrer dans le flux de `proactive_agent.py` (section 2.2) — c'est le chantier le plus critique en termes de sécurité commerciale, à traiter en priorité
3. Étendre le prompt système avec les nouveaux `action_type` propres au métier d'Akim (section 2.3)
4. Ajuster la fréquence du cron ou basculer vers `monitor_operative.py` selon le besoin réel de réactivité (section 3.1)
5. Créer `OrbePage.tsx` selon les décisions actées en section 3.3, en parallèle du chantier 2-3 puisqu'il touche des fichiers différents (frontend vs backend Python) — inclut la correction de `useSpeech.ts` et de la configuration Whisper backend
6. Brancher la cascade de modèles Gemini (déjà validée dans IMPERIUM) via LiteLLM ou le mécanisme natif d'engine d'OpenJarvis — pas encore audité en détail, chantier suivant à spécifier séparément (Addendum 8)
