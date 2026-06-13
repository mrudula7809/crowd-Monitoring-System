"""
step4_db.py — Database Layer
Primary: MySQL  |  Fallback: SQLite (auto-selected if MySQL unavailable)
Stores every tick's zone snapshot for history, ML training, trend analysis.
"""

import sqlite3
import os
from datetime import datetime
from typing import List, Dict, Optional, Tuple

# Try importing MySQL connector; gracefully fall back to SQLite
try:
    import mysql.connector
    MYSQL_AVAILABLE = True
except ImportError:
    MYSQL_AVAILABLE = False


# ─────────────────────────────────────────────
# DB Config (MySQL)  — override via env vars
# ─────────────────────────────────────────────
MYSQL_CONFIG = {
    "host":     os.environ.get("DB_HOST",   "localhost"),
    "port":     int(os.environ.get("DB_PORT", 3306)),
    "user":     os.environ.get("DB_USER",   "root"),
    "password": os.environ.get("DB_PASS",   "rutu@9087"),
    "database": os.environ.get("DB_NAME",   "crowd_intelligence"),
}

SQLITE_PATH = os.environ.get("SQLITE_PATH", "crowd_intelligence.db")


# ─────────────────────────────────────────────
# Schema DDL
# ─────────────────────────────────────────────
CREATE_TABLE_SQL = """
CREATE TABLE IF NOT EXISTS zone_snapshots (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    tick_number  INTEGER      NOT NULL,
    timestamp    DATETIME     NOT NULL,
    zone_id      VARCHAR(20)  NOT NULL,
    zone_name    VARCHAR(100),
    people_count INTEGER      NOT NULL,
    density      FLOAT        NOT NULL,
    entry_rate   FLOAT        NOT NULL,
    exit_rate    FLOAT        NOT NULL,
    risk_level   VARCHAR(20)  NOT NULL,
    occupancy_pct FLOAT
);
"""

CREATE_INDEX_SQL = """
CREATE INDEX idx_zone_tick ON zone_snapshots (zone_id, tick_number);
"""

CREATE_CROWD_LOGS_SQL = """
CREATE TABLE IF NOT EXISTS crowd_logs (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    zone_id      VARCHAR(20)  NOT NULL,
    zone_name    VARCHAR(100),
    entry_rate   FLOAT,
    exit_rate    FLOAT,
    people       INTEGER,
    density      FLOAT,
    capacity     INTEGER,
    timestamp    DATETIME     NOT NULL
);
"""


