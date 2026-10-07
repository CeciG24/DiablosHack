-- Open data/runs/<CURRENT>/diablos.duckdb with any DuckDB client.
SELECT * FROM summary_year ORDER BY year;

-- Rules that need organizer confirmation.
SELECT rule, count(*) AS issues
FROM quality_issues GROUP BY rule ORDER BY issues DESC;

-- Label availability is distinct from total row count.
SELECT season_split, count(*) AS rows,
       count(y_event) AS known_events,
       sum(CAST(eligible_stuff_default AS INTEGER)) AS usable_stuff
FROM model_base GROUP BY season_split;

-- Conditional whiff rate; denominator is swings with valid labels.
SELECT altitude_category,
       count(y_whiff_given_swing) AS valid_swings,
       avg(y_whiff_given_swing) AS whiff_rate
FROM model_base WHERE season_split='train'
GROUP BY altitude_category;

-- Historical arsenal is explicit and optional.
SELECT p.year, count(*) AS pitches,
       sum(CAST(a.has_prior_fastball_reference AS INTEGER)) AS with_reference
FROM arsenal_features a JOIN pitches p USING(pitch_uid)
GROUP BY p.year ORDER BY p.year;
