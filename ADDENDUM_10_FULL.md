<USER_REQUEST>
# ADDENDUM TECHNIQUE — CERBERUS V1

## Finalisation, intégration et validation end-to-end

**Document destiné à Antigravity / Agent de développement**

---

# 0. OBJECTIF DE CET ADDENDUM

Le développement initial de CERBERUS a permis de mettre en place plusieurs briques fonctionnelles, mais l'audit du dépôt montre que plusieurs composants restent isolés, incomplets ou non reliés entre eux.

**Objectif de cet addendum : transformer l'état actuel du dépôt en une V1 réellement fonctionnelle de bout en bout.**

La V1 ne devra pas être considérée comme terminée parce que les fichiers, classes ou endpoints existent.

Elle sera considérée comme terminée uniquement lorsque les scénarios utilisateur décrits dans ce document fonctionneront réellement sur une installation propre.

Le principe directeur est :

> **Ne pas réécrire inutilement ce qui existe. Réutiliser les briques existantes, les corriger et surtout les intégrer correctement.**

---

# 1. DÉFINITION EXACTE DE CERBERUS V1

CERBERUS V1 est un assistant IA personnel orienté gestion commerciale.

Il doit permettre à Akim de :

1. parler naturellement à CERBERUS ;
2. recevoir une réponse vocale ;
3. maintenir une véritable conversation ;
4. lire et analyser les emails Gmail ;
5. classifier les emails ;
6. identifier les demandes nécessitant une intervention humaine ;
7. rédiger des réponses ;
8. envoyer automatiquement uniquement les réponses autorisées par les règles ;
9. mettre en attente les cas nécessitant validation ;
10. permettre à Akim de valider, modifier ou refuser une action ;
11. exécuter réellement l'action après validation ;
12. fournir un briefing de ce qui s'est passé pendant l'absence d'Akim ;
13. rechercher automatiquement des prospects ;
14. préparer des premiers contacts personnalisés ;
15. mettre ces premiers contacts en attente de validation ;
16. mémoriser la relation avec chaque contact ;
17. conserver une traçabilité complète des décisions.

---

# 2. RÈGLE ABSOLUE DE FIN DE DÉVELOPPEMENT

Ne pas déclarer la V1 terminée simplement parce que :

* les tests unitaires passent ;
* les endpoints répondent ;
* les composants frontend s'affichent ;
* les agents existent ;
* les outils sont enregistrés.

La V1 doit être validée par des **scénarios end-to-end réels ou simulés de manière réaliste**.

Exemple obligatoire :

```text
Akim parle
        ↓
STT
        ↓
CERBERUS
        ↓
compréhension
        ↓
action
        ↓
outil
        ↓
résultat
        ↓
réponse CERBERUS
        ↓
TTS
        ↓
Akim entend la réponse
```

Même principe pour Gmail :

```text
Email entrant
      ↓
Gmail
      ↓
CERBERUS
      ↓
classification
      ↓
règles métier
      ↓
décision
      ↓
┌───────────────────────┐
│ auto-send autorisé    │
│ OU                    │
│ validation Akim       │
└───────────────────────┘
      ↓
Gmail
      ↓
journal
```

---

# 3. CORRECTION PRIORITAIRE — CONVERSATION VOCALE CERBERUS

## 3.1 Sélection réelle de l'agent

Actuellement, le frontend transmet un identifiant d'agent mais le backend ne l'utilise pas correctement.

Corriger l'architecture afin que :

```text
agent = cerberus_conversational
```

sélectionne réellement :

```text
CerberusConversationalAgent
```

et non l'agent par défaut.

La requête frontend/backend doit utiliser un contrat cohérent.

Ne pas avoir simultanément :

```text
agent
```

d'un côté et :

```text
model
```

de l'autre sans mapping explicite.

Créer un mécanisme propre du type :

```text
POST /v1/chat/completions

{
    "model": "cerberus_conversational",
    "messages": [...]
}
```

ou conserver `agent`, mais dans ce cas le backend doit réellement le prendre en compte.

L'important est la cohérence de bout en bout.

---

# 4. MÉMOIRE DE CONVERSATION

CERBERUS ne doit pas traiter chaque phrase comme une conversation indépendante.

Implémenter une notion de :

