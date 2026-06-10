# pipeline/utils/claude_p.py
import os
import anthropic

_client: anthropic.Anthropic | None = None

INPUT_COST = {
    "claude-haiku-4-5-20251001": 0.80 / 1_000_000,
    "claude-haiku-4-5": 0.80 / 1_000_000,
    "claude-sonnet-4-5": 3.00 / 1_000_000,
    "claude-sonnet-4-6": 3.00 / 1_000_000,
    "claude-opus-4-8": 5.00 / 1_000_000,
}
OUTPUT_COST = {
    "claude-haiku-4-5-20251001": 4.00 / 1_000_000,
    "claude-haiku-4-5": 4.00 / 1_000_000,
    "claude-sonnet-4-5": 15.00 / 1_000_000,
    "claude-sonnet-4-6": 15.00 / 1_000_000,
    "claude-opus-4-8": 25.00 / 1_000_000,
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
    images: list[tuple[str, str]] | None = None,
    thinking: dict | None = None,
) -> str:
    """Call Claude and return the text response. Logs cost to DB if conn provided.
    Pass image_b64 for a single image, or images=[(b64, media_type), ...] for multiple.
    Pass thinking={"type": "adaptive"} to enable adaptive thinking on supported models."""
    client = _get_client()

    # Build image blocks: images list takes precedence over single image_b64
    img_list = images or ([(image_b64, image_media_type)] if image_b64 else [])

    if img_list:
        content = [
            {
                "type": "image",
                "source": {"type": "base64", "media_type": mt, "data": b64},
            }
            for b64, mt in img_list
        ] + [{"type": "text", "text": prompt}]
    else:
        content = prompt

    kwargs: dict = {
        "model": model,
        "max_tokens": max_tokens,
        "messages": [{"role": "user", "content": content}],
    }
    if system:
        kwargs["system"] = [{"type": "text", "text": system, "cache_control": {"type": "ephemeral"}}]

    if thinking:
        kwargs["thinking"] = thinking

    # Extended output beta required for max_tokens > 8192
    if max_tokens > 8192:
        kwargs["extra_headers"] = {"anthropic-beta": "output-128k-2025-02-19"}

    resp = client.messages.create(**kwargs)

    # Find the text block — thinking blocks come first when adaptive thinking is active
    text = next(
        (block.text for block in resp.content if block.type == "text"),
        resp.content[0].text,
    )

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
