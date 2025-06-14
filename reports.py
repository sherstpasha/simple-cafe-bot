import pandas as pd
from db import get_connection


def generate_reports():
    conn = get_connection()
    orders_df = pd.read_sql_query(
        "SELECT date, payment_type, item_name FROM orders", conn
    )
    actions_df = pd.read_sql_query(
        "SELECT timestamp, action_type, payment_type, item_name, user_id, username FROM actions_log",
        conn,
    )
    conn.close()

    # Основной отчет
    with pd.ExcelWriter("report.xlsx", engine="openpyxl") as writer:
        orders_df.to_excel(writer, sheet_name="Все заказы", index=False)
        orders_df[orders_df.payment_type == "Наличный"].to_excel(
            writer, sheet_name="Наличные заказы", index=False
        )
        orders_df[orders_df.payment_type == "Безналичный"].to_excel(
            writer, sheet_name="Безналичные заказы", index=False
        )
        grouped = orders_df.groupby("item_name").size().reset_index(name="количество")
        grouped.to_excel(writer, sheet_name="Группировка по названию", index=False)

    # Журнал действий
    with pd.ExcelWriter("log_report.xlsx", engine="openpyxl") as writer:
        actions_df.to_excel(writer, sheet_name="Журнал действий", index=False)
