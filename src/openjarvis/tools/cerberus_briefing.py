"""cerberus_briefing.py - GetBriefingTool for CERBERUS V1."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict

from openjarvis.tools._stubs import BaseTool, ToolResult, ToolSpec


class GetBriefingTool(BaseTool):
    """Tool that generates a CERBERUS briefing from the ApprovalStore and decision journal."""

    @property
    def name(self) -> str:
        return "get_cerberus_briefing"

    @property
    def description(self) -> str:
        return (
            "Genere un briefing CERBERUS complet: emails traites, actions en attente, "
            "alertes, prospection, et journal des decisions recentes."
        )

    @property
    def spec(self) -> Any:
        return ToolSpec(
            name=self.name,
            description=self.description,
            parameters={"type": "object", "properties": {}, "required": []},
        )

    def execute(self, **kwargs: Any) -> ToolResult:
        try:
            from openjarvis.tools.approval_store import ApprovalStore, STATUS_PENDING, STATUS_APPROVED, STATUS_EXECUTED, STATUS_FAILED
            store = ApprovalStore()

            # -- Pending actions
            pending = store.list_pending()
            pending_count = len(pending)

            # -- All actions by status
            all_rows = store._conn.execute(
                "SELECT status, COUNT(*) FROM pending_actions GROUP BY status"
            ).fetchall()
            stats = {row[0]: row[1] for row in all_rows}

            approved_count = stats.get(STATUS_APPROVED, 0)
            executed_count = stats.get(STATUS_EXECUTED, 0)
            failed_count = stats.get(STATUS_FAILED, 0)

            # -- Decision journal (last 10)
            journal_rows = store._conn.execute(
                "SELECT timestamp, action_type, decision, reason FROM decision_journal ORDER BY timestamp DESC LIMIT 10"
            ).fetchall()

            # -- Relational memory stats
            contact_counts = store._conn.execute(
                "SELECT tier, COUNT(*) FROM relational_memory GROUP BY tier"
            ).fetchall()
            contact_stats = {row[0]: row[1] for row in contact_counts}

            # Build the briefing text
            now = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M UTC")
            lines = [
                f"BRIEFING CERBERUS — {now}",
                "",
                "ACTIONS EN ATTENTE",
                f"  - {pending_count} action(s) necessitent votre validation",
            ]
            for pa in pending[:5]:
                lines.append(f"    [{pa.id}] {pa.action_type}: {pa.description[:60]}")

            lines += [
                "",
                "STATISTIQUES GLOBALES",
                f"  - Approuvees (en attente d'execution) : {approved_count}",
                f"  - Executees avec succes : {executed_count}",
                f"  - Echecs : {failed_count}",
                "",
                "MEMOIRE RELATIONNELLE",
                f"  - Contacts ROUGE : {contact_stats.get('rouge', 0)}",
                f"  - Contacts GRIS  : {contact_stats.get('gris', 0)}",
                f"  - Contacts BLANC : {contact_stats.get('blanc', 0)}",
                "",
                "JOURNAL DES DECISIONS RECENTES",
            ]
            if journal_rows:
                for ts, action_type, decision, reason in journal_rows:
                    ts_short = ts[:16] if ts else "?"
                    lines.append(f"  [{ts_short}] {action_type} -> {decision}: {reason[:60]}")
            else:
                lines.append("  (aucune decision enregistree)")

            if pending_count > 0:
                lines += [
                    "",
                    "A VOTRE ATTENTION",
                    f"  {pending_count} action(s) requierent votre validation avant execution.",
                ]

            briefing_text = "\n".join(lines)
            return ToolResult(tool_name=self.name, content=briefing_text, success=True)

        except Exception as exc:
            return ToolResult(
                tool_name=self.name,
                content=f"Erreur lors de la generation du briefing: {exc}",
                success=False,
            )
