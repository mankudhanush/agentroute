"""Local persistent routing memory (SQLite, standard library only).

Stores RoutingObservation rows and computes aggregate statistics that the
AdaptiveRoutingPolicy consults. No third-party database dependency.

DATA-SAFETY: only the fields on RoutingObservation are stored (see that module).
No prompts, keys, headers, or raw API responses are persisted.
"""

import os
import sqlite3
from typing import Optional

from routing_observation import RoutingObservation

# Persistent DB lives next to this module so it is stable regardless of cwd.
DEFAULT_DB_PATH = os.path.join(os.path.dirname(__file__), "routing_memory.db")

_SCHEMA = """
CREATE TABLE IF NOT EXISTS routing_observations (
    id               INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp        REAL    NOT NULL,
    task_id          TEXT,
    intent           TEXT    NOT NULL,
    complexity       TEXT    NOT NULL,
    confidence       REAL,
    selected_agent   TEXT    NOT NULL,
    response_success INTEGER NOT NULL,
    latency_ms       INTEGER,
    user_feedback    TEXT,
    outcome_score    REAL,
    policy           TEXT
);
"""


class RoutingMemory:
    def __init__(self, db_path: str = DEFAULT_DB_PATH):
        self.db_path = db_path
        self.conn = sqlite3.connect(db_path)
        self.conn.row_factory = sqlite3.Row
        self.conn.executescript(_SCHEMA)
        self.conn.commit()

    def close(self) -> None:
        self.conn.close()

    # Context-manager sugar so tests/callers can use `with RoutingMemory(p) as m:`
    def __enter__(self):
        return self

    def __exit__(self, *exc):
        self.close()

    # --- writes -------------------------------------------------------------
    def record_observation(self, obs: RoutingObservation) -> int:
        cur = self.conn.execute(
            """
            INSERT INTO routing_observations (
                timestamp, task_id, intent, complexity, confidence,
                selected_agent, response_success, latency_ms,
                user_feedback, outcome_score, policy
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                obs.timestamp,
                obs.task_id,
                obs.intent,
                obs.complexity,
                obs.confidence,
                obs.selected_agent,
                1 if obs.response_success else 0,
                obs.latency_ms,
                obs.user_feedback,
                obs.outcome_score,
                obs.policy,
            ),
        )
        self.conn.commit()
        obs.id = cur.lastrowid
        return obs.id

    # --- reads --------------------------------------------------------------
    def get_observations(
        self,
        intent: Optional[str] = None,
        complexity: Optional[str] = None,
        selected_agent: Optional[str] = None,
        limit: Optional[int] = None,
    ) -> list:
        where, params = self._where(intent, complexity, selected_agent)
        sql = f"SELECT * FROM routing_observations {where} ORDER BY id DESC"
        if limit is not None:
            sql += " LIMIT ?"
            params = params + [limit]
        rows = self.conn.execute(sql, params).fetchall()
        return [self._row_to_obs(r) for r in rows]

    def agent_stats(
        self,
        intent: Optional[str] = None,
        complexity: Optional[str] = None,
    ) -> dict:
        """Return {agent: stats} aggregated over the matching observations."""
        where, params = self._where(intent, complexity, None)
        sql = f"""
            SELECT selected_agent,
                   COUNT(*)                AS attempts,
                   SUM(response_success)   AS successes,
                   AVG(outcome_score)      AS avg_score,
                   AVG(latency_ms)         AS avg_latency
            FROM routing_observations
            {where}
            GROUP BY selected_agent
        """
        out = {}
        for row in self.conn.execute(sql, params).fetchall():
            attempts = int(row["attempts"])
            successes = int(row["successes"] or 0)
            avg_score = row["avg_score"]
            avg_latency = row["avg_latency"]
            out[row["selected_agent"]] = {
                "attempts": attempts,
                "successes": successes,
                "success_rate": round(successes / attempts, 3) if attempts else 0.0,
                "average_score": round(avg_score, 3) if avg_score is not None else None,
                "average_latency_ms": (
                    round(avg_latency, 1) if avg_latency is not None else None
                ),
            }
        return out

    # Spec-named convenience wrappers -------------------------------------
    def get_agent_statistics(self) -> dict:
        return self.agent_stats()

    def get_statistics_by_intent(self) -> dict:
        return {intent: self.agent_stats(intent) for intent in self._distinct("intent")}

    def get_statistics_by_intent_and_complexity(self) -> dict:
        result = {}
        for intent in self._distinct("intent"):
            result[intent] = {
                complexity: self.agent_stats(intent, complexity)
                for complexity in self._distinct("complexity", intent)
            }
        return result

    # --- internals ----------------------------------------------------------
    @staticmethod
    def _where(intent, complexity, selected_agent):
        clauses, params = [], []
        if intent is not None:
            clauses.append("intent = ?")
            params.append(intent)
        if complexity is not None:
            clauses.append("complexity = ?")
            params.append(complexity)
        if selected_agent is not None:
            clauses.append("selected_agent = ?")
            params.append(selected_agent)
        where = ("WHERE " + " AND ".join(clauses)) if clauses else ""
        return where, params

    def _distinct(self, column: str, intent: Optional[str] = None) -> list:
        # column is an internal literal, never user input.
        if intent is None:
            sql = f"SELECT DISTINCT {column} FROM routing_observations"
            rows = self.conn.execute(sql).fetchall()
        else:
            sql = f"SELECT DISTINCT {column} FROM routing_observations WHERE intent = ?"
            rows = self.conn.execute(sql, [intent]).fetchall()
        return [r[0] for r in rows]

    @staticmethod
    def _row_to_obs(row) -> RoutingObservation:
        return RoutingObservation(
            id=row["id"],
            timestamp=row["timestamp"],
            task_id=row["task_id"],
            intent=row["intent"],
            complexity=row["complexity"],
            confidence=row["confidence"],
            selected_agent=row["selected_agent"],
            response_success=bool(row["response_success"]),
            latency_ms=row["latency_ms"],
            user_feedback=row["user_feedback"],
            outcome_score=row["outcome_score"],
            policy=row["policy"],
        )