```text
conversation_id
```

et conserver l'historique nécessaire.

Exemple :

Akim :

> Quel est le dernier mail de Jean ?

CERBERUS :

> Le dernier message de Jean date d'hier...

Akim :

> Et qu'est-ce qu'il veut exactement ?

CERBERUS doit comprendre que "il" correspond à Jean et conserver le contexte.

Akim :

> Réponds-lui que c'est possible.

CERBERUS doit savoir de quel email et de quelle personne il est question.

La mémoire conversationnelle doit être suffisamment persistante pendant la session.

---

# 5. CHAÎNE SPEECH COMPLÈTE

La chaîne suivante doit fonctionner :

```text
Micro
 ↓
STT
 ↓
texte utilisateur
 ↓
CERBERUS
 ↓
réponse texte
 ↓
TTS
 ↓
audio
 ↓
lecture frontend
```

## 5.1 STT

Vérifier et corriger :

* backend réellement installé ;
* dépendances déclarées ;
* chargement du modèle ;
* gestion des erreurs ;
* retour propre du texte.

Ne jamais considérer STT comme fonctionnel simplement parce que l'endpoint existe.

## 5.2 TTS

Même exigence.

Si Kokoro est conservé :

* ajouter correctement la dépendance ;
* vérifier son installation ;
* vérifier le chargement ;
* vérifier la génération audio ;
* vérifier la lecture frontend.

Si une autre solution déjà compatible avec l'architecture est retenue, elle doit être documentée.

## 5.3 Nettoyage des tests speech

Les tests doivent correspondre à l'architecture réellement utilisée :

```text
stt_backend
tts_backend
```

et non à d'anciens noms comme :

```text
speech_backend
```

Tous les tests doivent être remis en cohérence.

---

# 6. GMAIL — LECTURE

CERBERUS doit réellement pouvoir :

* rechercher les messages ;
* lire les messages ;
* lire les threads ;
* identifier l'expéditeur ;
* identifier le destinataire ;
* récupérer objet/date/contenu ;
* distinguer nouveaux messages et messages déjà traités.

Créer une abstraction propre :

```text
GmailService
```

avec au minimum :

```text
search_messages()
get_message()
get_thread()
send_message()
reply_to_thread()
archive_message()
```

Les noms peuvent différer, mais les capacités doivent exister.

---

# 7. GMAIL — RÉPONSE

C'est un élément obligatoire de la V1.

Implémenter réellement :

```text
email → analyse → rédaction → envoi
```

CERBERUS doit être capable de répondre dans le thread Gmail approprié.

Ne pas créer un nouvel email indépendant lorsqu'une réponse au thread est requise.

Créer les executors correspondant aux actions déjà produites par le moteur métier, notamment :

```text
email_reply_arduino_pricing
email_reply_ai_training_pricing
email_reply_generic_inquiry
email_reply_institutional
```

Les noms peuvent être factorisés en un executor générique si l'architecture est meilleure.

Mais le résultat doit être :

```text
action validée
      ↓
Gmail API
      ↓
réponse réellement envoyée
```

---

# 8. APPROVAL SYSTEM — CORRECTION COMPLÈTE

Le système actuel d'ApprovalStore doit devenir réellement opérationnel.

Il doit supporter au minimum :

```text
PENDING
APPROVED
REJECTED
EXECUTED
FAILED
```

ou une équivalence cohérente.

## 8.1 Validation

Lorsque Akim valide :

```text
pending
 ↓
approved
 ↓
executor
 ↓
executed
```

## 8.2 Refus

```text
pending
 ↓
rejected
```

Aucune action externe ne doit être exécutée.

## 8.3 Échec

Si Gmail ou un autre service échoue :

```text
approved
 ↓
failed
```

avec l'erreur enregistrée.

## 8.4 Edition

`EditDraftTool` ne doit plus simplement retourner :

```text
"Brouillon modifié."
```

Il doit réellement modifier le brouillon stocké.

Même exigence pour `ValidateActionTool`.

Chaque outil doit modifier l'état réel du système.

---

# 9. GARDE-FOU ABSOLU DES ACTIONS EXTERNES

Avant toute action externe :

```text
Action proposée
      ↓
Rules Engine
      ↓
Decision
```

Résultat possible :

