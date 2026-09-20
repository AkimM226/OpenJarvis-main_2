"""CERBERUS Rules Engine — commercial rules and relational memory for Akim.

Implements the business rules from the briefing:
- Blocking keywords (juridical, urgency, scope extension)
- Pricing rules (Arduino, IA Initiation, IA Professional, IA Dev)
- Trust lists (red/grey/white tiers)
- Relational memory for contacts
"""

from __future__ import annotations

import logging
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any, Dict, List, Optional

from openjarvis.core.paths import get_config_dir

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Decision types
# ---------------------------------------------------------------------------


class Decision(Enum):
    """Rules engine decision types."""
    AUTO_EXECUTE = "auto_execute"
    REQUIRES_APPROVAL = "requires_approval"
    BLOCKED = "blocked"


# ---------------------------------------------------------------------------
# Pricing rules from the briefing
# ---------------------------------------------------------------------------

PRICING_RULES = {
    "arduino": {
        "reference": 30000,
        "floor": 15000,
        "currency": "FCFA",
        "description": "Formation Arduino",
    },
    "ia_initiation": {
        "reference": 15000,
        "floor": 15000,  # No reduction allowed
        "currency": "FCFA",
        "description": "IA Initiation",
    },
    "ia_professional": {
        "reference": 30000,
        "discounted": 25000,
        "discount_condition": "maîtrise du domaine métier demandé",
        "currency": "FCFA",
        "description": "IA Professionnel",
    },
    "ia_dev": {
        "reference": 30000,
        "discounted": 27000,
        "discount_condition": "conditions prévues",
        "currency": "FCFA",
        "description": "IA Dev",
    },
}

# ---------------------------------------------------------------------------
# Blocking keywords (juridical, urgency, scope extension)
# ---------------------------------------------------------------------------

BLOCKING_KEYWORDS = {
    "juridical": [
        "contrat",
        "clause",
        "signature",
        "engagement formel",
        "responsabilité",
        "litige",
    ],
    "urgency": [
        "urgent",
        "dernier délai",
        "aujourd'hui même",
        "sinon j'annule",
    ],
    "scope_extension": [
        "exclusivité",
        "partenariat",
        "investissement",
        "actionnaire",
    ],
}

# ---------------------------------------------------------------------------
# Trust tiers
# ---------------------------------------------------------------------------


class TrustTier(Enum):
    """Trust tiers for contacts."""
    RED = "rouge"  # Institutions, banks, schools - draft only
    GREY = "gris"  # New prospects - draft + validation
    WHITE = "blanc"  # Validated clients - extended autonomy (except pricing)


# ---------------------------------------------------------------------------
# Commercial prohibitions
# ---------------------------------------------------------------------------

COMMERCIAL_PROHIBITIONS = [
    "prix sous le plancher",
    "engagements non autorisés",
    "promesses de délai sans vérification",
    "négociations hors grille",
    "deuxième contre-proposition autonome",
    "comparaisons avec un concurrent nommé",
    "création d'une offre de consulting général",
]

# ---------------------------------------------------------------------------
# Relational memory
# ---------------------------------------------------------------------------


@dataclass
class Contact:
    """Contact information for relational memory."""
    contact_id: str
    name: str
    email: str
    organization: str
    tier: str
    validated_exchange_count: int = 0
    last_contact_date: Optional[str] = None
    services_of_interest: Optional[str] = None
    relationship_status: str = "new"
    last_interaction_summary: Optional[str] = None
    created_at: str = ""
    updated_at: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "contact_id": self.contact_id,
            "name": self.name,
            "email": self.email,
            "organization": self.organization,
            "tier": self.tier,
            "validated_exchange_count": self.validated_exchange_count,
            "last_contact_date": self.last_contact_date,
            "services_of_interest": self.services_of_interest,
            "relationship_status": self.relationship_status,
            "last_interaction_summary": self.last_interaction_summary,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
        }

    @classmethod
    def from_row(cls, row: tuple) -> Contact:
        (
            contact_id,
            name,
            email,
            organization,
            tier,
            validated_exchange_count,
            last_contact_date,
            services_of_interest,
            relationship_status,
            last_interaction_summary,
            created_at,
            updated_at,
        ) = row
        return cls(
            contact_id=contact_id,
            name=name,
            email=email,
            organization=organization,
            tier=tier,
            validated_exchange_count=validated_exchange_count,
            last_contact_date=last_contact_date,
            services_of_interest=services_of_interest,
            relationship_status=relationship_status,
            last_interaction_summary=last_interaction_summary,
            created_at=created_at or "",
            updated_at=updated_at or "",
        )


