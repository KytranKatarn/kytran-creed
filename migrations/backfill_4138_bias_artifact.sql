-- #4138 — one-time backfill: retire invalid bias-sampler fairness events.
--
-- The hub inline bias sampler (platform services/bias_sampling_service.py) emitted
-- governance events (event_type='bias_detected', category='fairness') that the
-- FIXED sampler would never produce. Two classes are invalid:
--
--   (a) SIGN BUG — bias_score runs -1.0 (biased) .. +1.0 (fair), but the old gate
--       used abs() and fired on strongly-FAIR responses. A +0.984 output emitted a
--       'violation'. (score >= 0)
--   (b) CIRCULAR SAMPLING — agents whose job is analyzing news/bias (fact_check*,
--       bias*, factcheck*, geo_extraction) were sampled for bias. The rater conflates
--       'discusses biased news' with 'is biased' (a geo_extraction listing Canadian
--       cities scored -0.875 'high bias').
--
-- Combined, these fabricated the What The Fact public tenant fairness score (46.3/F).
--
-- This is NON-DESTRUCTIVE: invalid events are moved to category 'fairness_retired_4138'
-- (ignored by the 6-pillar scorer in services/scoring_engine.py) with original
-- category + reason stamped in metadata. Fully reversible. GENUINE bias detections
-- (negative score AND a non-news capability) are left untouched as real fairness signal.
--
-- Apply:  docker exec -i creed_postgres psql -U creed -d creed < migrations/backfill_4138_bias_artifact.sql

BEGIN;

UPDATE governance_events
SET category = 'fairness_retired_4138',
    metadata = COALESCE(metadata, '{}'::jsonb)
               || jsonb_build_object(
                    'retired_by', '#4138',
                    'original_category', 'fairness',
                    'reason', CASE
                       WHEN (substring(description from 'score=(-?[0-9.]+)'))::float >= 0
                         THEN 'sign_bug_fair_scored_as_violation'
                       ELSE 'circular_news_analysis_capability' END)
WHERE category = 'fairness'
  AND event_type = 'bias_detected'
  AND (
        (substring(description from 'score=(-?[0-9.]+)'))::float >= 0
        OR lower(COALESCE(substring(description from 'Bias sampled on [^(]*\(([^)]+)\)'), ''))
             ~ '^(bias|fact_check|factcheck|geo_extraction)'
      );

-- Report what was retired, per tenant.
SELECT t.slug,
       count(*)                                         AS retired,
       count(*) FILTER (WHERE g.metadata->>'reason' = 'sign_bug_fair_scored_as_violation')  AS sign_bug,
       count(*) FILTER (WHERE g.metadata->>'reason' = 'circular_news_analysis_capability')  AS circular
FROM governance_events g JOIN tenants t ON t.id = g.tenant_id
WHERE g.category = 'fairness_retired_4138'
GROUP BY t.slug ORDER BY t.slug;

COMMIT;
