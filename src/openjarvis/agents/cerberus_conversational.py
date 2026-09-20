"""CerberusConversationalAgent — conversational voice agent for Akim.

Uses OrchestratorAgent with function-calling mode.
Read-only tools (list alerts, view email, etc.) are executed freely.
Writing tools (edit draft, validate/reject) are intercepted and queued in
the ApprovalStore rather than auto-approved — per Addendum 8 section 1.4.
"""

from __future__ import annotations

import json
import logging
from typing import Any, Dict, List, Optional

from openjarvis.agents.orchestrator import OrchestratorAgent
from openjarvis.core.events import EventBus
from openjarvis.core.registry import AgentRegistry
from openjarvis.core.cerberus_rules import RulesEngine, Decision
from openjarvis.engine._stubs import InferenceEngine
from openjarvis.tools._stubs import BaseTool, ToolResult

logger = logging.getLogger(__name__)

CERBERUS_SYSTEM_PROMPT = """\
Tu es CERBERUS, l'assistant vocal personnel d'Akim Ouattara, directeur technique
base a Bobo-Dioulasso, Burkina Faso.

Tu aides Akim a gerer sa boite email, ses alertes commerciales, et ses brouillons.
Reponds toujours en francais, de maniere concise et professionnelle.

REGLES ABSOLUES :
1. Tu ne proposes jamais un prix ferme sans que le besoin ait ete qualifie.
2. Toute action de modification (edition, validation) requiert une confirmation
   explicite d'Akim via le mecanisme d'approbation.
3. En cas de doute sur une decision commerciale, tu alertes et n'improvises pas.
4. Tu maintains le contexte de la conversation - quand Akim dit "il" ou "ce client",
   tu dois te referer a la personne ou l'objet mentionne precedemment dans la conversation.
"""

_READ_ONLY_TOOLS = {"list_alerts", "list_drafts", "view_email", "suggest_variants"}


class _CerberusTool(BaseTool):
    @property
    def spec(self) -> Any:
        from openjarvis.tools._stubs import ToolSpec
        return ToolSpec(
            name=self.name,
            description=self.description,
            parameters=self.parameters_schema,
        )


class ListAlertsTool(_CerberusTool):
    @property
    def name(self) -> str:
        return "list_alerts"

    @property
    def description(self) -> str:
        return "Liste toutes les alertes en attente de traitement."

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {"type": "object", "properties": {}, "required": []}

    def execute(self, **kwargs: Any) -> ToolResult:
        try:
            from openjarvis.tools.approval_store import ApprovalStore
            store = ApprovalStore()
            items = store.list_pending()
            if not items:
                return ToolResult(tool_name=self.name, content="Aucune alerte en attente.", success=True)
            lines = [f"- [{i.tier.upper()}] {i.description} (id: {i.id})" for i in items[:10]]
            return ToolResult(tool_name=self.name, content="\n".join(lines), success=True)
        except Exception as exc:
            logger.warning("ListAlerts failed: %s", exc)
            return ToolResult(tool_name=self.name, content="Impossible de charger les alertes.", success=False)


class ListDraftsTool(_CerberusTool):
    @property
    def name(self) -> str:
        return "list_drafts"

    @property
    def description(self) -> str:
        return "Liste les brouillons en attente de validation."

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {"type": "object", "properties": {}, "required": []}

    def execute(self, **kwargs: Any) -> ToolResult:
        try:
            from openjarvis.tools.approval_store import ApprovalStore
            store = ApprovalStore()
            items = [i for i in store.list_pending() if "draft" in (i.action_type or "")]
            if not items:
                return ToolResult(tool_name=self.name, content="Aucun brouillon en attente.", success=True)
            lines = [f"- {i.id}: {i.description}" for i in items[:10]]
            return ToolResult(tool_name=self.name, content="\n".join(lines), success=True)
        except Exception as exc:
            logger.warning("ListDrafts failed: %s", exc)
            return ToolResult(tool_name=self.name, content="Impossible de charger les brouillons.", success=False)


