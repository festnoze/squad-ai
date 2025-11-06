SELECT
	SUM(1) AS total_records,
	MAX(ROUND(char_length(content_full) / 4.5)) AS max_full_content_tokens,
	MIN(ROUND(char_length(content_full) / 4.5)) AS min_full_content_tokens,
	MAX(ROUND(char_length(content_summary_full) / 4.5)) AS max_summary_full_tokens,
	MIN(ROUND(char_length(content_summary_full) / 4.5)) AS min_summary_full_tokens,
	ROUND(AVG(char_length(content_full) / 4.5)) AS avg_full_content_tokens,
    ROUND(AVG(char_length(content_summary_full) / 4.5)) AS avg_summary_full_tokens,
    ROUND(AVG(char_length(content_summary_light) / 4.5)) AS avg_summary_light_tokens,
    ROUND(AVG(char_length(content_summary_compact) / 4.5)) AS avg_summary_compact_tokens
FROM contents
WHERE content_summary_full IS NOT NULL;