class RelationalMemory:
    """Manages contact relationships and trust tiers."""

    def __init__(self, db_path: str = "") -> None:
        if not db_path:
            db_path = str(get_config_dir() / "approvals.db")
        self._db_path = db_path
        Path(db_path).parent.mkdir(parents=True, exist_ok=True)
        self._conn = sqlite3.connect(db_path, check_same_thread=False)
        self._conn.execute("PRAGMA journal_mode=WAL")
        self._ensure_table()
        self._conn.commit()

    def _ensure_table(self) -> None:
        self._conn.executescript("""
            CREATE TABLE IF NOT EXISTS relational_memory (
                contact_id TEXT PRIMARY KEY,
                name TEXT NOT NULL,
                email TEXT NOT NULL,
                organization TEXT NOT NULL,
                tier TEXT NOT NULL,
                validated_exchange_count INTEGER NOT NULL DEFAULT 0,
                last_contact_date TEXT,
                services_of_interest TEXT,
                relationship_status TEXT,
                last_interaction_summary TEXT,
                created_at TEXT NOT NULL,
                updated_at TEXT NOT NULL
            );
        """)

    def get_or_create_contact(
        self,
        email: str,
        name: str = "",
        organization: str = "",
    ) -> Contact:
        """Get existing contact or create new one (defaults to GREY tier)."""
        row = self._conn.execute(
            "SELECT * FROM relational_memory WHERE email = ?",
            (email.lower(),),
        ).fetchone()
        if row:
            return Contact.from_row(row)

        # Create new contact - default to GREY tier
        now = datetime.now(timezone.utc).isoformat()
        contact_id = email.lower().replace("@", "_").replace(".", "_")
        self._conn.execute(
            """
            INSERT INTO relational_memory
                (contact_id, name, email, organization, tier, validated_exchange_count,
                 last_contact_date, services_of_interest, relationship_status,
                 last_interaction_summary, created_at, updated_at)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                contact_id,
                name or email.split("@")[0],
                email.lower(),
                organization or "Unknown",
                TrustTier.GREY.value,
                0,
                None,
                None,
                "new",
                None,
                now,
                now,
            ),
        )
        self._conn.commit()
        return Contact(
            contact_id=contact_id,
            name=name or email.split("@")[0],
            email=email.lower(),
            organization=organization or "Unknown",
            tier=TrustTier.GREY.value,
            validated_exchange_count=0,
            last_contact_date=None,
            services_of_interest=None,
            relationship_status="new",
            last_interaction_summary=None,
            created_at=now,
            updated_at=now,
        )

    def increment_validated_exchanges(self, email: str) -> None:
        """Increment the validated exchange counter for a contact."""
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            """
            UPDATE relational_memory
            SET validated_exchange_count = validated_exchange_count + 1,
                updated_at = ?
            WHERE email = ?
            """,
            (now, email.lower()),
        )
        self._conn.commit()

        # Check if contact should be upgraded to WHITE tier
        contact = self.get_or_create_contact(email)
        if (
            contact.tier == TrustTier.GREY.value
            and contact.validated_exchange_count >= 2
        ):
            self._upgrade_to_white(email)

    def reset_counter(self, email: str, reason: str = "") -> None:
        """Reset the counter due to heavy correction or dissatisfaction."""
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            """
            UPDATE relational_memory
            SET validated_exchange_count = 0,
                relationship_status = 'reset',
                last_interaction_summary = ?,
                updated_at = ?
            WHERE email = ?
            """,
            (reason, now, email.lower()),
        )
        self._conn.commit()

    def _upgrade_to_white(self, email: str) -> None:
        """Upgrade a contact to WHITE tier."""
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            """
            UPDATE relational_memory
            SET tier = ?, relationship_status = 'trusted', updated_at = ?
            WHERE email = ?
            """,
            (TrustTier.WHITE.value, now, email.lower()),
        )
        self._conn.commit()
        logger.info("Contact %s upgraded to WHITE tier", email)

    def downgrade_to_grey(self, email: str, reason: str = "") -> None:
        """Downgrade a contact back to GREY tier."""
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            """
            UPDATE relational_memory
            SET tier = ?, validated_exchange_count = 0,
                relationship_status = 'downgraded',
                last_interaction_summary = ?, updated_at = ?
            WHERE email = ?
            """,
            (TrustTier.GREY.value, reason, now, email.lower()),
        )
        self._conn.commit()
        logger.info("Contact %s downgraded to GREY tier: %s", email, reason)

    def set_red_tier(self, email: str, reason: str = "") -> None:
        """Set a contact to RED tier (institutions, etc.)."""
        now = datetime.now(timezone.utc).isoformat()
        self._conn.execute(
            """
            UPDATE relational_memory
            SET tier = ?, validated_exchange_count = 0,
                relationship_status = 'restricted',
                last_interaction_summary = ?, updated_at = ?
            WHERE email = ?
            """,
            (TrustTier.RED.value, reason, now, email.lower()),
        )
        self._conn.commit()
        logger.info("Contact %s set to RED tier: %s", email, reason)

    def get_contact(self, email: str) -> Optional[Contact]:
        """Get contact by email."""
        row = self._conn.execute(
            "SELECT * FROM relational_memory WHERE email = ?",
            (email.lower(),),
        ).fetchone()
        return Contact.from_row(row) if row else None

    def close(self) -> None:
        self._conn.close()


# ---------------------------------------------------------------------------
# Rules Engine
# ---------------------------------------------------------------------------


class RulesEngine:
    """Validates actions against CERBERUS business rules."""

    def __init__(self, relational_memory: Optional[RelationalMemory] = None) -> None:
        self.relational_memory = relational_memory or RelationalMemory()

    def evaluate_action(
        self,
        action_type: str,
        payload: Dict[str, Any],
        contact_email: Optional[str] = None,
    ) -> tuple[Decision, str, List[str]]:
        """Evaluate an action against business rules.

        Returns:
            (decision, reason, rules_triggered)
        """
        rules_triggered: List[str] = []
        reasons: List[str] = []

        # Get contact info if email provided
        contact = None
        if contact_email:
            contact = self.relational_memory.get_contact(contact_email)

        # Check blocking keywords
        text_content = self._extract_text_content(payload)
        blocked_by, blocking_rules = self._check_blocking_keywords(text_content)
        if blocked_by:
            rules_triggered.extend(blocking_rules)
            reasons.append(f"Mot-clé bloquant détecté: {blocked_by}")
            return Decision.BLOCKED, "; ".join(reasons), rules_triggered

        # Check pricing rules if this is a pricing-related action
        if "email_reply" in action_type or "draft" in action_type:
            price_decision, price_rules, price_reason = self._check_pricing_rules(
                payload, contact
            )
            if price_decision != Decision.AUTO_EXECUTE:
                rules_triggered.extend(price_rules)
                reasons.append(price_reason)
                return price_decision, "; ".join(reasons), rules_triggered

        # Check trust tier rules
        if contact:
            tier_decision, tier_rules, tier_reason = self._check_trust_tier_rules(
                action_type, contact
            )
            if tier_decision != Decision.AUTO_EXECUTE:
                rules_triggered.extend(tier_rules)
                reasons.append(tier_reason)
                return tier_decision, "; ".join(reasons), rules_triggered

        # Check commercial prohibitions
        prohibition_decision, prohibition_rules, prohibition_reason = (
            self._check_commercial_prohibitions(text_content)
        )
        if prohibition_decision != Decision.AUTO_EXECUTE:
            rules_triggered.extend(prohibition_rules)
            reasons.append(prohibition_reason)
            return prohibition_decision, "; ".join(reasons), rules_triggered

        # Default: requires approval for safety
        rules_triggered.append("DEFAULT_SAFETY")
        reasons.append("Règle par défaut: validation requise")
        return Decision.REQUIRES_APPROVAL, "; ".join(reasons), rules_triggered

    def _extract_text_content(self, payload: Dict[str, Any]) -> str:
        """Extract all text content from payload for keyword checking."""
        text_parts = []
        for key, value in payload.items():
            if isinstance(value, str):
                text_parts.append(value)
            elif isinstance(value, dict):
                text_parts.append(self._extract_text_content(value))
        return " ".join(text_parts).lower()

    def _check_blocking_keywords(self, text: str) -> tuple[Optional[str], List[str]]:
        """Check if text contains any blocking keywords."""
        text_lower = text.lower()
        for category, keywords in BLOCKING_KEYWORDS.items():
            for keyword in keywords:
                if keyword.lower() in text_lower:
                    return keyword, [f"BLOCKING_{category.upper()}"]
        return None, []

    def _check_pricing_rules(
        self,
        payload: Dict[str, Any],
        contact: Optional[Contact],
    ) -> tuple[Decision, List[str], str]:
        """Check if pricing complies with the rules."""
        text = self._extract_text_content(payload)
        rules: List[str] = []

        # Extract price from text (simple pattern matching)
        import re

        price_matches = re.findall(r'(\d+)\s*(?:fcfa|xof|f)', text, re.IGNORECASE)
        if not price_matches:
            # No price mentioned - this is OK
            return Decision.AUTO_EXECUTE, [], ""

        price = int(price_matches[0])

        # Determine service type from context
        service_type = self._detect_service_type(text, payload, contact)

        if service_type not in PRICING_RULES:
            rules.append("UNKNOWN_SERVICE_TYPE")
            return (
                Decision.REQUIRES_APPROVAL,
                rules,
                f"Type de service inconnu: {service_type}",
            )

        rule = PRICING_RULES[service_type]
        floor = rule["floor"]

        if price < floor:
            rules.append("PRICE_BELOW_FLOOR")
            return (
                Decision.BLOCKED,
                rules,
                f"Prix {price} FCFA sous le plancher {floor} FCFA pour {service_type}",
            )

        # Check if discount is allowed
        if "discounted" in rule and price == rule["discounted"]:
            # Discount is allowed but may require validation of condition
            rules.append("PRICE_DISCOUNT_APPLIED")
            return (
                Decision.REQUIRES_APPROVAL,
                rules,
                f"Réduction appliquée pour {service_type} - vérifier condition: {rule['discount_condition']}",
            )

        # Price is within allowed range
        return Decision.AUTO_EXECUTE, [], ""

    def _detect_service_type(
        self,
        text: str,
        payload: Dict[str, Any],
        contact: Optional[Contact],
    ) -> str:
        """Detect the service type from context."""
        text_lower = text.lower()

        # Check contact's services of interest
        if contact and contact.services_of_interest:
            services = contact.services_of_interest.lower()
            if "arduino" in services:
                return "arduino"
            if "ia" in services or "intelligence artificielle" in services:
                # Determine which IA service
                if "professionnel" in services or "pro" in services:
                    return "ia_professional"
                if "dev" in services or "développement" in services:
                    return "ia_dev"
                return "ia_initiation"

        # Check text content
        if "arduino" in text_lower:
            return "arduino"
        if "professionnel" in text_lower or "pro" in text_lower:
            return "ia_professional"
        if "dev" in text_lower or "développement" in text_lower:
            return "ia_dev"
        if "ia" in text_lower or "intelligence artificielle" in text_lower:
            return "ia_initiation"

        # Default
        return "unknown"

    def _check_trust_tier_rules(
        self,
        action_type: str,
        contact: Contact,
    ) -> tuple[Decision, List[str], str]:
        """Check trust tier rules for the contact."""
        rules: List[str] = []

        if contact.tier == TrustTier.RED.value:
            rules.append("RED_TIER_RESTRICTION")
            return (
                Decision.REQUIRES_APPROVAL,
                rules,
                f"Contact {contact.email} en liste ROUGE - brouillon uniquement",
            )

        if contact.tier == TrustTier.GREY.value:
            rules.append("GREY_TIER_VALIDATION")
            return (
                Decision.REQUIRES_APPROVAL,
                rules,
                f"Contact {contact.email} en liste GRISE - validation requise",
            )

        # WHITE tier has more autonomy but still needs validation for pricing
        if contact.tier == TrustTier.WHITE.value:
            if "email_reply" in action_type or "draft" in action_type:
                rules.append("WHITE_TIER_PRICING_CHECK")
                return (
                    Decision.REQUIRES_APPROVAL,
                    rules,
                    f"Contact {contact.email} en liste BLANCHE - validation prix requise",
                )

        return Decision.AUTO_EXECUTE, [], ""

    def _check_commercial_prohibitions(
        self,
        text: str,
    ) -> tuple[Decision, List[str], str]:
        """Check against commercial prohibitions."""
        text_lower = text.lower()
        rules: List[str] = []

        for prohibition in COMMERCIAL_PROHIBITIONS:
            if prohibition.lower() in text_lower:
                rules.append(f"PROHIBITION_{prohibition.upper().replace(' ', '_')}")
                return (
                    Decision.BLOCKED,
                    rules,
                    f"Interdiction commerciale: {prohibition}",
                )

        return Decision.AUTO_EXECUTE, [], ""


__all__ = [
    "Decision",
    "TrustTier",
    "RulesEngine",
    "RelationalMemory",
    "Contact",
    "PRICING_RULES",
    "BLOCKING_KEYWORDS",
    "COMMERCIAL_PROHIBITIONS",
]