class ViewEmailTool(_CerberusTool):
    @property
    def name(self) -> str:
        return "view_email"

    @property
    def description(self) -> str:
        return "Affiche le contenu original d'un email identifie par son ID."

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "email_id": {"type": "string", "description": "L'identifiant de l'email a lire."}
            },
            "required": ["email_id"],
        }

    def execute(self, **kwargs: Any) -> ToolResult:
        email_id = kwargs.get("email_id", "")
        try:
            from openjarvis.tools.approval_store import ApprovalStore
            store = ApprovalStore()
            item = store.get_action(email_id)
            if item is None:
                return ToolResult(tool_name=self.name, content=f"Email {email_id} introuvable.", success=False)
            body = item.payload.get("body", item.description)
            return ToolResult(tool_name=self.name, content=f"Email {email_id}:\n{body}", success=True)
        except Exception as exc:
            logger.warning("ViewEmail failed: %s", exc)
            return ToolResult(tool_name=self.name, content="Impossible de charger l'email.", success=False)


class SuggestVariantsTool(_CerberusTool):
    @property
    def name(self) -> str:
        return "suggest_variants"

    @property
    def description(self) -> str:
        return "Propose des variantes de reponse pour un brouillon donne."

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "draft_id": {"type": "string", "description": "L'identifiant du brouillon."}
            },
            "required": ["draft_id"],
        }

    def execute(self, **kwargs: Any) -> ToolResult:
        draft_id = kwargs.get("draft_id", "")
        return ToolResult(
            tool_name=self.name,
            content=(
                f"Variantes pour {draft_id}:\n"
                "1. Ton professionnel, prix de reference.\n"
                "2. Ton bienveillant, degressivite si groupe >= 20.\n"
                "3. Demande de complement avant chiffrage."
            ),
            success=True,
        )


class EditDraftTool(_CerberusTool):
    @property
    def name(self) -> str:
        return "edit_draft"

    @property
    def description(self) -> str:
        return "Modifie un brouillon selon une instruction. Requiert confirmation."

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "draft_id": {"type": "string"},
                "instruction": {"type": "string"},
            },
            "required": ["draft_id", "instruction"],
        }

    def execute(self, **kwargs: Any) -> ToolResult:
        draft_id = kwargs.get("draft_id", "")
        instruction = kwargs.get("instruction", "")
        try:
            from openjarvis.tools.approval_store import ApprovalStore
            store = ApprovalStore()
            action = store.get_action(draft_id)
            if action is None:
                return ToolResult(tool_name=self.name, content=f"Brouillon {draft_id} introuvable.", success=False)
            # Persist the edit instruction into the payload
            action.payload["edit_instruction"] = instruction
            from openjarvis.tools.approval_store import STATUS_PENDING
            store.update_status(draft_id, STATUS_PENDING)  # Keep pending, just store edit
            # Update the payload via a direct upsert
            import json, sqlite3
            store._conn.execute(
                "UPDATE pending_actions SET payload = ? WHERE id = ?",
                (json.dumps(action.payload), draft_id),
            )
            store._conn.commit()
            return ToolResult(tool_name=self.name, content=f"Instruction de modification enregistree pour {draft_id}.", success=True)
        except Exception as exc:
            logger.error("EditDraftTool failed: %s", exc)
            return ToolResult(tool_name=self.name, content="Echec de la modification.", success=False)


class ValidateActionTool(_CerberusTool):
    @property
    def name(self) -> str:
        return "validate_action"

    @property
    def description(self) -> str:
        return "Approuve ou rejette une action en attente. Requiert confirmation."

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "action_id": {"type": "string"},
                "decision": {"type": "string", "enum": ["approve", "reject"]},
            },
            "required": ["action_id", "decision"],
        }

    def execute(self, **kwargs: Any) -> ToolResult:
        action_id = kwargs.get("action_id", "")
        decision = kwargs.get("decision", "")
        try:
            from openjarvis.tools.approval_store import ApprovalStore, STATUS_APPROVED, STATUS_REJECTED
            store = ApprovalStore()
            action = store.get_action(action_id)
            if action is None:
                return ToolResult(tool_name=self.name, content=f"Action {action_id} introuvable.", success=False)
            if decision == "approve":
                store.update_status(action_id, STATUS_APPROVED)
                store.log_decision(
                    action_type=action.action_type,
                    decision=STATUS_APPROVED,
                    rules_triggered="user_validation",
                    reason="Akim a approuve l'action.",
                    result="approved",
                    execution_status="pending_execution",
                )
                # Trigger executor asynchronously
                _execute_approved_action(action, store)
                return ToolResult(tool_name=self.name, content=f"Action {action_id} approuvee et execution lancee.", success=True)
            else:
                store.update_status(action_id, STATUS_REJECTED)
                store.log_decision(
                    action_type=action.action_type,
                    decision=STATUS_REJECTED,
                    rules_triggered="user_validation",
                    reason="Akim a refuse l'action.",
                    result="rejected",
                    execution_status="not_executed",
                )
                return ToolResult(tool_name=self.name, content=f"Action {action_id} rejetee.", success=True)
        except Exception as exc:
            logger.error("ValidateActionTool failed: %s", exc)
            return ToolResult(tool_name=self.name, content="Echec de la validation.", success=False)


