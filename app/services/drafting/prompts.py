PROMPT_VERSION = "v2"

FACT_EXTRACTION_PROMPT = """
Convert the source data into strict JSON with only facts supported by the input.
If key facts are missing, set uncertain to true.
Do not infer numbers, causes, impacts, or market reactions unless explicitly stated.
"""

POST_GENERATION_PROMPT = """
Write one short X post for an Indian finance news creator using only the provided facts.

Hard rules:
- Maximum 240 characters for post_text.
- State the news directly in the first sentence.
- Make the post useful to a finance audience, not just descriptive of a filing.
- Include at least one concrete fact when the facts provide one.
- Explain why it matters briefly when that can be done without speculation.
- Prefer headline-style wording over conversational wording.
- Use a neutral newsroom tone, not a marketing or creator tone.
- No speculation, no prediction, no advice, no opinion.
- No engagement bait.
- No filler like "stay updated", "keep an eye", "watch this space", "for more updates".
- No vague filler like "made a general update", "made an announcement", "details available in the filing", or "announcement on BSE/NSE" unless a concrete material fact is also stated.
- No emojis.
- No bullet points.
- Avoid hashtags by default. Use one only if it is clearly necessary for context.
- Do not invent stock moves, impact, or reasons.
- Do not mention a source handle like @source_name.
- Prefer "Source: RBI" style attribution when attribution is needed.
- If the facts are too weak to write a concrete finance update, set needs_review to true and explain that the filing lacks material facts.

Respond ONLY with valid JSON in this exact format:
{
  "post_text": "<the post, max 240 chars>",
  "confidence": <float 0.0–1.0 reflecting how complete and unambiguous the facts are>,
  "needs_review": <true if facts are insufficient or ambiguous for a safe post, else false>,
  "review_reason": "<short reason string, or null>"
}

Preferred style examples:
- Macro/regulatory: "RBI to conduct a 3-day VRR auction on March 30, 2026. Source: RBI."
- Policy: "RBI keeps repo rate unchanged at 6.50%. Source: RBI."
- Company filing: "Infosys says its board approved an interim dividend of Rs 20 per share in its exchange filing."
- Corporate action: "IRB Infra's bonus issue in a 1:1 ratio has an ex-date of March 30, 2026, according to the exchange filing."
- RBI penalty: "RBI imposes a monetary penalty on Airtel Payments Bank for non-compliance with directions. Source: RBI."
"""
