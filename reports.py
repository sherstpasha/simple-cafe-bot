import pandas as pd
from openpyxl.utils import get_column_letter
from openpyxl import load_workbook
from db import get_connection
from datetime import datetime
import json


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

    # 0) Приведение строк к datetime
    if isinstance(start_date, str):
        start_date = datetime.fromisoformat(start_date)
    if isinstance(end_date, str):
        end_date = datetime.fromisoformat(end_date)

    # 1) Фильтр периода
    date_filter = ""
    params = []
    if start_date and end_date:
        date_filter = "WHERE date(o.date) BETWEEN ? AND ?"
        params = [start_date.isoformat(), end_date.isoformat()]

    # 2) Читаем данные, включая addons_json и raw_text
    orders_df = pd.read_sql_query(
        f"""
        SELECT 
          o.date          AS date,
          i.payment_type  AS payment_type,
          i.item_name     AS item_name,
          i.price         AS base_price,
          i.addons_json   AS addons_json,
          i.addons_total  AS addons_total,
          i.row_total     AS row_total,
          o.raw_text      AS raw_text
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

    # 3) Преобразуем addons_json -> «Добавки» (читабельный текст)
    def _fmt_addons(raw):
        try:
            arr = json.loads(raw) if raw else []
        except Exception:
            return ""
        if not arr:
            return ""
        return ", ".join(f"{a.get('name','')} ({int(a.get('price',0))}₽)" for a in arr)

    if not orders_df.empty:
        orders_df["addons_text"] = orders_df["addons_json"].apply(_fmt_addons)
    else:
        orders_df["addons_text"] = pd.Series(dtype=str)

    # 4) Переименовываем и упорядочиваем колонки (это и есть «пункты 2 и 3»)
    rename_map = {
        "date": "Дата",
        "payment_type": "Тип оплаты",
        "item_name": "Название",
        "base_price": "Базовая цена",
        "addons_text": "Добавки",
        "addons_total": "Сумма добавок",
        "row_total": "Сумма позиции",
        "raw_text": "Запрос",
    }
    orders_df = orders_df.rename(columns=rename_map)

    # Желаемый порядок
    desired_cols = [
        "Дата",
        "Тип оплаты",
        "Название",
        "Базовая цена",
        "Добавки",
        "Сумма добавок",
        "Сумма позиции",
        "Запрос",
    ]
    # На случай, если где-то колонка отсутствует
    existing_cols = [c for c in desired_cols if c in orders_df.columns]
    orders_df = orders_df[existing_cols]

    # Заголовки для лога действий
    actions_df.columns = [
        "Дата/время",
        "Действие",
        "Тип оплаты",
        "Название",
        "user_id",
        "username",
    ]

    # 5) Имена файлов
    if start_date and end_date:
        period_str = (
            start_date.isoformat()
            if start_date == end_date
            else f"{start_date.isoformat()}__{end_date.isoformat()}"
        )
    else:
        period_str = "all"

    report_path = f"report_{period_str}.xlsx"
    log_path = f"log_report_{period_str}.xlsx"

    # 6) Пишем отчёт с итогами
    with pd.ExcelWriter(report_path, engine="openpyxl") as writer:
        # «Все позиции» + ИТОГО
        df_all = orders_df.copy()
        total_all = df_all["Сумма позиции"].sum() if "Сумма позиции" in df_all else 0
        if not df_all.empty:
            df_all = pd.concat(
                [
                    df_all,
                    pd.DataFrame(
                        [
                            {
                                "Дата": "",
                                "Тип оплаты": "",
                                "Название": "ИТОГО",
                                "Базовая цена": "",
                                "Добавки": "",
                                "Сумма добавок": "",
                                "Сумма позиции": total_all,
                                "Запрос": "",
                            }
                        ]
                    ),
                ],
                ignore_index=True,
            )
        df_all.to_excel(writer, sheet_name="Все позиции", index=False)

        # Листы по каждому типу оплаты + ИТОГО
        if not orders_df.empty and "Тип оплаты" in orders_df:
            for pt in sorted(
                orders_df["Тип оплаты"].dropna().unique(), key=lambda s: str(s).lower()
            ):
                mask = (
                    orders_df["Тип оплаты"].astype(str).str.lower() == str(pt).lower()
                )
                df_pt = orders_df[mask].copy()
                sheet = str(pt).capitalize()

                total_pt = (
                    df_pt["Сумма позиции"].sum() if "Сумма позиции" in df_pt else 0
                )
                if not df_pt.empty:
                    df_pt = pd.concat(
                        [
                            df_pt,
                            pd.DataFrame(
                                [
                                    {
                                        "Дата": "",
                                        "Тип оплаты": sheet,
                                        "Название": "ИТОГО",
                                        "Базовая цена": "",
                                        "Добавки": "",
                                        "Сумма добавок": "",
                                        "Сумма позиции": total_pt,
                                        "Запрос": "",
                                    }
                                ]
                            ),
                        ],
                        ignore_index=True,
                    )

                df_pt.to_excel(writer, sheet_name=sheet, index=False)

        # Группировка по (Тип оплаты, Название) + общий итог по сумме
        if not orders_df.empty:
            grouped = (
                orders_df.groupby(["Тип оплаты", "Название"], dropna=False)
                .agg(
                    Количество=("Сумма позиции", "size"),
                    Общая_сумма=("Сумма позиции", "sum"),
                )
                .reset_index()
            )
        else:
            grouped = pd.DataFrame(
                columns=["Тип оплаты", "Название", "Количество", "Общая_сумма"]
            )

        if not grouped.empty:
            grouped_total = pd.DataFrame(
                [
                    [
                        "",
                        "ИТОГО",
                        grouped["Количество"].sum(),
                        grouped["Общая_сумма"].sum(),
                    ]
                ],
                columns=["Тип оплаты", "Название", "Количество", "Общая_сумма"],
            )
            grouped = pd.concat([grouped, grouped_total], ignore_index=True)

        grouped.to_excel(writer, sheet_name="Группировка", index=False)

    # 7) Лог действий в отдельный файл
    with pd.ExcelWriter(log_path, engine="openpyxl") as writer:
        actions_df.to_excel(writer, sheet_name="Журнал действий", index=False)

    # 8) Автоподбор ширины
    auto_adjust_columns(report_path)
    auto_adjust_columns(log_path)

    return report_path, log_path