```text
AUTO_EXECUTE
REQUIRES_APPROVAL
BLOCKED
```

Le LLM ne doit jamais pouvoir contourner cette couche.

Architecture souhaitée :

```text
LLM
 ↓
proposition d'action
 ↓
RULE ENGINE
 ↓
autorisation
 ↓
EXECUTOR
```

et surtout pas :

```text
LLM → Gmail directement
```

---

# 10. IMPLÉMENTER COMPLÈTEMENT LES RÈGLES CERBERUS

Le moteur de règles doit reprendre fidèlement le briefing V1.

## 10.1 Règle méta

En cas de :

* doute ;
* ambiguïté ;
* situation non couverte ;

alors :

```text
REQUIRES_APPROVAL
```

Jamais :

```text
AUTO_EXECUTE
```

---

# 11. MOTS-CLÉS BLOQUANTS

Implémenter au minimum les catégories du briefing :

### Juridique / contractuel

```text
contrat
clause
signature
engagement formel
responsabilité
litige
```

### Urgence

```text
urgent
dernier délai
aujourd'hui même
sinon j'annule
```

### Périmètre étendu

```text
exclusivité
partenariat
investissement
actionnaire
```

### Prix

Toute négociation sortant des règles tarifaires doit nécessiter validation.

La liste doit être centralisée et facilement extensible.

---

# 12. LISTES ROUGE / GRISE / BLANCHE

Implémenter réellement le système de confiance décrit dans le briefing.

## Rouge

Institutions, banques, écoles, organismes et contacts liés à Capital du Savoir en tant que DG.

Comportement :

```text
BROUILLON UNIQUEMENT
```

Jamais d'envoi automatique.

## Gris

Nouveaux prospects et nouveaux contacts.

Comportement :

```text
BROUILLON
+
VALIDATION
```

## Blanc

Client non institutionnel ayant obtenu 2-3 échanges validés consécutifs sans modification lourde.

Autonomie élargie uniquement dans le périmètre autorisé.

Jamais d'autonomie totale sur les prix.

---

# 13. MÉMOIRE RELATIONNELLE

Créer une vraie structure persistante par contact.

Minimum :

```text
contact_id
name
email
organization
tier
validated_exchange_count
last_contact_date
services_of_interest
relationship_status
last_interaction_summary
created_at
updated_at
```

Le compteur doit fonctionner réellement.

Exemple :

```text
nouveau contact
→ GRIS
→ échange validé
→ compteur 1

échange validé
→ compteur 2

échange validé
→ BLANC
```

Une correction lourde ou un signal de mécontentement doit remettre le compteur à zéro conformément au briefing.

---

# 14. CLASSIFICATION DES SERVICES

CERBERUS doit distinguer :

```text
Arduino
IA Initiation
IA Professionnel
IA Dev
```

et déterminer le besoin réel du prospect.

Il doit pouvoir poser une question de clarification lorsque le besoin est ambigu.

Il ne doit pas proposer automatiquement une offre plus chère sans justification par le besoin identifié.

---

# 15. MOTEUR TARIFAIRE

Reprendre exactement les règles tarifaires du briefing.

### Arduino

```text
référence : 30 000 FCFA
plancher : 15 000 FCFA
```

Réduction uniquement selon les critères autorisés.

### IA Initiation

```text
15 000 FCFA
```

Pas de réduction.

### IA Professionnel

```text
30 000 FCFA
25 000 FCFA dans les conditions prévues
```

Validation obligatoire concernant la maîtrise du domaine métier demandé.

### IA Dev

```text
30 000 FCFA
27 000 FCFA dans les conditions prévues
```

Toute situation hors grille :

```text
REQUIRES_APPROVAL
```

---

# 16. INTERDICTIONS COMMERCIALES

CERBERUS doit empêcher automatiquement :

* les prix sous le plancher ;
* les engagements non autorisés ;
* les promesses de délai sans vérification ;
* les négociations hors grille ;
* la deuxième contre-proposition autonome ;
* les comparaisons avec un concurrent nommé ;
* la création d'une offre de consulting général.

---

# 17. BRIEFING CERBERUS

Créer une vraie capacité :

```text
get_cerberus_briefing()
```

ou équivalent.

Lorsque Akim dit :

