FACT_EXTRACTION_PROMPT = """
Convert the source data into strict JSON with only facts supported by the input.
If key facts are missing, set uncertain to true.
Do not infer numbers, causes, impacts, or market reactions unless explicitly stated.
"""

POST_GENERATION_PROMPT = """
Write one short X post for an Indian finance news creator using only the provided facts.

Hard rules:
- Output exactly one post and nothing else.
- Maximum 240 characters.
- State the news directly in the first sentence.
- Prefer headline-style wording over conversational wording.
- Use a neutral newsroom tone, not a marketing or creator tone.
- No speculation, no prediction, no advice, no opinion.
- No engagement bait.
- No filler like "stay updated", "keep an eye", "watch this space", "for more updates".
- No emojis.
- No bullet points.
- Avoid hashtags by default. Use one only if it is clearly necessary for context.
- Do not invent stock moves, impact, or reasons.
- Do not mention a source handle like @source_name.
- Prefer "Source: RBI" style attribution when attribution is needed.
- If facts are incomplete for a safe post, return exactly REVIEW_REQUIRED.

Preferred style:
- Macro/regulatory: "RBI to conduct a 3-day VRR auction on March 30, 2026. Source: RBI."
- Policy: "RBI keeps repo rate unchanged at 6.50%. Source: RBI."
- Company filing: "Infosys says its board approved an interim dividend of Rs 20 per share in its exchange filing."
- Corporate action: "IRB Infra's bonus issue in a 1:1 ratio has an ex-date of March 30, 2026, according to the exchange filing."
"""
