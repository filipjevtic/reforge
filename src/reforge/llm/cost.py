"""Token-to-cost accounting from a small, editable pricing table.

Prices are USD per million tokens (input, output). The table is intentionally
simple and local; update it as prices change. Unknown models cost 0 and are
flagged so a run never crashes just because a price is missing.
"""

from __future__ import annotations

from dataclasses import dataclass

# USD per 1M tokens: model -> (input, output). Prefix matches are allowed.
PRICING: dict[str, tuple[float, float]] = {
    "claude-opus-4": (15.0, 75.0),
    "claude-sonnet-4": (3.0, 15.0),
    "claude-haiku-4": (1.0, 5.0),
    "gpt-4.1": (2.0, 8.0),
    "gpt-4o": (2.5, 10.0),
    "o4-mini": (1.1, 4.4),
    "gemini-2.5-pro": (1.25, 10.0),
    "gemini-2.5-flash": (0.30, 2.50),
    "kimi": (0.60, 2.50),
}


@dataclass
class Price:
    input_per_mtok: float
    output_per_mtok: float
    known: bool


def price_for(model: str | None) -> Price:
    if not model:
        return Price(0.0, 0.0, known=False)
    for prefix, (pin, pout) in PRICING.items():
        if model.startswith(prefix):
            return Price(pin, pout, known=True)
    return Price(0.0, 0.0, known=False)


def compute_cost(model: str | None, input_tokens: int, output_tokens: int) -> float | None:
    """USD cost for a call, or None if the model's price is unknown."""
    price = price_for(model)
    if not price.known:
        return None
    return round(
        input_tokens / 1_000_000 * price.input_per_mtok
        + output_tokens / 1_000_000 * price.output_per_mtok,
        6,
    )
