"""ProspectionAgent — real web-search-based prospection for Akim.

Addendum 8, Chantier 2.
Key constraints:
- Every contact MUST include source_excerpt + source_url from real search results.
- No hallucinated emails — if no contact found, flag as "a trouver manuellement".
- Every first-contact action is always tier HIGH (enforced by commercial_rules.py).
- Each prospect is logged (source, date, content) to avoid double contacts.
"""

from __future__ import annotations

import json
import logging
import sqlite3
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from openjarvis.agents.orchestrator import OrchestratorAgent
from openjarvis.core.events import EventBus
from openjarvis.core.registry import AgentRegistry
from openjarvis.engine._stubs import InferenceEngine
from openjarvis.tools._stubs import BaseTool, ToolResult

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Prospect journal (SQLite, local only)
# ---------------------------------------------------------------------------

_DB_PATH = Path.home() / ".openjarvis" / "prospection_log.db"


def _get_db() -> sqlite3.Connection:
    _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    con = sqlite3.connect(str(_DB_PATH))
    con.execute(
        "CREATE TABLE IF NOT EXISTS prospects ("
        "  id INTEGER PRIMARY KEY AUTOINCREMENT,"
        "  source_url TEXT NOT NULL,"
        "  source_excerpt TEXT NOT NULL,"
        "  contact TEXT,"
        "  message_content TEXT,"
        "  logged_at TEXT NOT NULL"
        ")"
    )
    con.commit()
    return con


def _already_contacted(source_url: str) -> bool:
    try:
        con = _get_db()
        cur = con.execute("SELECT 1 FROM prospects WHERE source_url = ?", (source_url,))
        result = cur.fetchone() is not None
        con.close()
        return result
    except Exception as exc:
        logger.warning("Prospect DB read error: %s", exc)
        return False


def _log_prospect(source_url: str, source_excerpt: str, contact: str, message_content: str) -> None:
    try:
        con = _get_db()
        con.execute(
            "INSERT INTO prospects (source_url, source_excerpt, contact, message_content, logged_at)"
            " VALUES (?, ?, ?, ?, ?)",
            (source_url, source_excerpt, contact, message_content, datetime.utcnow().isoformat()),
        )
        con.commit()
        con.close()
    except Exception as exc:
        logger.error("Failed to log prospect: %s", exc)


# ---------------------------------------------------------------------------
# Prospection system prompt — anti-hallucination guardrails
# ---------------------------------------------------------------------------

PROSPECTION_SYSTEM_PROMPT = """\
Tu es un agent de prospection commerciale pour Akim Ouattara, formateur tech a Bobo-Dioulasso.

MISSION : Rechercher des opportunites reelles (entreprises, institutions, hackathons, appels a projets)
a Bobo-Dioulasso et Ouagadougou susceptibles d'etre interesses par des formations Arduino ou IA.

REGLES ABSOLUES — NON NEGOCIABLES :

1. JAMAIS d'adresse email, numero de telephone, ou coordonnee inventee.
   - Seule une coordonnee TEXTUELLEMENT PRESENTE dans un resultat de recherche peut etre utilisee.
   - Tu DOIS citer l'extrait exact (source_excerpt) et l'URL source (source_url) pour chaque contact.

2. Si aucune coordonnee directe n'est trouvee pour une opportunite, signale-la comme
   "opportunite_sans_contact" plutot que de deviner.

3. Le message de premier contact ne doit JAMAIS mentionner un prix ferme.

4. Ne contacte jamais deux fois le meme prospect (source_url identique).

5. Pour chaque prospect propose, le JSON de sortie DOIT contenir :
   {
     "type": "prospect" | "opportunite_sans_contact",
     "name": "...",
     "source_url": "...",
     "source_excerpt": "extrait textuel exact contenant la coordonnee",
     "contact": "email ou tel trouve",  // null si type=opportunite_sans_contact
     "draft_message": "...",  // null si type=opportunite_sans_contact
     "sector": "arduino" | "ia_training" | "general"
   }
"""

