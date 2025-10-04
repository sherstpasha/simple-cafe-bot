import sqlite3
from datetime import datetime, date
import json as _json

DB_PATH = "orders.db"

CREATE_ORDERS = """
CREATE TABLE IF NOT EXISTS orders (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    date TEXT,
    user_id INTEGER,
    username TEXT,
    raw_text TEXT,
    is_staff INTEGER DEFAULT 0
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
    username TEXT,
    is_staff INTEGER DEFAULT 0
);
"""

CREATE_ORDER_ITEMS = """
CREATE TABLE IF NOT EXISTS order_items (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    order_id INTEGER,
    item_name TEXT,
    payment_type TEXT,
    price INTEGER,
    quantity INTEGER DEFAULT 1,
    addons_total INTEGER DEFAULT 0,
    addons_json  TEXT DEFAULT '[]',
    row_total INTEGER NOT NULL,
    is_staff INTEGER DEFAULT 0,
    FOREIGN KEY(order_id) REFERENCES orders(id)
);
"""


def _ensure_column(cursor, table: str, column_def: str):
    try:
        cursor.execute(f"ALTER TABLE {table} ADD COLUMN {column_def}")
    except sqlite3.OperationalError as exc:
        if "duplicate column name" in str(exc).lower():
            return
        raise


def get_connection():
    conn = sqlite3.connect(DB_PATH, timeout=10)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(CREATE_ORDERS)
    cursor.execute(CREATE_LOG)
    cursor.execute(CREATE_ORDER_ITEMS)

    _ensure_column(cursor, "orders", "is_staff INTEGER DEFAULT 0")
    _ensure_column(cursor, "order_items", "is_staff INTEGER DEFAULT 0")
    _ensure_column(cursor, "actions_log", "is_staff INTEGER DEFAULT 0")

    conn.commit()
    conn.close()


def log_action(action_type, payment_type, item_name, user_id, username, *, is_staff=False):
    conn = get_connection()
    try:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO actions_log
              (timestamp, action_type, payment_type, item_name, user_id, username, is_staff)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (
                datetime.now().isoformat(),
                action_type,
                payment_type,
                item_name,
                user_id,
                username,
                1 if is_staff else 0,
            ),
        )
        conn.commit()
    finally:
        conn.close()


# def clear_today(user_id, username):
#     conn = get_connection()
#     cursor = conn.cursor()
#     today = date.today().isoformat()
#     cursor.execute(
#         "SELECT id, payment_type, item_name FROM orders WHERE date(date)=date(?) AND user_id=?",
#         (today, user_id),
#     )
#     rows = cursor.fetchall()
#     for r in rows:
#         cursor.execute("DELETE FROM orders WHERE id=?", (r["id"],))
#         log_action(
#             "очистка_сегодня", r["payment_type"], r["item_name"], user_id, username
#         )
#     conn.commit()
#     conn.close()


# def get_user_orders(user_id):
#     conn = get_connection()
#     cursor = conn.cursor()
#     cursor.execute(
#         "SELECT id, date, payment_type, item_name FROM orders WHERE user_id = ? ORDER BY date DESC",
#         (user_id,),
#     )
#     rows = cursor.fetchall()
#     conn.close()
#     return [
#         {"id": r[0], "date": r[1], "payment_type": r[2], "item_name": r[3]}
#         for r in rows
#     ]


# def delete_order(order_id, user_id):
#     conn = get_connection()
#     cursor = conn.cursor()
#     cursor.execute(
#         "SELECT payment_type, item_name FROM orders WHERE id = ? AND user_id = ?",
#         (order_id, user_id),
#     )
#     row = cursor.fetchone()
#     if not row:
#         conn.close()
#         return None
#     cursor.execute(
#         "DELETE FROM orders WHERE id = ? AND user_id = ?", (order_id, user_id)
#     )
#     conn.commit()
#     conn.close()
#     return {"payment_type": row[0], "item_name": row[1]}


# def delete_orders_today(user_id):
#     from datetime import date

#     conn = get_connection()
#     cursor = conn.cursor()
#     today = date.today().isoformat()
#     cursor.execute(
#         "SELECT payment_type, item_name FROM orders WHERE user_id = ? AND date(date) = ?",
#         (user_id, today),
#     )
#     rows = cursor.fetchall()
#     cursor.execute(
#         "DELETE FROM orders WHERE user_id = ? AND date(date) = ?", (user_id, today)
#     )
#     conn.commit()
#     conn.close()
#     return len(rows), [{"payment_type": r[0], "item_name": r[1]} for r in rows]


