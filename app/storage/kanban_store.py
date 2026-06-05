"""CRUD for kanban boards and cards."""
from __future__ import annotations

import time
import uuid

from app.db import LOCK, get_conn


# ── Boards ────────────────────────────────────────────────────────────────────

def create_board(title: str, description: str | None = None) -> str:
    bid = uuid.uuid4().hex
    now = time.time()
    conn = get_conn()
    with LOCK:
        conn.execute(
            "INSERT INTO kanban_boards (id, title, description, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?)",
            (bid, title, description, now, now),
        )
    return bid


def list_boards() -> list[dict]:
    rows = get_conn().execute(
        "SELECT b.*, "
        "  (SELECT COUNT(*) FROM kanban_cards WHERE board_id=b.id AND \"column\"='todo')  AS todo_count, "
        "  (SELECT COUNT(*) FROM kanban_cards WHERE board_id=b.id AND \"column\"='doing') AS doing_count, "
        "  (SELECT COUNT(*) FROM kanban_cards WHERE board_id=b.id AND \"column\"='done')  AS done_count "
        "FROM kanban_boards b ORDER BY b.created_at DESC"
    ).fetchall()
    return [dict(r) for r in rows]


def get_board(board_id: str) -> dict | None:
    row = get_conn().execute(
        "SELECT * FROM kanban_boards WHERE id = ?", (board_id,)
    ).fetchone()
    return dict(row) if row else None


def update_board(board_id: str, title: str, description: str | None) -> None:
    with LOCK:
        get_conn().execute(
            "UPDATE kanban_boards SET title=?, description=?, updated_at=? WHERE id=?",
            (title, description, time.time(), board_id),
        )


def delete_board(board_id: str) -> None:
    with LOCK:
        get_conn().execute("DELETE FROM kanban_boards WHERE id=?", (board_id,))


# ── Cards ─────────────────────────────────────────────────────────────────────

def create_card(board_id: str, title: str, body: str | None = None,
                column: str = "todo") -> str:
    cid = uuid.uuid4().hex
    now = time.time()
    conn = get_conn()
    with LOCK:
        row = conn.execute(
            "SELECT COALESCE(MAX(position), -1) + 1 FROM kanban_cards "
            "WHERE board_id=? AND \"column\"=?",
            (board_id, column),
        ).fetchone()
        position = row[0] if row else 0
        conn.execute(
            "INSERT INTO kanban_cards "
            "(id, board_id, title, body, \"column\", position, created_at, updated_at) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (cid, board_id, title, body, column, position, now, now),
        )
    return cid


def get_card(card_id: str) -> dict | None:
    row = get_conn().execute(
        "SELECT * FROM kanban_cards WHERE id=?", (card_id,)
    ).fetchone()
    return dict(row) if row else None


def list_cards_for_board(board_id: str) -> dict[str, list[dict]]:
    rows = get_conn().execute(
        "SELECT * FROM kanban_cards WHERE board_id=? ORDER BY position, created_at",
        (board_id,),
    ).fetchall()
    result: dict[str, list[dict]] = {"todo": [], "doing": [], "done": []}
    for r in rows:
        d = dict(r)
        col = d.get("column", "todo")
        if col in result:
            result[col].append(d)
    return result


def update_card(card_id: str, title: str, body: str | None) -> None:
    with LOCK:
        get_conn().execute(
            "UPDATE kanban_cards SET title=?, body=?, updated_at=? WHERE id=?",
            (title, body, time.time(), card_id),
        )


def delete_card(card_id: str) -> None:
    with LOCK:
        get_conn().execute("DELETE FROM kanban_cards WHERE id=?", (card_id,))


VALID_COLUMNS = {"todo", "doing", "done"}


def reorder_board(board_id: str, columns: dict[str, list[str]]) -> None:
    """Bulk-update positions for all cards from the given column→[card_id] map."""
    now = time.time()
    conn = get_conn()
    with LOCK:
        for col, card_ids in columns.items():
            if col not in VALID_COLUMNS:
                continue  # silently skip invalid column names
            for pos, card_id in enumerate(card_ids):
                conn.execute(
                    "UPDATE kanban_cards SET \"column\"=?, position=?, updated_at=? "
                    "WHERE id=? AND board_id=?",
                    (col, pos, now, card_id, board_id),
                )