# ---------------------------------------------------------------------------
# Web search tool for prospection
# ---------------------------------------------------------------------------

class _ProspectionTool(BaseTool):
    @property
    def spec(self) -> Any:
        from openjarvis.tools._stubs import ToolSpec
        return ToolSpec(
            name=self.name,
            description=self.description,
            parameters=self.parameters_schema,
        )


class ProspectionSearchTool(_ProspectionTool):
    """Real web search for prospecting opportunities."""

    @property
    def name(self) -> str:
        return "search_prospects"

    @property
    def description(self) -> str:
        return (
            "Effectue une recherche web pour trouver des opportunites de prospection "
            "a Bobo-Dioulasso ou Ouagadougou. Retourne les resultats bruts avec URL."
        )

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "query": {"type": "string", "description": "La requete de recherche."},
                "max_results": {"type": "integer", "default": 5},
            },
            "required": ["query"],
        }

    def execute(self, **kwargs: Any) -> ToolResult:
        query = kwargs.get("query", "")
        max_results = int(kwargs.get("max_results", 5))
        try:
            # Use OpenJarvis built-in web search if available
            from openjarvis.tools.web_search import WebSearchTool  # noqa: PLC0415
            tool = WebSearchTool()
            result = tool.execute(query=query, max_results=max_results)
            return result
        except ImportError:
            pass
        # Fallback: DuckDuckGo via requests
        try:
            import urllib.request
            import urllib.parse
            enc = urllib.parse.quote_plus(query)
            url = f"https://html.duckduckgo.com/html/?q={enc}"
            req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
            with urllib.request.urlopen(req, timeout=15) as resp:
                html = resp.read().decode("utf-8", errors="replace")
            # Basic extraction: find result snippets
            import re
            results = re.findall(r'<a class="result__url"[^>]*>([^<]+)</a>.*?<a class="result__snippet"[^>]*>([^<]+)</a>', html, re.DOTALL)
            if not results:
                return ToolResult(tool_name=self.name, content="Aucun resultat trouve.", success=True)
            lines = [f"URL: {r[0].strip()}\nExtrait: {r[1].strip()}" for r in results[:max_results]]
            return ToolResult(tool_name=self.name, content="\n\n".join(lines), success=True)
        except Exception as exc:
            logger.warning("ProspectionSearch fallback failed: %s", exc)
            return ToolResult(tool_name=self.name, content=f"Recherche impossible: {exc}", success=False)


class LogAndQueueProspectTool(_ProspectionTool):
    """Logs a found prospect and queues the first-contact action for Akim's approval."""

    @property
    def name(self) -> str:
        return "log_and_queue_prospect"

    @property
    def description(self) -> str:
        return (
            "Enregistre un prospect trouve (source_url, source_excerpt, contact, draft_message) "
            "et le place dans la file d'approbation d'Akim. "
            "NE PAS appeler si source_excerpt ou source_url est absent ou invente."
        )

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "source_url": {"type": "string"},
                "source_excerpt": {"type": "string"},
                "contact": {"type": "string"},
                "draft_message": {"type": "string"},
                "sector": {"type": "string"},
            },
            "required": ["name", "source_url", "source_excerpt", "contact", "draft_message"],
        }

    def execute(self, **kwargs: Any) -> ToolResult:
        source_url = kwargs.get("source_url", "")
        source_excerpt = kwargs.get("source_excerpt", "")
        contact = kwargs.get("contact", "")
        draft_message = kwargs.get("draft_message", "")
        name = kwargs.get("name", "Prospect inconnu")

        if not source_url or not source_excerpt:
            return ToolResult(
                tool_name=self.name,
                content="REFUSE: source_url ou source_excerpt manquant.",
                success=False,
            )

        # Validate that the contact appears in the excerpt (anti-hallucination)
        if contact and contact not in source_excerpt:
            return ToolResult(
                tool_name=self.name,
                content=(
                    f"REFUSE: le contact '{contact}' n'est pas present dans source_excerpt. "
                    "Seuls les contacts textuellement cites peuvent etre utilises."
                ),
                success=False,
            )

        # Deduplication
        if _already_contacted(source_url):
            return ToolResult(
                tool_name=self.name,
                content=f"Prospect {name} ({source_url}) deja contacte — ignore.",
                success=True,
            )

        # Log to DB
        _log_prospect(source_url, source_excerpt, contact, draft_message)

        # Queue in ApprovalStore — ALWAYS tier HIGH
        try:
            from openjarvis.tools.approval_store import ApprovalStore, TIER_HIGH  # noqa: PLC0415
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
        except Exception as exc:
            logger.error("Failed to queue prospect action: %s", exc)
            return ToolResult(
                tool_name=self.name,
                content=f"Prospect logue mais echec de la mise en file: {exc}",
                success=False,
            )

        return ToolResult(
            tool_name=self.name,
            content=f"Prospect '{name}' logue et mis en attente d'approbation d'Akim.",
            success=True,
        )


