import sqlite3
from datetime import datetime, date

DB_PATH = "orders.db"

CREATE_ORDERS = """
CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY,
    date TEXT,
    payment_type TEXT,
    item_name TEXT,
    username TEXT,
    user_id INTEGER
);
"""
CREATE_LOG = """
CREATE TABLE IF NOT EXISTS actions_log (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp TEXT,
    action_type TEXT,
    payment_type TEXT,
    item_name TEXT,
    user_id INTEGER,
    username TEXT
);
"""


def get_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(CREATE_ORDERS)
    cursor.execute(CREATE_LOG)
    conn.commit()
    conn.close()


def log_action(action_type, payment_type, item_name, user_id, username):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO actions_log (timestamp, action_type, payment_type, item_name, user_id, username) VALUES (?,?,?,?,?,?)",
        (
            datetime.now().isoformat(),
            action_type,
            payment_type,
            item_name,
            user_id,
            username,
        ),
    )
    conn.commit()
    conn.close()


def add_order(payment_type, item_name, user_id, username):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "INSERT INTO orders (date, payment_type, item_name, username, user_id) VALUES (?,?,?,?,?)",
        (datetime.now().isoformat(), payment_type, item_name, username, user_id),
    )
    conn.commit()
    conn.close()
    log_action("добавление", payment_type, item_name, user_id, username)


def delete_order(order_id, user_id, username):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT payment_type, item_name FROM orders WHERE id=? AND user_id=?",
        (order_id, user_id),
    )
    row = cursor.fetchone()
    if row:
        payment, item = row["payment_type"], row["item_name"]
        cursor.execute(
            "DELETE FROM orders WHERE id=? AND user_id=?", (order_id, user_id)
        )
        conn.commit()
        log_action("удаление", payment, item, user_id, username)
    conn.close()


def clear_today(user_id, username):
    conn = get_connection()
    cursor = conn.cursor()
    today = date.today().isoformat()
    cursor.execute(
        "SELECT id, payment_type, item_name FROM orders WHERE date(date)=date(?) AND user_id=?",
        (today, user_id),
    )
    rows = cursor.fetchall()
    for r in rows:
        cursor.execute("DELETE FROM orders WHERE id=?", (r["id"],))
        log_action(
            "очистка_сегодня", r["payment_type"], r["item_name"], user_id, username
        )
    conn.commit()
    conn.close()


def get_user_orders(user_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT * FROM orders WHERE user_id=? ORDER BY date DESC", (user_id,)
    )
    rows = cursor.fetchall()
    conn.close()
    return [dict(r) for r in rows]


def get_user_orders(user_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT id, date, payment_type, item_name FROM orders WHERE user_id = ? ORDER BY date DESC",
        (user_id,),
    )
    rows = cursor.fetchall()
    conn.close()
    return [
        {"id": r[0], "date": r[1], "payment_type": r[2], "item_name": r[3]}
        for r in rows
    ]


def delete_order(order_id, user_id):
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        "SELECT payment_type, item_name FROM orders WHERE id = ? AND user_id = ?",
        (order_id, user_id),
    )
    row = cursor.fetchone()
    if not row:
        conn.close()
        return None
    cursor.execute(
        "DELETE FROM orders WHERE id = ? AND user_id = ?", (order_id, user_id)
    )
    conn.commit()
    conn.close()
    return {"payment_type": row[0], "item_name": row[1]}


def delete_orders_today(user_id):
    from datetime import date

    conn = get_connection()
    cursor = conn.cursor()
    today = date.today().isoformat()
    cursor.execute(
        "SELECT payment_type, item_name FROM orders WHERE user_id = ? AND date(date) = ?",
        (user_id, today),
    )
    rows = cursor.fetchall()
    cursor.execute(
        "DELETE FROM orders WHERE user_id = ? AND date(date) = ?", (user_id, today)
    )
    conn.commit()
    conn.close()
    return len(rows), [{"payment_type": r[0], "item_name": r[1]} for r in rows]
