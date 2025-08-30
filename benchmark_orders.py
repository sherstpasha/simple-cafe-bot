import asyncio
import csv
import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Tuple, Optional

# ====== НАСТРОЙКИ ======
CSV_PATH = Path("orders_dataset.csv")
OUTPUT_PATH = None
LIMIT = None
TEMPERATURE = 0.2
SAVE_RAW_REPLIES_NDJSON: Optional[Path] = (
    None  # Path("raw_replies.ndjson") чтобы сохранять сырые ответы
)
# =======================

from llm_client import parse_order_from_text
from config import MENU_FILE


def load_menu() -> Dict[str, Any]:
    with open(MENU_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def norm_pay(v) -> int:
    try:
        iv = int(v)
        return iv if iv in (-1, 0, 1) else -1
    except Exception:
        return -1


def canon_item(item: Dict[str, Any]) -> Dict[str, Any]:
    name = (item.get("n") or item.get("name") or "").strip()
    try:
        q = int(item.get("q") or item.get("qty") or 1)
    except Exception:
        q = 1
    addons = item.get("a") or item.get("addons") or []
    if isinstance(addons, dict):
        addons = list(addons.values())
    addons = [str(a).strip() for a in addons if str(a).strip()]
    addons.sort(key=lambda s: s.lower())
    return {"n": name, "q": max(1, q), "a": addons}


def canon_list(items: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    canon = [canon_item(x) for x in items if isinstance(x, dict)]
    canon.sort(key=lambda x: (x["n"].lower(), x["q"], tuple(x["a"])))
    return canon


def canon_result(d: Dict[str, Any]) -> Tuple[List[Dict[str, Any]], int]:
    it = d.get("it") or d.get("items") or []
    pay = d.get("pay", -1)
    return canon_list(it), norm_pay(pay)


def dicts_equal(a: List[Dict[str, Any]], b: List[Dict[str, Any]]) -> bool:
    if len(a) != len(b):
        return False
    for x, y in zip(a, b):
        if x != y:
            return False
    return True


def make_diff(
    a: List[Dict[str, Any]], b: List[Dict[str, Any]], pay_a: int, pay_b: int
) -> str:
    diffs = []
    if pay_a != pay_b:
        diffs.append(f"pay: expected {pay_a}, got {pay_b}")
    if len(a) != len(b):
        diffs.append(f"len(it): expected {len(a)}, got {len(b)}")
    common = min(len(a), len(b))
    for i in range(common):
        if a[i] != b[i]:
            diffs.append(f"it[{i}]: expected {a[i]}, got {b[i]}")
            break
    if len(b) > len(a):
        diffs.append(f"extra items: {b[len(a):]}")
    if len(a) > len(b):
        diffs.append(f"missing items: {a[len(b):]}")
    return "; ".join(diffs) if diffs else ""


@dataclass
class RowResult:
    idx: int
    request: str
    expected_json: str
    model_json: str
    match: bool
    latency_ms: float
    diff: str
    error_kind: str = ""
    error_reason: str = ""
    error_context: str = ""  # небольшой сниппет с ^


async def eval_row(
    idx: int,
    req: str,
    expected_json: str,
    menu: Dict[str, Any],
    temperature: float,
    raw_sink,
):
    t0 = time.perf_counter()
    try:
        model_dict = await parse_order_from_text(req, menu, temperature=temperature)
        model_json = json.dumps(model_dict, ensure_ascii=False)
        latency_ms = (time.perf_counter() - t0) * 1000.0

        # Канонизируем ожидаемое и фактическое
        try:
            exp_dict = json.loads(expected_json)
        except Exception as e:
            return RowResult(
                idx,
                req,
                expected_json,
                model_json,
                False,
                latency_ms,
                f"bad_expected_json: {e}",
            )

        exp_it, exp_pay = canon_result(exp_dict)
        mod_it, mod_pay = canon_result(model_dict)

        ok = (exp_pay == mod_pay) and dicts_equal(exp_it, mod_it)
        diff = "" if ok else make_diff(exp_it, mod_it, exp_pay, mod_pay)
        return RowResult(idx, req, expected_json, model_json, ok, latency_ms, diff)

    except Exception as e:
        latency_ms = (time.perf_counter() - t0) * 1000.0
        # по желанию — сохраняем краткую диагностику
        if raw_sink is not None:
            raw_sink.write(
                json.dumps(
                    {
                        "idx": idx,
                        "request": req,
                        "error": type(e).__name__,
                        "message": str(e),
                    },
                    ensure_ascii=False,
                )
                + "\n"
            )

        return RowResult(
            idx,
            req,
            expected_json,
            model_json=json.dumps({"error": str(e)}, ensure_ascii=False),
            match=False,
            latency_ms=latency_ms,
            diff="error",
            error_kind=type(e).__name__,
            error_reason=str(e),
            error_context="",  # контекст больше не формируем
        )


async def run_benchmark():
    menu = load_menu()
    # читаем CSV
    rows = []
    with open(CSV_PATH, "r", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        for i, row in enumerate(reader):
            if LIMIT is not None and i >= LIMIT:
                break
            req = (row.get("request") or "").strip()
            ans = (row.get("answer_json") or "").strip()
            if not req or not ans:
                continue
            rows.append((i, req, ans))

    results: List[RowResult] = []
    latencies = []
    ok_count = 0

    raw_sink = (
        open(SAVE_RAW_REPLIES_NDJSON, "w", encoding="utf-8")
        if SAVE_RAW_REPLIES_NDJSON
        else None
    )
    try:
        for idx, req, ans in rows:
            r = await eval_row(idx, req, ans, menu, TEMPERATURE, raw_sink)
            results.append(r)
            latencies.append(r.latency_ms)
            ok_count += 1 if r.match else 0
            status = "OK" if r.match else f"ERR({r.error_kind or r.diff})"
            print(
                f"[{len(results)}/{len(rows)}] {status}  {r.latency_ms:.0f} ms  — {req[:60]}"
            )
    finally:
        if raw_sink is not None:
            raw_sink.close()

    total = len(results)
    avg_ms = (sum(latencies) / total) if total else 0.0
    acc = (ok_count / total) if total else 0.0

    print("\n==== SUMMARY ====")
    print(f"Total: {total}")
    print(f"Matched: {ok_count}  ({acc:.1%})")
    print(f"Avg latency: {avg_ms:.1f} ms")

    out = OUTPUT_PATH or CSV_PATH.with_name(CSV_PATH.stem + "_report.csv")
    with open(out, "w", encoding="utf-8", newline="") as f:
        w = csv.writer(f)
        w.writerow(
            [
                "idx",
                "request",
                "expected_json",
                "model_json",
                "match",
                "latency_ms",
                "diff",
                "error_kind",
                "error_reason",
                "error_context",
            ]
        )
        for r in results:
            w.writerow(
                [
                    r.idx,
                    r.request,
                    r.expected_json,
                    r.model_json,
                    int(r.match),
                    f"{r.latency_ms:.1f}",
                    r.diff,
                    r.error_kind,
                    r.error_reason,
                    r.error_context,
                ]
            )

    print(f"\nReport saved to: {out}")


if __name__ == "__main__":
    asyncio.run(run_benchmark())
