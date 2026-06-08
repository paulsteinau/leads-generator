# pipeline/utils/claude_p.py
import os
import anthropic

_client: anthropic.Anthropic | None = None

INPUT_COST = {
    "claude-haiku-4-5-20251001": 0.80 / 1_000_000,
    "claude-haiku-4-5": 0.80 / 1_000_000,
    "claude-sonnet-4-5": 3.00 / 1_000_000,
    "claude-sonnet-4-6": 3.00 / 1_000_000,
    "claude-opus-4-8": 15.00 / 1_000_000,
}
OUTPUT_COST = {
    "claude-haiku-4-5-20251001": 4.00 / 1_000_000,
    "claude-haiku-4-5": 4.00 / 1_000_000,
    "claude-sonnet-4-5": 15.00 / 1_000_000,
    "claude-sonnet-4-6": 15.00 / 1_000_000,
    "claude-opus-4-8": 75.00 / 1_000_000,
}


def _get_client() -> anthropic.Anthropic:
    global _client
    if _client is None:
        _client = anthropic.Anthropic(api_key=os.environ["ANTHROPIC_API_KEY"])
    return _client


def claude_p(
    prompt: str,
    system: str = "",
    model: str = "claude-haiku-4-5-20251001",
    max_tokens: int = 4096,
    lead_id: int = 0,
    stage: str = "",
    conn=None,
    image_b64: str | None = None,
    image_media_type: str = "image/jpeg",
) -> str:
    """Call Claude and return the text response. Logs cost to DB if conn provided.
    Pass image_b64 to include a vision input alongside the text prompt."""
    client = _get_client()

    if image_b64:
        content = [
            {
                "type": "image",
                "source": {
                    "type": "base64",
                    "media_type": image_media_type,
                    "data": image_b64,
                },
            },
            {"type": "text", "text": prompt},
        ]
    else:
        content = prompt

    kwargs: dict = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": content}],
    }
    if system:
        kwargs["system"] = system

    resp = client.messages.create(**kwargs)
    text = resp.content[0].text

    if conn and lead_id:
        in_tok = resp.usage.input_tokens
        out_tok = resp.usage.output_tokens
        cost = (in_tok * INPUT_COST.get(model, 0.80 / 1_000_000)) + \
               (out_tok * OUTPUT_COST.get(model, 4.00 / 1_000_000))
        conn.execute(
            "INSERT INTO cost_log (lead_id, model, stage, input_tokens, output_tokens, cost_usd)"
            " VALUES (?,?,?,?,?,?)",
            (lead_id, model, stage, in_tok, out_tok, round(cost, 6)),
        )
        conn.commit()

    return text