> CERBERUS, fais-moi le briefing.

Le système doit produire une synthèse des événements depuis le dernier briefing ou depuis une période demandée.

Exemple de structure :

```text
BRIEFING CERBERUS

Pendant ton absence :

EMAILS
- 17 nouveaux emails analysés
- 9 classés sans intervention
- 3 brouillons préparés
- 2 réponses envoyées automatiquement
- 1 email nécessite ton intervention
- 2 emails restent en attente

PROSPECTION
- 12 prospects identifiés
- 5 qualifiés
- 3 premiers messages préparés
- 2 en attente de validation

ALERTES
- 1 demande de partenariat
- 1 négociation hors grille

À TON ATTENTION
- ...

ACTIONS AUTOMATIQUES
- ...

ACTIONS EN ATTENTE
- ...
```

Le nombre réel doit naturellement provenir de la base.

---

# 18. PRIORITÉ DES ALERTES

Le briefing doit distinguer :

```text
URGENT
ACTION REQUISE
EN ATTENTE
INFORMATION
```

Les mots-clés d'urgence doivent être remontés en priorité.

Aucune notification intrusive permanente n'est nécessaire : le briefing à la demande reste le mode privilégié.

---

# 19. JOURNAL DE DÉCISIONS

Chaque action CERBERUS doit enregistrer :

```text
timestamp
contact_id
message_id
action_type
decision
rules_triggered
reason
result
execution_status
```

Exemple :

```text
2026-09-20 14:35
email_reply
Jean Dupont
REQUIRES_APPROVAL
RULE_PRICE_NEGOTIATION
Prix demandé sous le plancher
PENDING
```

Le journal doit être consultable.

---

# 20. PROSPECTION AUTONOME

Le module `prospection_agent.py` doit être réellement enregistré et intégré au système.

Il doit pouvoir :

1. rechercher des entreprises/cibles ;
2. identifier les prospects pertinents ;
3. récupérer les informations disponibles ;
4. éliminer les doublons ;
5. enregistrer la source ;
6. générer une personnalisation ;
7. générer le premier message ;
8. créer une action `PENDING` ;
9. permettre à Akim de valider ;
10. envoyer réellement le message après validation ;
11. enregistrer la date et le contenu envoyé.

---

# 21. PAS D'HALLUCINATION EN PROSPECTION

CERBERUS ne doit jamais inventer :

* une adresse email ;
* un nom ;
* un poste ;
* une entreprise ;
* une information sur le prospect.

Toute information utilisée dans la personnalisation doit avoir une source.

En absence d'information fiable :

```text
information inconnue
```

et non une invention.

---

# 22. PLANIFICATION DES RELANCES

Implémenter un mécanisme simple de relance.

Chaque prospect doit pouvoir avoir :

```text
first_contact_date
follow_up_date
follow_up_count
last_message
status
```

Statuts minimum :

```text
NEW
CONTACT_PENDING
CONTACTED
RESPONDED
QUALIFIED
CONVERTED
NOT_INTERESTED
DO_NOT_CONTACT
```

Les paramètres de relance doivent être facilement configurables.

---

# 23. ENREGISTREMENT DE L'AGENT PROSPECTION

Corriger l'initialisation afin que :

```text
prospection_agent
```

soit effectivement enregistré au démarrage.

Même exigence pour :

```text
cerberus_conversational
```

Aucun agent ne doit nécessiter un import manuel pour être disponible.

Ajouter un test :

```text
assert AgentRegistry.contains("cerberus_conversational")
assert AgentRegistry.contains("prospection_agent")
```

---

# 24. CONFIGURATION GEMINI

Le briefing V1 spécifie :

```text
Modèle IA : Gemini exclusivement
```

Adapter l'implémentation CERBERUS afin qu'elle respecte cette décision.

Le modèle doit être configurable par variable d'environnement/configuration.

Ne pas hardcoder une clé API.

Exemple :

```text
GEMINI_API_KEY
CERBERUS_MODEL
```

Documenter les variables nécessaires dans `.env.example`.

---

# 25. SÉCURITÉ

Les secrets ne doivent jamais être :

* commités ;
* affichés dans les logs ;
* retournés par une API ;
* inclus dans les prompts.

Cela concerne notamment :

