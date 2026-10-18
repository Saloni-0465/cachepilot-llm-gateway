"""Configurable per-model cost estimates; pricing is not hard-coded."""

import json
import os
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from cachepilot.schemas import TokenUsage

_COST_QUANTUM = Decimal("0.00000001")


def estimate_cost_usd(
    provider_name: str, model: str, usage: TokenUsage
) -> Decimal | None:
    """Estimate cost from configured USD-per-million-token rates.

    The mock provider is free. For OpenAI, set OPENAI_MODEL_PRICING_JSON to a
    JSON object keyed by model ID. Without a matching model entry, the legacy
    provider-wide environment variables are used when both are configured.
    """
    if provider_name == "mock":
        return Decimal("0")

    try:
        configured = json.loads(os.getenv("OPENAI_MODEL_PRICING_JSON", "{}"))
    except (json.JSONDecodeError, TypeError):
        configured = {}

    model_rates = configured.get(model) if isinstance(configured, dict) else None
    if isinstance(model_rates, dict):
        input_rate = model_rates.get("input_usd_per_1m_tokens")
        output_rate = model_rates.get("output_usd_per_1m_tokens")
    else:
        input_rate = os.getenv("OPENAI_INPUT_PRICE_USD_PER_1M_TOKENS")
        output_rate = os.getenv("OPENAI_OUTPUT_PRICE_USD_PER_1M_TOKENS")

    if input_rate is None or output_rate is None:
        return None

    try:
        input_price = Decimal(str(input_rate))
        output_price = Decimal(str(output_rate))
    except (InvalidOperation, ValueError):
        return None
    if (
        not input_price.is_finite()
        or not output_price.is_finite()
        or input_price < 0
        or output_price < 0
    ):
        return None

    cost = (
        Decimal(usage.prompt_tokens) * input_price
        + Decimal(usage.completion_tokens) * output_price
    ) / Decimal(1_000_000)
    return cost.quantize(_COST_QUANTUM, rounding=ROUND_HALF_UP)