class FlagOpportunityWithoutContactTool(_ProspectionTool):
    """Flags an opportunity that was found but has no direct contact."""

    @property
    def name(self) -> str:
        return "flag_opportunity_no_contact"

    @property
    def description(self) -> str:
        return (
            "Signale une opportunite interessante pour laquelle aucun contact direct "
            "n'a ete trouve dans les resultats. Akim devra trouver le contact manuellement."
        )

    @property
    def parameters_schema(self) -> Dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "name": {"type": "string"},
                "source_url": {"type": "string"},
                "description": {"type": "string"},
                "sector": {"type": "string"},
            },
            "required": ["name", "source_url", "description"],
        }

    def execute(self, **kwargs: Any) -> ToolResult:
        source_url = kwargs.get("source_url", "")
        name = kwargs.get("name", "Opportunite")
        description = kwargs.get("description", "")

        if not source_url:
            return ToolResult(tool_name=self.name, content="source_url manquant.", success=False)

        try:
            from openjarvis.tools.approval_store import ApprovalStore, TIER_MEDIUM  # noqa: PLC0415
            store = ApprovalStore()
            action = store.queue_action(
                action_type="prospection_opportunity_flagged",
                description=f"[OPPORTUNITE] {name} — contact a trouver manuellement",
                payload={"name": name, "source_url": source_url, "description": description},
                permission_key=f"prospection_opportunity_flagged:url:{source_url}",
                tier=TIER_MEDIUM,
            )
        except Exception as exc:
            logger.error("Failed to flag opportunity: %s", exc)

        return ToolResult(
            tool_name=self.name,
            content=f"Opportunite '{name}' signalee (contact a trouver manuellement).",
            success=True,
        )


# ---------------------------------------------------------------------------
# Agent
# ---------------------------------------------------------------------------

@AgentRegistry.register("prospection_agent")
class ProspectionAgent(OrchestratorAgent):
    """Web-search-based prospection agent for Akim.

    Uses real web search only — no hallucinated contacts.
    All first-contact proposals are queued as TIER_HIGH in ApprovalStore.
    """

    agent_id = "prospection_agent"

    def __init__(
        self,
        engine: InferenceEngine,
        model: str,
        *,
        tools: Optional[List[BaseTool]] = None,
        bus: Optional[EventBus] = None,
        **kwargs: Any,
    ) -> None:
        default_tools: List[BaseTool] = [
            ProspectionSearchTool(),
            LogAndQueueProspectTool(),
            FlagOpportunityWithoutContactTool(),
        ]
        resolved_tools = tools if tools is not None else default_tools

        # Never interactive — all actions go through ApprovalStore, not confirm_callback
        kwargs.pop("interactive", None)
        kwargs.pop("confirm_callback", None)
        kwargs.setdefault("system_prompt", PROSPECTION_SYSTEM_PROMPT)
        kwargs.setdefault("max_turns", 12)
        kwargs.setdefault("max_tokens", 1024)

        super().__init__(engine, model, tools=resolved_tools, bus=bus, **kwargs)


__all__ = ["ProspectionAgent"]
