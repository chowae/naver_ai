from datetime import datetime
import secrets
import sqlite3

from fastapi import FastAPI, HTTPException, Header
from pydantic import BaseModel


app = FastAPI(title="Todo REST API")

DB_NAME = "todos.db"

# 실습용 관리자 비밀번호
ADMIN_PASSWORD = "admin123"

# 발급된 관리자 토큰 저장
admin_tokens = set()

# 차단 태그
blocked_tags = ["spam", "ad", "private", "temp"]


# =========================================================
# Pydantic Models
# =========================================================

class TodoCreate(BaseModel):
    title: str
    description: str = ""
    is_completed: bool = False
    tags: str = ""


class AdminLogin(BaseModel):
    password: str


# =========================================================
# Database
# =========================================================

def get_db():
    conn = sqlite3.connect(DB_NAME)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db()

    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS todos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            description TEXT,
            is_completed INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            tags TEXT DEFAULT ''
        )
        """
    )

    conn.commit()
    conn.close()


init_db()


def row_to_dict(row):
    return {
        "id": row["id"],
        "title": row["title"],
        "description": row["description"],
        "is_completed": bool(row["is_completed"]),
        "created_at": row["created_at"],
        "tags": row["tags"],
    }


# =========================================================
# 1. 기본 CRUD
# =========================================================

@app.get("/todos")
def get_todos():
    conn = get_db()

    rows = conn.execute(
        "SELECT * FROM todos ORDER BY id DESC"
    ).fetchall()

    conn.close()

    return [row_to_dict(row) for row in rows]


@app.post("/todos")
def create_todo(todo: TodoCreate):
    conn = get_db()

    created_at = datetime.now().isoformat()

    cursor = conn.execute(
        """
        INSERT INTO todos
        (title, description, is_completed, created_at, tags)
        VALUES (?, ?, ?, ?, ?)
        """,
        (
            todo.title,
            todo.description,
            int(todo.is_completed),
            created_at,
            todo.tags,
        ),
    )

    conn.commit()

    row = conn.execute(
        "SELECT * FROM todos WHERE id = ?",
        (cursor.lastrowid,),
    ).fetchone()

    conn.close()

    return row_to_dict(row)


# =========================================================
# 2. 키워드 검색
# =========================================================

@app.get("/todos/search")
def search_todos(q: str):
    conn = get_db()

    keyword = f"%{q}%"

    rows = conn.execute(
        """
        SELECT *
        FROM todos
        WHERE title LIKE ?
           OR description LIKE ?
        ORDER BY id DESC
        """,
        (keyword, keyword),
    ).fetchall()

    conn.close()

    return [row_to_dict(row) for row in rows]


# =========================================================
# 3. 관리자 인증
# =========================================================

@app.post("/admin/login")
def admin_login(login: AdminLogin):

    if login.password != ADMIN_PASSWORD:
        raise HTTPException(
            status_code=401,
            detail="Invalid admin password",
        )

    token = secrets.token_urlsafe(32)
    admin_tokens.add(token)

    return {
        "access_token": token,
        "token_type": "bearer",
    }


def verify_admin_token(authorization: str | None):
    if not authorization:
        raise HTTPException(
            status_code=401,
            detail="Authorization header required",
        )

    parts = authorization.split()

    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(
            status_code=401,
            detail="Invalid authorization format",
        )

    token = parts[1]

    if token not in admin_tokens:
        raise HTTPException(
            status_code=401,
            detail="Invalid admin token",
        )


@app.delete("/admin/todos/{todo_id}")
def delete_todo(
    todo_id: int,
    authorization: str | None = Header(default=None),
):
    verify_admin_token(authorization)

    conn = get_db()

    todo = conn.execute(
        "SELECT * FROM todos WHERE id = ?",
        (todo_id,),
    ).fetchone()

    if todo is None:
        conn.close()
        raise HTTPException(
            status_code=404,
            detail="Todo not found",
        )

    conn.execute(
        "DELETE FROM todos WHERE id = ?",
        (todo_id,),
    )

    conn.commit()
    conn.close()

    return {
        "message": "Todo deleted successfully",
        "id": todo_id,
    }


# =========================================================
# 4. 차단 태그 필터링
# =========================================================

@app.get("/todos/filtered")
def get_filtered_todos():
    conn = get_db()

    rows = conn.execute(
        "SELECT * FROM todos ORDER BY id DESC"
    ).fetchall()

    conn.close()

    clean_todos = []

    for row in rows:
        todo = row_to_dict(row)

        tags = {
            tag.strip().lower()
            for tag in todo["tags"].split(",")
            if tag.strip()
        }

        # blocked_tags와 하나라도 겹치면 제외
        if not tags.intersection(blocked_tags):
            clean_todos.append(todo)

    return clean_todos


# =========================================================
# Health Check
# =========================================================

@app.get("/")
def root():
    return {
        "message": "Todo API is running"
    }