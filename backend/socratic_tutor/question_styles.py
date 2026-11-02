import random

# Neutral, open-ended prompts: none reveal or hint at the answer.
STYLES: dict[str, str] = {
    "what_does": "Ask what this part of the code is doing, in the learner's own words.",
    "designed_for": "Ask what this code was designed for, or what problem it exists to solve.",
    "inputs_outputs": "Ask what goes in and what comes out, and what the learner expects them to look like.",
    "why_here": "Ask why this logic might live at this place in the file rather than somewhere else.",
    "what_if_removed": "Ask what the learner thinks would change if this code were removed.",
    "who_calls": "Ask what the learner thinks calls or depends on this code, and why.",
    "walk_through": "Ask the learner to walk through the code line by line for a sample input.",
    "edge_cases": "Ask what unusual inputs or situations the learner thinks this code has to handle.",
    "summarize": "Ask the learner to summarize this in one sentence, as if telling a teammate.",
    "surprising": "Ask whether anything in this snippet surprises or confuses them.",
}


def pick_style(recent: list[str], rng: random.Random | None = None) -> str:
    """Pick a style not used recently so consecutive questions differ."""
    rng = rng or random
    fresh = [s for s in STYLES if s not in recent]
    if not fresh:
        fresh = [s for s in STYLES if s != (recent[-1] if recent else None)]
    return rng.choice(fresh)
