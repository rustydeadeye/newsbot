PROMPT_VERSION = "v3"
AI_WIRE_PROMPT_VERSION = "ai_v3"
INSTAGRAM_CAROUSEL_PROMPT_VERSION = "instagram_v1"

FACT_EXTRACTION_PROMPT = """
Convert the source data into strict JSON with only facts supported by the input.
If key facts are missing, set uncertain to true.
Do not infer numbers, causes, impacts, or market reactions unless explicitly stated.
"""

POST_GENERATION_PROMPT = """
Write one short X post for an Indian finance news feed using only the provided facts.

Hard rules:
- Maximum 240 characters for post_text.
- Lead with the news immediately.
- Prefer a crisp public-facing finance update over a filing summary or newsroom attribution block.
- Include concrete figures, dates, or comparisons when the facts provide them.
- Keep the wording compact and publishable within seconds.
- Use a neutral newsroom tone, not a marketing or creator tone.
- No speculation, no prediction, no advice, no opinion.
- No engagement bait.
- No explanatory framing unless it is explicitly supported by the facts.
- No filler like "stay updated", "keep an eye", "watch this space", "for more updates".
- No vague filler like "made a general update", "made an announcement", "details available in the filing", or "announcement on BSE/NSE" unless a concrete material fact is also stated.
- No inferred benefits, impacts, market reactions, or investor outcomes.
- No emojis.
- No bullet points.
- Avoid hashtags by default. Use one only if it is clearly necessary for context.
- Do not invent stock moves, impact, or reasons.
- Do not mention a source handle like @source_name.
- Never include "Source:" attribution in the final post text.
- If the facts are too weak to write a concrete finance wire update, set needs_review to true and explain that the filing lacks material facts.

Respond ONLY with valid JSON in this exact format:
{
  "post_text": "<the post, max 240 chars>",
  "confidence": <float 0.0–1.0 reflecting how complete and unambiguous the facts are>,
  "needs_review": <true if facts are insufficient or ambiguous for a safe post, else false>,
  "review_reason": "<short reason string, or null>"
}

Preferred style examples:
- Macro/regulatory: "RBI to conduct a 3-day VRR auction on March 30, 2026."
- Policy: "RBI keeps repo rate unchanged at 6.50%."
- Company filing: "APL Apollo Tubes: Q4FY26 sales volume 924,881 ton (+9% YoY); FY26 sales volume 3,491,243 ton (+11% YoY)."
- Corporate action: "IRB Infra: bonus issue in a 1:1 ratio; ex-date March 30, 2026."
- RBI penalty: "RBI imposes a monetary penalty on Airtel Payments Bank for non-compliance with directions."
"""

AI_NEWS_POST_PROMPT = """
Write one short X post for a general-audience AI news feed using only the provided facts.

Hard rules:
- Maximum 240 characters for post_text.
- Use plain English that a general reader can follow.
- Keep concrete names, dates, prices, numbers, or limits when the facts provide them.
- Say what changed first, then why it matters.
- Explain who it affects when the facts make that clear.
- Sound like a sharp human explainer, not a robotic AI roundup.
- No hashtags, no emojis, no source attribution, no filler.
- Do not invent product capabilities, pricing, impact, or comparisons.
- Avoid vague phrasing like "signals momentum", "reflects growing interest", or generic AI commentary.
- If the facts are too vague, do not guess. Set needs_review to true.

Respond ONLY with valid JSON in this exact format:
{
  "post_text": "<the post, max 240 chars>",
  "confidence": <float 0.0–1.0>,
  "needs_review": <true or false>,
  "review_reason": "<short reason string, or null>"
}
"""

AI_EXPLAINED_POST_PROMPT = """
Write one short X post that explains a recent AI development in simple, useful language using only the provided facts.

Hard rules:
- Maximum 240 characters for post_text.
- Use plain English that a general reader can follow.
- Focus on what the update really means, not just what happened.
- Give one clear takeaway.
- Sound calm, clear, and human.
- Avoid jargon, benchmark shorthand, and generic AI hype.
- No hashtags, no emojis, no source attribution, no filler.
- Do not invent implications that are not grounded in the facts.
- If there is no clear explanatory takeaway, set needs_review to true.

Respond ONLY with valid JSON in this exact format:
{
  "post_text": "<the post, max 240 chars>",
  "confidence": <float 0.0–1.0>,
  "needs_review": <true or false>,
  "review_reason": "<short reason string, or null>"
}
"""

AI_FOR_BUSINESS_POST_PROMPT = """
Write one short X post that translates a recent AI development into practical business value using only the provided facts.

Hard rules:
- Maximum 240 characters for post_text.
- Use plain English that founders, operators, and small teams can follow.
- Focus on workflow impact, cost, adoption, or business usefulness.
- Keep the tone practical and grounded, not salesy.
- Avoid empty business buzzwords and hype.
- No hashtags, no emojis, no source attribution, no filler.
- Do not turn the post into a pitch.
- Do not invent ROI, savings, or adoption claims not supported by the facts.
- If there is no real business angle, set needs_review to true.

Respond ONLY with valid JSON in this exact format:
{
  "post_text": "<the post, max 240 chars>",
  "confidence": <float 0.0–1.0>,
  "needs_review": <true or false>,
  "review_reason": "<short reason string, or null>"
}
"""

AI_WIRE_POST_PROMPT = AI_NEWS_POST_PROMPT

INSTAGRAM_CAROUSEL_BLUEPRINT_PROMPT = """
Write a structured Instagram carousel blueprint in valid JSON using only the provided facts.

Hard rules:
- Keep the carousel informative, saveable, and human.
- Do not invent facts, numbers, dates, or capabilities.
- Return between 4 and 8 slides.
- Use only as many slides as the topic genuinely supports.
- Prefer shorter decks when extra slides would feel repetitive or padded.
- Slide 1 is a hook slide:
  - giant information-gap headline
  - no support body copy
- Interior slides:
  - short headline
  - very short support copy
  - keep each slide to roughly 15-30 words total
- The final slide is a closing CTA slide:
  - must include a specific save/share/follow CTA
  - must include the handle @newsbot in headline or support
- Respect the requested lane and its intent.
- Each slide role must be distinct and purposeful.
- Caption should include a short hook, body, and CTA.
- Avoid filler like "read caption".
- Use concise, punchy headline language suitable for a black high-contrast carousel.

Respond ONLY with valid JSON in this exact format:
{
  "title": "<title>",
  "hook": "<short hook>",
  "angle": "<editorial angle>",
  "carousel_type": "<type>",
  "slide_count": <int>,
  "slides": [
    {
      "slide_number": 1,
      "role": "<role>",
      "headline": "<headline>",
      "support": "<support>"
    }
  ],
  "caption": {
    "hook": "<caption hook>",
    "body": "<caption body>",
    "cta": "<caption cta>"
  }
}
"""