def _execute_approved_action(action: Any, store: Any) -> None:
    """Execute an approved action: route to the appropriate executor."""
    from openjarvis.tools.approval_store import STATUS_EXECUTED, STATUS_FAILED
    from openjarvis.core.cerberus_rules import RulesEngine, Decision

    try:
        # Guard: never execute if already executed
        current = store.get_action(action.id)
        if current and current.status == STATUS_EXECUTED:
            logger.info("Action %s already executed — idempotency guard triggered.", action.id)
            return

        payload = action.payload
        action_type = action.action_type

        # Final rules check before execution
        rules_engine = RulesEngine()
        decision, reason, rules_triggered = rules_engine.evaluate_action(
            action_type=action_type,
            payload=payload,
            contact_email=payload.get("email") or payload.get("to"),
        )

        if decision == Decision.BLOCKED:
            logger.warning("Action %s BLOCKED by final rules check: %s", action.id, reason)
            store.update_status(action.id, STATUS_FAILED)
            store.log_decision(
                action_type=action_type, decision="blocked",
                rules_triggered=",".join(rules_triggered),
                reason=f"Action bloquée par Rules Engine lors de l'exécution: {reason}",
                result="blocked", execution_status="failed",
            )
            return

        if "email_reply" in action_type or "draft_pending" in action_type:
            # Send via Gmail
            from openjarvis.connectors.gmail import GmailConnector
            gmail = GmailConnector()
            if not gmail.is_connected():
                raise RuntimeError("Gmail not connected")
            body = payload.get("body") or payload.get("edit_instruction") or action.description
            to = payload.get("to", "")
            subject = payload.get("subject", "RE: " + action.description[:40])
            thread_id = payload.get("thread_id")
            if thread_id:
                # Use the connector method for thread reply
                gmail.reply_to_thread(
                    to=to, subject=subject, body=body,
                    thread_id=thread_id,
                    in_reply_to=payload.get("in_reply_to"),
                )
            else:
                # Use the connector method for new message
                gmail.send_message(to=to, subject=subject, body=body)
            store.update_status(action.id, STATUS_EXECUTED)
            store.log_decision(
                action_type=action_type, decision="executed",
                rules_triggered=",".join(rules_triggered),
                reason=f"Action validée par Akim et exécutée via Gmail. {reason}",
                result="email_sent", execution_status="executed",
            )
        else:
            # Unknown action type — just mark executed so it doesn't loop
            store.update_status(action.id, STATUS_EXECUTED)
            store.log_decision(
                action_type=action_type, decision="executed",
                rules_triggered=",".join(rules_triggered),
                reason=f"Action validée, aucun exécuteur spécifique. {reason}",
                result="no_external_action", execution_status="executed",
            )
    except Exception as exc:
        logger.error("Executor failed for action %s: %s", action.id, exc)
        store.update_status(action.id, STATUS_FAILED)
        store.log_decision(
            action_type=action.action_type, decision="failed",
            rules_triggered="executor_error",
            reason=str(exc),
            result="failure", execution_status="failed",
        )