```text
GEMINI_API_KEY
GMAIL credentials
OAuth tokens
DATABASE credentials
```

Les erreurs doivent être nettoyées avant affichage utilisateur.

---

# 26. GMAIL OAUTH

Vérifier le parcours complet :

```text
connexion Gmail
↓
OAuth
↓
token
↓
lecture
↓
réponse
↓
renouvellement token
```

Une installation fraîche doit être documentée.

Le README doit expliquer précisément :

1. création/configuration OAuth ;
2. variables nécessaires ;
3. lancement ;
4. première authentification ;
5. vérification de connexion.

---

# 27. INTERFACE CERBERUS

L'interface actuelle doit rester visuellement cohérente.

Elle doit cependant afficher au minimum :

### État

```text
CERBERUS
● En ligne
```

### Conversation

Historique conversationnel visible.

### Actions en attente

```text
3 actions nécessitent votre validation
```

### Dernier briefing

Accessible rapidement.

### Journal

Possibilité de consulter les dernières actions.

### Micro

Bouton permettant :

```text
appui
→ écoute
→ transcription
→ réponse
→ lecture
```

---

# 28. ACTIONS DE VALIDATION DANS L'INTERFACE

Pour une action en attente :

```text
[Voir]
[Modifier]
[Valider]
[Refuser]
```

Après validation :

```text
Validation
↓
exécution
↓
succès/échec
↓
journal
```

Ne jamais afficher "envoyé" si Gmail n'a pas confirmé l'envoi.

---

# 29. GESTION DES ERREURS

Tous les appels externes doivent gérer :

```text
timeout
authentication error
rate limit
network failure
API error
invalid response
```

Une erreur ne doit jamais être interprétée comme une réussite.

---

# 30. IDEMPOTENCE

Une action email ne doit jamais être exécutée deux fois par accident.

Avant l'envoi :

```text
action_id
```

doit permettre de vérifier si l'action a déjà été exécutée.

Exemple :

```text
PENDING
→ APPROVED
→ EXECUTING
→ EXECUTED
```

Une seconde tentative sur une action `EXECUTED` doit être refusée.

---

# 31. TESTS OBLIGATOIRES

Créer des tests unitaires pour :

### Rules engine

* mots-clés bloquants ;
* listes rouge/grise/blanche ;
* seuils de prix ;
* deuxième contre-proposition ;
* absence de délai ;
* concurrence ;
* consulting.

### ApprovalStore

* création ;
* modification ;
* validation ;
* rejet ;
* exécution ;
* échec ;
* idempotence.

### Gmail

* recherche ;
* lecture ;
* réponse ;
* thread ;
* erreur ;
* authentification.

### Prospection

* recherche ;
* déduplication ;
* personnalisation ;
* source ;
* création d'action ;
* validation ;
* envoi.

### Conversation

* agent CERBERUS sélectionné ;
* historique ;
* STT ;
* LLM ;
* TTS.

---

# 32. TESTS END-TO-END OBLIGATOIRES

Ces scénarios doivent être automatisés autant que possible.

## TEST A — Conversation

```text
Akim parle
→ transcription
→ CERBERUS
→ réponse
→ TTS
→ audio
```

Résultat attendu : conversation fonctionnelle.

---

## TEST B — Email simple autorisé

Créer un email fictif correspondant à un cas explicitement autorisé.

Résultat :

```text
classification
→ règle
→ auto-send
→ Gmail mock
→ journal EXECUTED
```

---

## TEST C — Email nécessitant validation

Exemple :

```text
Client : Pouvez-vous faire 12 000 FCFA ?
```

Résultat :

```text
analyse
→ prix hors règle
→ PENDING
→ aucune réponse envoyée
```

Après validation :

```text
APPROVED
→ réponse envoyée
→ EXECUTED
```

---

## TEST D — Institution

Un email institutionnel doit automatiquement rester en validation.

---

## TEST E — Urgence

Un email contenant une condition d'urgence doit bloquer l'autonomie.

---

## TEST F — Prospect

```text
recherche
→ prospect
→ qualification
→ message personnalisé
→ PENDING
→ validation
→ envoi
→ journal
```

---

## TEST G — Briefing

Créer plusieurs événements.

Demander :

> CERBERUS, briefing.

