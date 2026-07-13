# Kramp News Feed — Configuration & Tuning Guide

The classified, scored, clustered news feed is driven entirely by
`feed_config.json`. Change that file and the API will pick up your edits on
the next cache refresh (12h, or restart the mount to force it).

This guide explains what each knob does, how items flow through the pipeline,
and how to tune the model.

---

## 1. Pipeline overview

```
RSS sources (config.sources with rss_url)
        │
        ▼
   parseRss()          ← strips HTML, decodes entities, cleans AGCO template
        │
        ▼
   dedupe by URL       ← canonicalises URLs, keeps highest-tier source
        │
        ▼
   detect countries    ← source defaults + regex text scan
   detect industries   ← source defaults + config.industry_keywords
   classify type       ← regex rules (12 article types)
   detect strategic    ← config.strategic_signal_keywords
   compute scores      ← weighted sum per section
   assign section      ← thresholds + article type + age
        │
        ▼
   cluster titles      ← Jaccard similarity ≥ config.thresholds.cluster_similarity
        │
        ▼
   emit sections       ← must_reads, market_pulse, latest_signals, archive
```

Each item retains its **raw** fields (`raw_title`, `raw_url`, etc.) alongside
enriched fields, so no source data is destroyed by the pipeline.

---

## 2. Sections & thresholds

`config.thresholds`:

| Key | Meaning | Default |
|---|---|---|
| `days_latest_signals` | Max age for the Latest Signals section | 14 |
| `days_market_pulse` | Max age for Market Pulse | 45 |
| `days_must_reads` | Max age for Must-Reads | 180 |
| `min_score_latest_signals` | Min `score_latest` to appear in Latest | 55 |
| `min_score_market_pulse` | Min `score_pulse` to appear in Market Pulse | 65 |
| `min_score_must_reads` | Min `score_must_reads` to appear in Must-Reads | 75 |
| `cluster_similarity` | Jaccard threshold to merge titles into a cluster | 0.55 |
| `dedupe_title_similarity` | (Reserved for future title-dedupe) | 0.85 |

**Must-Reads** additionally requires the item's `article_type` to be one of:
`data_release`, `association_report`, `market_report`, `oem_financial_result`,
`regulation_policy`. This keeps generic press releases out even if their score
is high.

**Recommended UI default** (`_meta`): `min_score_visible: 60` — items below this
score are still returned by the API but the UI hides them until the user lowers
the "Min score" slider.

---

## 3. Scoring

Each item gets **six sub-scores** (0–100):

| Score | How it's computed |
|---|---|
| `source_score` | tier 1 → 95, tier 2 → 75, tier 3 → 45 |
| `industry_score` | 80 if any industry detected, else 40 |
| `country_score` | 80 if EU-wide, 70 if a specific country, 55 if only Global, 50 if none |
| `article_type_score` | Direct lookup in `config.article_type_scores` |
| `strategic_score` | 40 + 12·min(3, high_hits) + 5·min(4, medium_hits) − 15·min(3, noise_hits) |
| `recency_score` | `100 × (1 − age_days / shelf_life)` clamped to 0–100 |

Shelf life is defined per article type in `config.article_type_shelf_life_days`.
For example, an `association_report` has 180-day shelf life; a `generic_press_release` has 3 days.
This is why a CEMA Barometer stays visible for months while a "Distributor announces new hire" decays in 72h.

The **final score for a section** is a weighted sum of the six sub-scores,
using the weights in `config.scoring_weights[section]`:

```
score_latest = source·0.20 + industry·0.15 + country·0.10 + article_type·0.15 + strategic·0.20 + recency·0.20
score_pulse  = source·0.25 + industry·0.20 + country·0.15 + article_type·0.15 + strategic·0.15 + recency·0.10
score_reads  = source·0.30 + industry·0.20 + country·0.10 + article_type·0.20 + strategic·0.15 + recency·0.05
```

The **`relevance_score`** shown in the UI badge is `score_pulse` — the neutral middle option.

---

## 4. Tuning recipes

### "I see too many trade-media stories in Market Pulse"
Raise `min_score_market_pulse` from 65 → 70 or 72.

### "I see too few must-reads"
Lower `min_score_must_reads` from 75 → 70, OR add more allowed article types
in `assignSection()` in the API mount script (harder — code change).

### "The ECB feed is spamming me with speeches"
Options:
- Downgrade `ECB Monetary Policy Decisions` source_tier from 1 → 2 in the config.
- Or: add "speech" to `strategic_signal_keywords.noise_indicators`.

### "I want German ag registrations to always show up"
- Ensure `VDMA Agricultural Machinery` is `must_monitor: true` (already set).
- Because VDMA has no RSS, it appears in the "Manual Watch" panel with a
  homepage link. To have items auto-flow in, add a scraper (out of scope of
  this guide — write it as a separate API mount).

