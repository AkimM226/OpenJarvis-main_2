"""Deterministic commercial validation rules for Akim's domain.

Addendum 8, Chantier 3: Pricing grids are now enforced numerically.
If a proposed price violates the grids below, the tier is forced to HIGH.
"""

import re
from typing import Any, Dict, Optional
from openjarvis.tools.approval_store import TIER_HIGH, TIER_MEDIUM, TIER_LOW, TIER_TRIVIAL

# ---------------------------------------------------------------------------
# Alert keywords — always elevate to HIGH
# ---------------------------------------------------------------------------
ALERT_KEYWORDS = [
    "contrat", "urgent", "exclusivite", "exclusivité",
    "partenariat", "investissement",
]

# ---------------------------------------------------------------------------
# Pricing grids (FCFA) — locked per Addendum 8 section 3.2
# ---------------------------------------------------------------------------

# Arduino formation
ARDUINO_REF_PRICE = 30_000      # Prix de référence / participant
ARDUINO_FLOOR_PRICE = 15_000    # Plancher absolu / participant
ARDUINO_GROUP_THRESHOLD = 20    # >= 20 pers → dégressivité vers le plancher

# AI Training packs
AI_PACKS = {
    # pack_name: {ref, reduced (None = pas de réduction), min_for_reduced}
    "initiation":     {"ref": 15_000, "reduced": None,   "min_group": None},
    "professionnel":  {"ref": 30_000, "reduced": 25_000, "min_group": 10},
    "dev":            {"ref": 30_000, "reduced": 27_000, "min_group": 10},
    "vibe_coding":    {"ref": 30_000, "reduced": 27_000, "min_group": 10},
}


def _extract_price(text: str) -> Optional[int]:
    """Extract the first integer price found in a text (e.g. '25 000 FCFA')."""
    # Remove spaces inside numbers: "25 000" -> "25000"
    normalized = re.sub(r"(\d)\s+(\d)", r"\1\2", text)
    match = re.search(r"\b(\d{4,7})\b", normalized)
    if match:
        return int(match.group(1))
    return None


def _extract_participant_count(text: str) -> Optional[int]:
    """Try to parse a participant count from payload text."""
    m = re.search(r"(\d+)\s*(?:participant|personne|etudiant|élève|apprenant)", text, re.IGNORECASE)
    if m:
        return int(m.group(1))
    return None


def validate_price_in_payload(action_type: str, payload: Dict[str, Any]) -> bool:
    """Return True if the price in `payload` respects the grids, False otherwise.

    Called by apply_commercial_rules before returning the final tier.
    A False result forces tier to HIGH regardless of the LLM proposal.
    """
    payload_text = " ".join(str(v) for v in payload.values()).lower()
    proposed_price = _extract_price(payload_text)
    if proposed_price is None:
        # No explicit price → no violation, let other rules decide
        return True

    participants = _extract_participant_count(payload_text)

    # --- Arduino rules ---
    if action_type in ("email_reply_arduino_pricing", "arduino_quote"):
        if proposed_price < ARDUINO_FLOOR_PRICE:
            return False  # Below absolute floor
        if proposed_price > ARDUINO_REF_PRICE:
            return False  # Above reference price
        # Degressivity is only allowed for large groups
        if proposed_price < ARDUINO_REF_PRICE:
            if participants is None or participants < ARDUINO_GROUP_THRESHOLD:
                return False  # Discount without justification
        return True

    # --- AI Training rules ---
    if action_type in ("email_reply_ai_training_pricing", "ai_training_quote"):
        for pack_name, pack in AI_PACKS.items():
            if pack_name in payload_text:
                ref = pack["ref"]
                reduced = pack["reduced"]
                min_group = pack["min_group"]
                # Price must not exceed reference
                if proposed_price > ref:
                    return False
                # Pack Initiation: no reduction allowed ever
                if reduced is None and proposed_price < ref:
                    return False
                # Other packs: reduced price only if group >= min_group
                if reduced is not None and proposed_price < ref:
                    if proposed_price < reduced:
                        return False  # Below minimum allowed reduction
                    if min_group and (participants is None or participants < min_group):
                        return False  # Reduction not justified
                return True
        # No pack matched — can't validate
        return True

    return True


# ---------------------------------------------------------------------------
# Main override function
# ---------------------------------------------------------------------------

def apply_commercial_rules(action_type: str, payload: Dict[str, Any], proposed_tier: str) -> str:
    """Deterministically overrides the LLM's proposed tier for commercial actions.

    Never downgrades a tier, only forces it to HIGH or MEDIUM based on rigid rules.
    """
    final_tier = proposed_tier

    # 1. Institutional → ALWAYS high
    if action_type == "email_reply_institutional":
        return TIER_HIGH

    # 2. Prospection first contact → ALWAYS high (Addendum 8 section 2.3)
    if action_type in ("prospection_first_contact", "prospection_followup"):
        return TIER_HIGH

    # 3. Alert keywords in any payload value
    payload_str = " ".join(str(v) for v in payload.values()).lower()
    for kw in ALERT_KEYWORDS:
        if kw in payload_str:
            return TIER_HIGH

    # 4. Price validation — force HIGH if price violates the grid
    if not validate_price_in_payload(action_type, payload):
        return TIER_HIGH

    # 5. Specific action-type rules
    if action_type in ("email_reply_arduino_pricing", "arduino_quote",
                       "email_reply_ai_training_pricing", "ai_training_quote"):
        if final_tier in (TIER_TRIVIAL, TIER_LOW):
            final_tier = TIER_HIGH

    elif action_type == "email_reply_generic_inquiry":
        if final_tier == TIER_TRIVIAL:
            final_tier = TIER_LOW

    # 6. Never downgrade — only upgrade
    tier_ranks = {TIER_TRIVIAL: 0, TIER_LOW: 1, TIER_MEDIUM: 2, TIER_HIGH: 3}
    return max(final_tier, proposed_tier, key=lambda t: tier_ranks.get(t, 2))
