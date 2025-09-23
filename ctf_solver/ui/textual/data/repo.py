from typing import List, Tuple

from ctf_solver.database.db import get_db_cursor


def fetch_jobs() -> List[Tuple]:
    sql = """
    WITH last_step AS (
        SELECT s.attempt_id, MAX(s.created_at) AS last_ts
        FROM steps s
        GROUP BY s.attempt_id
    )
    SELECT a.id::text AS attempt_id,
           c.name,
           CASE
             WHEN a.status = 'running' AND COALESCE(NOW() - ls2.last_ts, NOW() - a.started_at) > INTERVAL '120 seconds'
               THEN 'stale'
             ELSE a.status
           END AS status,
           COALESCE(a.total_steps, 0) AS steps,
           a.started_at,
           COALESCE(ls.last_action, ''),
           COALESCE(ls.last_output, ''),
           COALESCE(a.flag, '')
    FROM attempts a
    JOIN challenges c ON a.challenge_id = c.id
    LEFT JOIN last_step ls2 ON ls2.attempt_id = a.id
    LEFT JOIN LATERAL (
        SELECT COALESCE(s.action->>'cmd', s.action->>'tool') AS last_action,
               LEFT(COALESCE(encode(s.output, 'escape'), ''), 100) AS last_output
        FROM steps s
        WHERE s.attempt_id = a.id
        ORDER BY s.step_num DESC
        LIMIT 1
    ) ls ON TRUE
    ORDER BY a.started_at DESC
    LIMIT 100;
    """
    with get_db_cursor() as cur:
        cur.execute(sql)
        return cur.fetchall()


def fetch_logs(attempt_id: str) -> List[Tuple]:
    sql = """
    SELECT step_num,
           COALESCE(action->>'cmd', action->>'tool') AS action,
           LEFT(COALESCE(encode(output, 'escape'), ''), 500),
           execution_time_ms,
           COALESCE(action->>'analysis','') AS analysis,
           COALESCE(action->>'approach','') AS approach
    FROM steps
    WHERE attempt_id = %s
    ORDER BY step_num ASC
    LIMIT 200;
    """
    with get_db_cursor() as cur:
        cur.execute(sql, (attempt_id,))
        return cur.fetchall()