Résultat : synthèse correcte de toutes les actions.

---

# 33. TEST DE NON-RÉGRESSION

Avant de déclarer la V1 terminée :

```bash
pytest
```

doit être vert.

Frontend :

```bash
npm run typecheck
npm run build
```

doivent être verts.

Aucune nouvelle fonctionnalité ne doit casser les fonctionnalités existantes.

---

# 34. INSTALLATION PROPRE

Tester également dans un environnement propre.

Procédure :

```text
clone repository
↓
installation dépendances
↓
configuration .env
↓
database initialisation
↓
OAuth Gmail
↓
lancement backend
↓
lancement frontend
↓
test conversation
↓
test Gmail
↓
test prospection
```

La V1 ne doit pas dépendre d'un état caché de l'environnement de développement.

---

# 35. DOCUMENTATION

Mettre à jour :

```text
README.md
.env.example
```

avec :

* architecture ;
* installation ;
* variables ;
* Gmail OAuth ;
* Gemini ;
* STT ;
* TTS ;
* lancement ;
* tests ;
* dépannage ;
* architecture des règles ;
* fonctionnement ApprovalStore ;
* fonctionnement prospection.

---

# 36. CE QUI EST HORS PÉRIMÈTRE

Ne pas dériver vers :

```text
SENTINEL
surveillance PC
contrôle du PC
automatisation système
WhatsApp
LinkedIn
consulting général
```

Ces fonctionnalités restent hors V1 conformément au briefing.

La priorité absolue est de terminer CERBERUS Email + Voice + Prospection.

---

# 37. CRITÈRE FINAL DE VALIDATION

Antigravity ne doit pas répondre :

> "La V1 est terminée."

simplement parce que le code compile.

Il doit fournir à la fin un rapport de validation contenant :

```text
CERBERUS V1 — FINAL VALIDATION

Conversation vocale : PASS / FAIL
Mémoire conversationnelle : PASS / FAIL
STT : PASS / FAIL
TTS : PASS / FAIL

Gmail lecture : PASS / FAIL
Gmail classification : PASS / FAIL
Gmail brouillon : PASS / FAIL
Gmail validation : PASS / FAIL
Gmail envoi : PASS / FAIL

Rules Engine : PASS / FAIL
Liste rouge : PASS / FAIL
Liste grise : PASS / FAIL
Liste blanche : PASS / FAIL

Briefing : PASS / FAIL

Prospection recherche : PASS / FAIL
Prospection qualification : PASS / FAIL
Prospection validation : PASS / FAIL
Prospection envoi : PASS / FAIL

Journal : PASS / FAIL
Idempotence : PASS / FAIL

Tests unitaires : X/X
Tests intégration : X/X
Tests E2E : X/X

Frontend build : PASS / FAIL
Backend : PASS / FAIL

Installation propre : PASS / FAIL
```

Tout élément critique en `FAIL` signifie :

> **V1 NON TERMINÉE**

---

# 38. RÈGLE FINALE DE QUALITÉ

CERBERUS doit être pensé comme un véritable agent opérationnel et non comme une démonstration d'interface.

Le test ultime est simple :

> **Akim doit pouvoir quitter son ordinateur, laisser CERBERUS travailler sur son périmètre autorisé, revenir, dire "CERBERUS, fais-moi le briefing", et obtenir une représentation fiable de ce qui a été fait, de ce qui est en attente et de ce qui nécessite son intervention.**

Et lorsqu'une action nécessite son autorisation :

```text
CERBERUS attend.
```

Il ne contourne jamais la validation.

Lorsqu'une action est explicitement autorisée :

```text
CERBERUS exécute.
```

Puis :

```text
CERBERUS journalise.
```

Lorsqu'une action échoue :

```text
CERBERUS signale l'échec.
```

Il ne prétend jamais avoir réussi.

---

# 39. ORDRE DE PRIORITÉ DE DÉVELOPPEMENT

Pour éviter de disperser le développement, suivre cet ordre :

### PRIORITÉ 1

Réparer le routage réel :

```text
Frontend → CERBERUS agent → Backend
```

### PRIORITÉ 2

Terminer :

```text
Voice → CERBERUS → Voice
```

### PRIORITÉ 3

Terminer :

```text
Gmail → analyse → règles → action
```