def add_order_items(
    items: list[dict],
    user_id: int,
    username: str,
    raw_text: str = "",
    *,
    is_staff: bool = False,
):
    """
    Записывает в БД сам заказ и сразу все позиции + логи в одном соединении.
    """
    conn = get_connection()
    cursor = conn.cursor()

    # 1) создаём новую запись в orders
    cursor.execute(
        "INSERT INTO orders (date, user_id, username, raw_text, is_staff) VALUES (?, ?, ?, ?, ?)",
        (datetime.now().isoformat(), user_id, username, raw_text, 1 if is_staff else 0),
    )

    order_id = cursor.lastrowid

    now = datetime.now().isoformat()
    # 2) вставляем все позиции + одно лог-сообщение на каждую
    for item in items:
        qty = item.get("quantity", 1)
        base_price = int(item["price"])
        addons = item.get("addons", [])
        addons_total = sum(int(a.get("price", 0)) for a in addons)
        row_total = (base_price + addons_total) * qty

        addons_json = _json.dumps(addons, ensure_ascii=False)

        cursor.execute(
            "INSERT INTO order_items (order_id, item_name, payment_type, price, quantity, addons_total, addons_json, row_total, is_staff) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                order_id,
                item["item_name"],
                item["payment_type"],
                base_price,
                qty,
                addons_total,
                addons_json,
                row_total,
                1 if is_staff else 0,
            ),
        )
        cursor.execute(
            "INSERT INTO actions_log (timestamp, action_type, payment_type, item_name, user_id, username, is_staff) "
            "VALUES (?, ?, ?, ?, ?, ?, ?)",
            (
                now,
                "добавление",
                item["payment_type"],
                item["item_name"],
                user_id,
                username,
                1 if is_staff else 0,
            ),
        )

    # 3) единственный коммит и закрытие
    conn.commit()
    conn.close()


def get_user_orders_with_items(user_id: int) -> list[dict]:
    """
    Возвращает список заказов пользователя с позициями и итоговой суммой каждого заказа.
    Формат:
    [
      {
        "id": 123,
        "date": "2025-06-27T12:34:56",
        "payment_type": "наличный",
        "items": [
          {"item_name": "Американо", "price": 90, "quantity": 2, "row_total": 180},
          {"item_name": "Латте",     "price": 150, "quantity": 1, "row_total": 150},
        ],
        "total": 330
      },
      ...
    ]
    """
    conn = get_connection()
    cursor = conn.cursor()
    # Сначала пробегаемся по уникальным заказам
    cursor.execute(
        """
        SELECT DISTINCT o.id, o.date, o.is_staff, oi.payment_type
        FROM orders o
        JOIN order_items oi ON oi.order_id = o.id
        WHERE o.user_id = ?
        ORDER BY o.date DESC
        """,
        (user_id,),
    )
    orders = []
    for oid, date_, is_staff, payment in cursor.fetchall():
        # Для каждого заказа собираем позиции
        cursor2 = conn.cursor()
        cursor2.execute(
            """
            SELECT item_name, price, quantity, addons_total, addons_json, row_total, is_staff
            FROM order_items
            WHERE order_id = ?
            """,
            (oid,),
        )
        rows = cursor2.fetchall()
        items = []
        for r in rows:
            addons = []
            try:
                addons = _json.loads(r["addons_json"]) if r["addons_json"] else []
            except Exception:
                addons = []
            items.append(
                {
                    "item_name": r["item_name"],
                    "price": r["price"],  # базовая цена
                    "quantity": r["quantity"],
                    "addons_total": r["addons_total"],  # сумма добавок
                    "addons": addons,  # список добавок [{name, price}, ...]
                    "row_total": r["row_total"],  # ИТОГО по позиции (с добавками * qty)
                    "is_staff": bool(r["is_staff"]),
                }
            )
        # Считаем суммарную стоимость заказа
        total = sum(r["row_total"] for r in items)
        orders.append(
            {
                "id": oid,
                "date": date_,
                "payment_type": payment,
                "items": items,
                "total": total,
                "is_staff": bool(is_staff),
            }
        )
    conn.close()
    return orders


def delete_entire_order(order_id: int, user_id: int, username: str) -> list[dict]:
    """
    Удаляет весь заказ (строку в orders + все связанные order_items).
    Возвращает список удалённых позиций для лога и показа.
    """
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute(
        """
        SELECT item_name, price, quantity, payment_type,
               row_total, addons_total, addons_json, is_staff
        FROM order_items
        WHERE order_id=?
        """,
        (order_id,),
    )
    items = [dict(r) for r in cursor.fetchall()]
    cursor.execute("DELETE FROM order_items WHERE order_id=?", (order_id,))
    cursor.execute("DELETE FROM orders WHERE id=? AND user_id=?", (order_id, user_id))
    conn.commit()
    conn.close()

    # Лог каждого удаления
    for it in items:
        log_action(
            action_type="удаление",
            payment_type=it["payment_type"],
            item_name=f"{it['item_name']} x{it['quantity']}",
            user_id=user_id,
            username=username,
            is_staff=bool(it.get("is_staff")),
        )
    return items
