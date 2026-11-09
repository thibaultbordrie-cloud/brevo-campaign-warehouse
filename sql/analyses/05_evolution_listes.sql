-- Size of each contact list at the latest snapshot, with the change since the previous snapshot.
-- The change columns stay empty until the pipeline has run on two different days.
SELECT name,
       subscribers,
       change_subscribers,
       total_blacklisted,
       change_blacklisted
FROM v_list_growth
WHERE snapshot_date = (SELECT MAX(snapshot_date) FROM fact_list_size)
ORDER BY subscribers DESC;
