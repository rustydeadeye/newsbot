-- Migration 002: SEBI/PIB source fixes
-- Run this in Supabase SQL editor (or psql).

-- PIB's RSS endpoint (ViewRss.aspx?lang=1&reg=31) returns JavaScript-rendered HTML,
-- not XML. Disabling until a working scraper (headless browser) is implemented.
update sources
set enabled = false,
    metadata = metadata || '{"disabled_reason": "pib_rss_returns_html_not_xml"}'::jsonb
where name = 'pib_economy';