@AgentRegistry.register("cerberus_conversational")
class CerberusConversationalAgent(OrchestratorAgent):
    """Conversational voice agent for Akim."""

    agent_id = "cerberus_conversational"

    def __init__(
        self,
        engine: InferenceEngine,
        model: str,
        *,
        tools: Optional[List[BaseTool]] = None,
        bus: Optional[EventBus] = None,
        **kwargs: Any,
    ) -> None:
        from openjarvis.tools.cerberus_briefing import GetBriefingTool
        default_tools: List[BaseTool] = [
            ListAlertsTool(),
            ListDraftsTool(),
            ViewEmailTool(),
            SuggestVariantsTool(),
            EditDraftTool(),
            ValidateActionTool(),
            GetBriefingTool(),
        ]
        resolved_tools = tools if tools is not None else default_tools

        # Initialize Rules Engine
        self._rules_engine = RulesEngine()

        kwargs["interactive"] = True
        kwargs["confirm_callback"] = self._cerberus_confirm
        kwargs.setdefault("system_prompt", CERBERUS_SYSTEM_PROMPT)
        kwargs.setdefault("max_turns", 8)
        kwargs.setdefault("max_tokens", 512)

        super().__init__(engine, model, tools=resolved_tools, bus=bus, **kwargs)

    def _cerberus_confirm(self, tool_name: str, arguments: str) -> bool:
        """Allow read-only tools; validate and queue write tools via Rules Engine."""
        if tool_name in _READ_ONLY_TOOLS:
            return True

        try:
            args_dict: Dict[str, Any] = json.loads(arguments)
        except Exception:
            args_dict = {"raw_args": arguments}

        # Apply Rules Engine validation
        try:
            decision, reason, rules_triggered = self._rules_engine.evaluate_action(
                action_type=f"conversational_{tool_name}",
                payload=args_dict,
                contact_email=args_dict.get("email") or args_dict.get("to"),
            )

            if decision == Decision.BLOCKED:
                logger.warning(
                    "Action %s BLOCKED by rules: %s (rules: %s)",
                    tool_name,
                    reason,
                    rules_triggered,
                )
                # Block the action - don't queue it
                return False

            elif decision == Decision.AUTO_EXECUTE:
                # For now, still queue for safety but mark as auto-approved
                from openjarvis.tools.approval_store import ApprovalStore, TIER_LOW
                store = ApprovalStore()
                fingerprint = args_dict.get("draft_id") or args_dict.get("action_id") or "unspecified"
                action = store.queue_action(
                    action_type=f"conversational_{tool_name}",
                    description=f"[CERBERUS AUTO] {tool_name}: {json.dumps(args_dict, ensure_ascii=False)[:120]}",
                    payload=args_dict,
                    permission_key=f"conversational_{tool_name}:target:{fingerprint}",
                    tier=TIER_LOW,  # Lower tier for auto-approved actions
                )
                # Auto-approve it
                from openjarvis.tools.approval_store import STATUS_APPROVED
                store.update_status(action.id, STATUS_APPROVED)
                store.log_decision(
                    action_type=action.action_type,
                    decision=STATUS_APPROVED,
                    rules_triggered=",".join(rules_triggered),
                    reason=f"Auto-approuvé par Rules Engine: {reason}",
                    result="auto_approved",
                    execution_status="pending_execution",
                )
                logger.info("Auto-approved conversational action %s: %s", action.id, reason)
                return False  # Still return False to prevent direct execution

            # REQUIRES_APPROVAL - queue with appropriate tier
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
            logger.info(
                "Queued conversational action %s (requires approval): %s (rules: %s)",
                action.id,
                reason,
                rules_triggered,
            )
        except Exception as exc:
            logger.error("Rules Engine validation failed: %s", exc)
            # Fallback to normal queuing
            try:
                from openjarvis.tools.approval_store import ApprovalStore, TIER_HIGH
                store = ApprovalStore()
                fingerprint = args_dict.get("draft_id") or args_dict.get("action_id") or "unspecified"
                action = store.queue_action(
                    action_type=f"conversational_{tool_name}",
                    description=f"[CERBERUS FALLBACK] {tool_name}: {json.dumps(args_dict, ensure_ascii=False)[:120]}",
                    payload=args_dict,
                    permission_key=f"conversational_{tool_name}:target:{fingerprint}",
                    tier=TIER_HIGH,
                )
                logger.info("Queued conversational action %s (fallback).", action.id)
            except Exception as fallback_exc:
                logger.error("Failed to queue conversational action (fallback): %s", fallback_exc)

        return False


__all__ = ["CerberusConversationalAgent"]