# ─────────────────────────────────────────────
# DatabaseManager
# ─────────────────────────────────────────────
class DatabaseManager:
    """
    Unified DB interface.  Chooses MySQL if available and connectable,
    otherwise falls back to SQLite transparently.
    """

    def __init__(self, use_mysql: bool = True, verbose: bool = True):
        self.use_mysql = use_mysql and MYSQL_AVAILABLE
        self.verbose   = verbose
        self._conn     = None
        self._backend  = None
        self._connect()
        self._create_schema()

    # ── connection ────────────────────────
    def _connect(self):
        if self.use_mysql:
            try:
                self._conn = mysql.connector.connect(**MYSQL_CONFIG)
                self._backend = "MySQL"
                if self.verbose:
                    print(f"  [DB] Database: MySQL connected ({MYSQL_CONFIG['host']}:{MYSQL_CONFIG['port']})")
                return
            except Exception as e:
                if self.verbose:
                    print(f"  [WARN] MySQL unavailable ({e}). Falling back to SQLite.")

        # SQLite fallback
        self._conn    = sqlite3.connect(SQLITE_PATH, check_same_thread=False)
        self._backend = "SQLite"
        if self.verbose:
            print(f"  [DB] Database: SQLite  ({SQLITE_PATH})")

    def _cursor(self):
        # Auto-reconnect on closed connection
        try:
            if self._backend == "MySQL":
                self._conn.ping(reconnect=True)
            return self._conn.cursor()
        except Exception:
            self._connect()
            return self._conn.cursor()

    def _placeholder(self) -> str:
        return "%s" if self._backend == "MySQL" else "?"

    # ── schema ────────────────────────────
    def _create_schema(self):
        cur = self._cursor()
        # MySQL needs AUTO_INCREMENT syntax fix
        ddl = CREATE_TABLE_SQL
        ddl_logs = CREATE_CROWD_LOGS_SQL
        if self._backend == "MySQL":
            ddl = ddl.replace("INTEGER PRIMARY KEY AUTOINCREMENT",
                               "INT AUTO_INCREMENT PRIMARY KEY")
            ddl_logs = ddl_logs.replace("INTEGER PRIMARY KEY AUTOINCREMENT",
                               "INT AUTO_INCREMENT PRIMARY KEY")
        cur.execute(ddl)
        try:
            cur.execute(CREATE_INDEX_SQL)
        except Exception as e:
            # Ignore duplicate key error if the index already exists, or syntax error if IF NOT EXISTS fails
            pass
        cur.execute(ddl_logs)
        self._conn.commit()
        cur.close()

    # ── write ─────────────────────────────
    def insert_snapshot(
        self,
        tick_number:   int,
        zone_id:       str,
        zone_name:     str,
        people_count:  int,
        density:       float,
        entry_rate:    float,
        exit_rate:     float,
        risk_level:    str,
        occupancy_pct: float,
    ):
        ph = self._placeholder()
        sql = f"""
            INSERT INTO zone_snapshots
              (tick_number, timestamp, zone_id, zone_name, people_count,
               density, entry_rate, exit_rate, risk_level, occupancy_pct)
            VALUES ({ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph})
        """
        cur = self._cursor()
        cur.execute(sql, (
            tick_number, datetime.now().isoformat(), zone_id, zone_name,
            people_count, density, entry_rate, exit_rate, risk_level, occupancy_pct,
        ))
        self._conn.commit()
        cur.close()

    def insert_crowd_log(
        self,
        zone_id: str,
        zone_name: str,
        entry_rate: float,
        exit_rate: float,
        people: int,
        density: float,
        capacity: int
    ):
        ph = self._placeholder()
        sql = f"""
            INSERT INTO crowd_logs
              (zone_id, zone_name, entry_rate, exit_rate, people, density, capacity, timestamp)
            VALUES ({ph},{ph},{ph},{ph},{ph},{ph},{ph},{ph})
        """
        cur = self._cursor()
        cur.execute(sql, (
            zone_id, zone_name, entry_rate, exit_rate, people, density, capacity, datetime.now().isoformat()
        ))
        self._conn.commit()
        cur.close()

    def bulk_insert_tick(self, tick_number: int, zones: Dict):
        """zones: {zone_id: Zone object}"""
        for zone in zones.values():
            self.insert_snapshot(
                tick_number   = tick_number,
                zone_id       = zone.zone_id,
                zone_name     = zone.name,
                people_count  = zone.people_count,
                density       = zone.density,
                entry_rate    = zone.entry_rate,
                exit_rate     = zone.exit_rate,
                risk_level    = zone.risk_level,
                occupancy_pct = zone.occupancy_pct,
            )

    # ── read ──────────────────────────────
    def get_zone_history(
        self, zone_id: str, last_n: Optional[int] = None
    ) -> List[Dict]:
        ph  = self._placeholder()
        sql = f"""
            SELECT tick_number, timestamp, people_count, density,
                   entry_rate, exit_rate, risk_level, occupancy_pct
            FROM zone_snapshots
            WHERE zone_id = {ph}
            ORDER BY tick_number DESC
        """
        if last_n:
            sql += f" LIMIT {last_n}"

        cur = self._cursor()
        cur.execute(sql, (zone_id,))
        cols = ["tick", "timestamp", "people", "density", "entry", "exit", "risk", "occupancy_pct"]
        rows = [dict(zip(cols, row)) for row in cur.fetchall()]
        cur.close()
        return list(reversed(rows))

    def get_risk_timeline(self, zone_id: str) -> List[Tuple[int, str]]:
        ph  = self._placeholder()
        sql = f"""
            SELECT tick_number, risk_level
            FROM zone_snapshots
            WHERE zone_id = {ph}
            ORDER BY tick_number ASC
        """
        cur = self._cursor()
        cur.execute(sql, (zone_id,))
        result = cur.fetchall()
        cur.close()
        return result

    def get_all_zones_at_tick(self, tick_number: int) -> List[Dict]:
        ph  = self._placeholder()
        sql = f"""
            SELECT zone_id, zone_name, people_count, density, risk_level
            FROM zone_snapshots
            WHERE tick_number = {ph}
        """
        cur = self._cursor()
        cur.execute(sql, (tick_number,))
        cols = ["zone_id", "zone_name", "people", "density", "risk"]
        result = [dict(zip(cols, row)) for row in cur.fetchall()]
        cur.close()
        return result

    def get_training_data(self, zone_id: str) -> List[Tuple[int, float]]:
        """Returns (tick, people_count) pairs for ML training."""
        ph  = self._placeholder()
        sql = f"""
            SELECT tick_number, people_count
            FROM zone_snapshots
            WHERE zone_id = {ph}
            ORDER BY tick_number ASC
        """
        cur = self._cursor()
        cur.execute(sql, (zone_id,))
        result = cur.fetchall()
        cur.close()
        return result

    def get_summary_stats(self) -> Dict:
        cur = self._cursor()
        cur.execute("SELECT COUNT(*) FROM zone_snapshots")
        total_rows = cur.fetchone()[0]
        cur.execute("SELECT MAX(tick_number) FROM zone_snapshots")
        max_tick = cur.fetchone()[0] or 0
        cur.execute("SELECT COUNT(DISTINCT zone_id) FROM zone_snapshots")
        zone_count = cur.fetchone()[0]
        cur.close()
        return {"total_rows": total_rows, "max_tick": max_tick, "zone_count": zone_count}

    # ── cleanup ───────────────────────────
    def close(self):
        if self._conn:
            self._conn.close()

    def clear_all(self):
        """Wipe all data (useful for fresh simulation runs)."""
        cur = self._cursor()
        cur.execute("DELETE FROM zone_snapshots")
        self._conn.commit()
        cur.close()

    def __repr__(self):
        return f"DatabaseManager(backend={self._backend})"