### PRIORITÉ 4

Terminer :

```text
ApprovalStore → validation → executor → Gmail
```

### PRIORITÉ 5

Implémenter :

```text
mémoire relationnelle
listes rouge/grise/blanche
```

### PRIORITÉ 6

Implémenter :

```text
briefing
```

### PRIORITÉ 7

Intégrer complètement :

```text
prospection autonome
```

### PRIORITÉ 8

Tests E2E + installation propre + documentation.

---

# 40. INSTRUCTION À ANTIGRAVITY

**Travaille directement sur le dépôt existant.**

Avant chaque modification importante :

1. inspecter le code existant ;
2. comprendre les abstractions déjà utilisées ;
3. réutiliser les composants existants lorsqu'ils sont pertinents ;
4. éviter les doublons ;
5. ne pas créer une seconde architecture parallèle ;
6. connecter les composants existants lorsqu'ils sont actuellement isolés ;
7. ajouter les tests correspondant à chaque correction.

Après chaque étape importante :

```text
implémentation
→ test
→ correction
→ test
```

À la fin :

```text
tests unitaires
+
tests intégration
+
tests E2E
+
build frontend
+
installation propre
```

**Ne pas masquer les problèmes par des mocks dans le chemin de production.**

Les mocks sont autorisés pour les tests automatisés, mais le chemin réel de production doit utiliser les vraies intégrations configurées.

**Ne pas supprimer une fonctionnalité existante simplement parce qu'elle est incomplète : la corriger ou la remplacer proprement en conservant les capacités déjà présentes.**

---

# DÉFINITION DE DONE

CERBERUS V1 est terminé uniquement lorsque le scénario suivant fonctionne réellement :

```text
                    ┌──────────────┐
                    │     AKIM     │
                    └──────┬───────┘
                           │
                     voix / texte
                           │
                           ▼
                 ┌──────────────────┐
                 │    CERBERUS      │
                 │ Conversation IA  │
                 └────────┬─────────┘
                          │
             ┌────────────┼────────────┐
             ▼            ▼            ▼
          Gmail       Prospection    Briefing
             │            │
             ▼            ▼
       Rules Engine ← Mémoire
             │
      ┌──────┼──────┐
      ▼      ▼      ▼
    AUTO   APPROVAL BLOCK
      │      │
      │      ▼
      │    AKIM
      │      │
      └──────┴───────┐
                     ▼
                 EXECUTOR
                     │
                     ▼
                  ACTION
                     │
                     ▼
                  JOURNAL
```

**Si cette boucle fonctionne de bout en bout, de manière fiable, avec les garde-fous définis dans le briefing, alors CERBERUS V1 peut être considérée comme fonctionnelle.**

Fin de l'addendum.

</USER_REQUEST>
<ADDITIONAL_METADATA>
The current local time is: 2026-09-20T14:45:13+01:00.

The user's current state is as follows:
Active Document: c:\Users\bamba\Downloads\ADDENDUM_10_CORRECTIF_FINAL_V1.md (LANGUAGE_MARKDOWN)
Cursor is on line: 1
Other open documents:
- c:\Users\bamba\Downloads\ADDENDUM_10_CORRECTIF_FINAL_V1.md (LANGUAGE_MARKDOWN)
- c:\Users\bamba\Downloads\ADDENDUM_9_CORRECTIF_APPROVAL_STORE_TTS.md (LANGUAGE_MARKDOWN)
- c:\Users\bamba\Downloads\ADDENDUM_8_ORBE_PROSPECTION_GRILLES.md (LANGUAGE_MARKDOWN)
- d:\OpenJarvis-main\OpenJarvis-main_1\frontend\tsconfig.json (LANGUAGE_UNSPECIFIED)
- c:\Users\bamba\Downloads\ADDENDUM_7_PORTAGE_OPENJARVIS.md (LANGUAGE_MARKDOWN)
</ADDITIONAL_METADATA>
<USER_SETTINGS_CHANGE>
The user changed setting `Model Selection` from Claude Sonnet 4.6 (Thinking) to Gemini 3.1 Pro (High). No need to comment on this change if the user doesn't ask about it. If reporting what model you are, please use a human readable name instead of the exact string.
</USER_SETTINGS_CHANGE>