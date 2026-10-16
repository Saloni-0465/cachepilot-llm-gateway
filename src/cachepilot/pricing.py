"""Configurable model cost estimates; provider pricing is not hard-coded."""

import os
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP

from cachepilot.schemas import TokenUsage

_COST_QUANTUM = Decimal("0.00000001")


def estimate_cost_usd(provider_name: str, usage: TokenUsage) -> Decimal | None:
    """Estimate cost from configured USD-per-million-token rates.

    The mock provider is free. For OpenAI, set current model-specific rates via
    environment variables; without both rates the estimate is unknown.
    """
    if provider_name == "mock":
        return Decimal("0")

    input_rate = os.getenv("OPENAI_INPUT_PRICE_USD_PER_1M_TOKENS")
    output_rate = os.getenv("OPENAI_OUTPUT_PRICE_USD_PER_1M_TOKENS")
    if not input_rate or not output_rate:
        return None

    try:
        input_price = Decimal(input_rate)
        output_price = Decimal(output_rate)
    except InvalidOperation:
        return None
    if input_price < 0 or output_price < 0:
        return None

    cost = (
        Decimal(usage.prompt_tokens) * input_price
        + Decimal(usage.completion_tokens) * output_price
    ) / Decimal(1_000_000)
    return cost.quantize(_COST_QUANTUM, rounding=ROUND_HALF_UP)