### "Country X should include EU-wide items automatically"
Add the country's code to `config.eu_wide_bleeds_to_countries`.

### "This keyword should count as strategic"
Add it to `config.strategic_signal_keywords.high_value` (12-point boost each)
or `.medium_value` (5-point boost).

### "This keyword should mark an item as noise"
Add it to `config.strategic_signal_keywords.noise_indicators` (15-point penalty).

---

## 5. Sources: adding, removing, editing

Each entry in `config.sources` has:

| Field | Notes |
|---|---|
| `name` | Display name |
| `rss_url` | Set to `null` for watch-only sources (they'll show in the Manual Watch panel) |
| `homepage_url` | Always required — used as fallback link |
| `source_tier` | 1 = official/OEM IR/association; 2 = trade media/company; 3 = generic |
| `source_reliability` | 1–5 informational (not used in scoring yet) |
| `default_industries` | Array — e.g. `["agriculture", "competitors"]` |
| `default_countries` | Array — the country tag applied even if the article text says nothing |
| `source_type` | Fallback `article_type` when text classification returns nothing |
| `must_monitor` | Highlights the source in the Manual Watch panel |
| `active` | Set to `false` to disable the source without deleting it |
| `refresh_frequency` | Human-readable; not used for automation yet |
| `watch_method` | `rss`, `api`, `web_monitoring`, `email` |
| `notes` | Free-form. Shows in the Manual Watch panel. |

**To add a new RSS source** (e.g. a national ag ministry with a feed):
1. Add an entry with `active: true, rss_url: "…"`.
2. Save `feed_config.json`.
3. Wait 12h or force a cache bust (change the cache key in the mount script, or hit the endpoint after clearing cache).

---

## 6. Country tagging behaviour

An item gets one or more country tags via:
1. **Source defaults**: `default_countries` on the source config.
2. **Text scan**: regex rules in `detectCountries()` inside the API mount.

**EU-wide bleed**: If the country filter is set to (say) Germany, items tagged
`EU-wide` are still included, but with `country_score` weighting reduced to 70.
This is why ECB rate decisions show up when filtering by Germany, France, etc.

`Global` items only bleed into country views with `country_score` 45 — much
lower priority.

---

## 7. Article types & shelf life

| Type | Base score | Shelf life | Example |
|---|---|---|---|
| `data_release` | 95 | 180d | Monthly tractor registrations |
| `association_report` | 92 | 180d | CEMA Business Barometer |
| `market_report` | 90 | 180d | McKinsey Ag Report |
| `oem_financial_result` | 88 | 120d | AGCO Q2 earnings |
| `regulation_policy` | 82 | 365d | Stage V, right-to-repair |
| `macroeconomic_update` | 80 | 90d | ECB rate decision |
| `weather_crop_update` | 75 | 30d | Drought reports |
| `competitor_news` | 72 | 60d | Granit expansion |
| `supplier_news` | 68 | 60d | Component shortage |
| `trade_media_article` | 55 | 21d | Farming UK daily story |
| `product_launch` | 40 | 14d | New tractor model |
| `event_announcement` | 25 | 7d | Agritechnica preview |
| `generic_press_release` | 20 | 3d | Sponsor news |

Tune these numbers directly in `feed_config.json`.

---

## 8. "Why this matters for Kramp"

Templates in `config.why_it_matters_templates` are keyed by
`<article_type>+<primary_industry>`. Add new keys to override the default
message. Example:

```json
"data_release+agriculture": "Machinery registration data drives Kramp's medium-term spare-parts demand model…"
```

If no key matches, the `default` template is used.

**Future**: this can be swapped for an LLM call (Gemini/GPT) to generate
per-article summaries. Keep the template list as the fallback for cost/quota
protection.

---

## 9. Clustering

Two items are considered the same story when their titles have
Jaccard similarity ≥ `config.thresholds.cluster_similarity` (default 0.55).
The cluster keeps the highest-tier source as the representative and hides
the rest behind a "+N related" chip in the UI.

To be more aggressive about deduping (e.g. multiple trade outlets covering
one CEMA report), raise the threshold; to be more permissive (show each
outlet's version), lower it.

**Note**: This is token-overlap similarity, not semantic. A CEMA report
covered by five outlets with divergent headlines may not merge. If this
becomes a problem we can add a second pass using entity matching or hand
off to an embedding API — but for now, keep it simple.

---

## 10. Sample test cases

See `feed_sample_tests.json` for canonical examples of each article type
and where they should end up. Run the same URLs through the pipeline to
verify scoring doesn't regress after config changes.
