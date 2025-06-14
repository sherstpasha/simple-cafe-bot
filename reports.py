import pandas as pd
from openpyxl.utils import get_column_letter
from openpyxl import load_workbook
from db import get_connection
from datetime import datetime


def auto_adjust_columns(file_path):
    wb = load_workbook(file_path)
    for sheet in wb.worksheets:
        for column_cells in sheet.columns:
            max_length = max(len(str(cell.value or "")) for cell in column_cells)
            column_letter = get_column_letter(column_cells[0].column)
            sheet.column_dimensions[column_letter].width = max_length + 2
    wb.save(file_path)


def generate_reports(start_date=None, end_date=None):
    conn = get_connection()

    if isinstance(start_date, str):
        start_date = datetime.fromisoformat(start_date)
    if isinstance(end_date, str):
        end_date = datetime.fromisoformat(end_date)

    date_filter = ""
    params = []
    if start_date and end_date:
        date_filter = "WHERE date(date) BETWEEN ? AND ?"
        params = [start_date.isoformat(), end_date.isoformat()]

    orders_df = pd.read_sql_query(
        f"SELECT date, payment_type, item_name FROM orders {date_filter}",
        conn,
        params=params,
    )
    actions_df = pd.read_sql_query(
        "SELECT timestamp, action_type, payment_type, item_name, user_id, username FROM actions_log",
        conn,
    )
    conn.close()

    # Русские заголовки
    orders_df.columns = ["Дата", "Тип оплаты", "Название"]
    actions_df.columns = [
        "Дата/время",
        "Действие",
        "Тип оплаты",
        "Название",
        "user_id",
        "username",
    ]

    if start_date and end_date:
        if start_date == end_date:
            period_str = start_date.strftime("%Y-%m-%d")
        else:
            period_str = (
                f"{start_date.strftime('%Y-%m-%d')}__{end_date.strftime('%Y-%m-%d')}"
            )
    else:
        period_str = "all"

    report_path = f"report_{period_str}.xlsx"
    log_path = f"log_report_{period_str}.xlsx"

    with pd.ExcelWriter(report_path, engine="openpyxl") as writer:
        orders_df.to_excel(writer, sheet_name="Все заказы", index=False)
        orders_df[orders_df["Тип оплаты"] == "Наличный"].to_excel(
            writer, sheet_name="Наличные", index=False
        )
        orders_df[orders_df["Тип оплаты"] == "Безналичный"].to_excel(
            writer, sheet_name="Безналичные", index=False
        )
        grouped = orders_df.groupby("Название").size().reset_index(name="Количество")
        grouped.to_excel(writer, sheet_name="Группировка", index=False)

    with pd.ExcelWriter(log_path, engine="openpyxl") as writer:
        actions_df.to_excel(writer, sheet_name="Журнал действий", index=False)

    # Автоподбор ширины
    auto_adjust_columns(report_path)
    auto_adjust_columns(log_path)

    return report_path, log_path
