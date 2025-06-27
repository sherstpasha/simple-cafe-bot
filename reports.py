import pandas as pd
from openpyxl.utils import get_column_letter
from openpyxl import load_workbook
from db import get_connection
from datetime import datetime, date


def auto_adjust_columns(file_path):
    wb = load_workbook(file_path)
    for sheet in wb.worksheets:
        for column_cells in sheet.columns:
            max_length = max(len(str(cell.value or "")) for cell in column_cells)
            letter = get_column_letter(column_cells[0].column)
            sheet.column_dimensions[letter].width = max_length + 2
    wb.save(file_path)


def generate_reports(start_date=None, end_date=None):
    conn = get_connection()

    # Приведение строк к datetime
    if isinstance(start_date, str):
        start_date = datetime.fromisoformat(start_date)
    if isinstance(end_date, str):
        end_date = datetime.fromisoformat(end_date)

    # Фильтрация по дате
    date_filter = ""
    params = []
    if start_date and end_date:
        date_filter = "WHERE date(o.date) BETWEEN ? AND ?"

        def to_iso(d):
            # если d — date или datetime, просто isoformat
            return d.isoformat()

        params = [to_iso(start_date), to_iso(end_date)]

    # Считываем все позиции из order_items
    orders_df = pd.read_sql_query(
        f"""
        SELECT 
          o.date         AS date,
          i.payment_type AS payment_type,
          i.item_name    AS item_name,
          i.row_total    AS row_total
        FROM orders o
        JOIN order_items i ON i.order_id = o.id
        {date_filter}
        ORDER BY o.date
        """,
        conn,
        params=params,
    )
    actions_df = pd.read_sql_query(
        "SELECT timestamp, action_type, payment_type, item_name, user_id, username FROM actions_log",
        conn,
    )
    conn.close()

    # Русские заголовки
    orders_df.columns = ["Дата", "Тип оплаты", "Название", "Сумма позиции"]
    actions_df.columns = [
        "Дата/время",
        "Действие",
        "Тип оплаты",
        "Название",
        "user_id",
        "username",
    ]

    # Подготовка имени файлов
    if start_date and end_date:
        if start_date == end_date:
            period_str = start_date.isoformat()
        else:
            period_str = f"{start_date.isoformat()}__{end_date.isoformat()}"
    else:
        period_str = "all"

    report_path = f"report_{period_str}.xlsx"
    log_path = f"log_report_{period_str}.xlsx"

    # Пишем отчёт
    with pd.ExcelWriter(report_path, engine="openpyxl") as writer:
        orders_df.to_excel(writer, sheet_name="Все позиции", index=False)

        # Листы по каждому типу оплаты
        for pt in sorted(orders_df["Тип оплаты"].dropna().unique(), key=str.lower):
            mask = orders_df["Тип оплаты"].str.lower() == str(pt).lower()
            df_pt = orders_df[mask]
            sheet = str(pt).capitalize()
            df_pt.to_excel(writer, sheet_name=sheet, index=False)

        # Группировка по (Тип оплаты, Название)
        grouped = (
            orders_df.groupby(["Тип оплаты", "Название"], dropna=False)
            .agg(
                Количество=("Сумма позиции", "size"),
                Общая_сумма=("Сумма позиции", "sum"),
            )
            .reset_index()
        )
        grouped.to_excel(writer, sheet_name="Группировка", index=False)

    # Журнал действий
    with pd.ExcelWriter(log_path, engine="openpyxl") as writer:
        actions_df.to_excel(writer, sheet_name="Журнал действий", index=False)

    # Автоподбор ширины
    auto_adjust_columns(report_path)
    auto_adjust_columns(log_path)

    return report_path, log_path
