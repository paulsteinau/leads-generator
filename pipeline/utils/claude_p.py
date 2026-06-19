# pipeline/utils/claude_p.py
import os
from collections.abc import Callable
import anthropic

_client: anthropic.Anthropic | None = None

# Prices per token (not per million) — verify at console.anthropic.com/settings/plans
INPUT_COST = {
    "claude-haiku-4-5-20251001": 0.80 / 1_000_000,
    "claude-haiku-4-5":          0.80 / 1_000_000,
    "claude-sonnet-4-5":         3.00 / 1_000_000,
    "claude-sonnet-4-6":         3.00 / 1_000_000,
    "claude-opus-4-8":           5.00 / 1_000_000,
    "claude-fable-5":            10.00 / 1_000_000,  # $10/MTok input (2x Opus)
}
OUTPUT_COST = {
    "claude-haiku-4-5-20251001": 4.00 / 1_000_000,
    "claude-haiku-4-5":          4.00 / 1_000_000,
    "claude-sonnet-4-5":         15.00 / 1_000_000,
    "claude-sonnet-4-6":         15.00 / 1_000_000,
    "claude-opus-4-8":           25.00 / 1_000_000,
    "claude-fable-5":            50.00 / 1_000_000,  # $50/MTok output (2x Opus)
}
# Cache read = 10% of input price; cache write = 125% of input price
CACHE_READ_MULTIPLIER  = 0.10
CACHE_WRITE_MULTIPLIER = 1.25


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
    generation_num: int = 1,
    on_progress: Callable[[int], None] | None = None,
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

    if on_progress is not None:
        # Streaming mode: call on_progress(char_count) every ~2000 chars for real-time visibility
        text = ""
        prev_report = 0
        with client.messages.stream(**kwargs) as stream:
            for chunk in stream.text_stream:
                text += chunk
                if len(text) - prev_report >= 2000:
                    on_progress(len(text))
                    prev_report = len(text)
            final = stream.get_final_message()
        in_tok      = final.usage.input_tokens
        out_tok     = final.usage.output_tokens
        cache_read  = getattr(final.usage, "cache_read_input_tokens", 0) or 0
        cache_write = getattr(final.usage, "cache_creation_input_tokens", 0) or 0
    else:
        resp = client.messages.create(**kwargs)
        # Find the text block — thinking blocks come first when adaptive thinking is active
        text = next(
            (block.text for block in resp.content if block.type == "text"),
            resp.content[0].text,
        )
        in_tok      = resp.usage.input_tokens
        out_tok     = resp.usage.output_tokens
        cache_read  = getattr(resp.usage, "cache_read_input_tokens", 0) or 0
        cache_write = getattr(resp.usage, "cache_creation_input_tokens", 0) or 0

    if conn and lead_id:

        in_price  = INPUT_COST.get(model, 3.00 / 1_000_000)   # default: Sonnet, not Haiku
        out_price = OUTPUT_COST.get(model, 15.00 / 1_000_000)

        cost = (
            in_tok      * in_price +
            out_tok     * out_price +
            cache_read  * in_price * CACHE_READ_MULTIPLIER +
            cache_write * in_price * CACHE_WRITE_MULTIPLIER
        )
        conn.execute(
            "INSERT INTO cost_log"
            " (lead_id, model, stage, input_tokens, output_tokens,"
            "  cache_read_tokens, cache_write_tokens, cost_usd, generation_num)"
            " VALUES (?,?,?,?,?,?,?,?,?)",
            (lead_id, model, stage, in_tok, out_tok,
             cache_read, cache_write, round(cost, 6), generation_num),
        )
        conn.commit()
        print(
            f"[cost] lead={lead_id} gen={generation_num} stage={stage} model={model}"
            f" in={in_tok} out={out_tok} cache_r={cache_read} cache_w={cache_write}"
            f" → ${cost:.4f}"
        )

    return text
