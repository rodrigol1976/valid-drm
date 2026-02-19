import csv
import sys
import time
import requests
from pathlib import Path
from urllib.parse import urlparse
from html import escape
from concurrent.futures import ThreadPoolExecutor, as_completed
from threading import Lock


CSV_DRM_FIELDS = ["URL", "TIMESHIFT_URL"]
MAX_WORKERS = 3  # ajuste conforme capacidade / rede


def read_csv(csv_filename: str) -> list[dict]:
    script_dir = Path(__file__).resolve().parent
    csv_path = script_dir / csv_filename

    if not csv_path.exists():
        raise FileNotFoundError(f"Arquivo CSV não encontrado: {csv_path}")

    with csv_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return list(reader)


def check_manifest(url: str) -> dict:
    if not url:
        return {"checked": False, "type": "-", "drm_found": False, "error": None}

    result = {"checked": True, "type": "UNKNOWN", "drm_found": False, "error": None}

    try:
        response = requests.get(url, timeout=30)
        response.raise_for_status()
        content = response.text
        path = urlparse(url).path.lower()

        if path.endswith(".mpd"):
            result["type"] = "MPD"
            result["drm_found"] = "<ContentProtection" in content

        elif path.endswith(".m3u8"):
            result["type"] = "M3U8"
            has_key = "#EXT-X-KEY" in content
            method_none = "#EXT-X-KEY:METHOD=NONE" in content
            result["drm_found"] = has_key and not method_none

    except requests.RequestException as e:
        result["error"] = str(e)

    return result


def process_row(index: int, row: dict) -> tuple[int, dict]:
    """
    Processa uma linha do CSV (URL + TIMESHIFT_URL)
    """
    drm_results = {}
    for field in CSV_DRM_FIELDS:
        drm_results[field] = check_manifest(row.get(field, "").strip())
    return index, drm_results


def format_time(seconds: float) -> str:
    m, s = divmod(int(seconds), 60)
    return f"{m:02d}:{s:02d}"


def generate_html_report(rows: list[dict], results: list[dict], output_file: Path):
    headers = [h for h in rows[0].keys() if h not in CSV_DRM_FIELDS]

    def status_cell(res):
        if not res["checked"]:
            return '<td class="na">-</td>'
        if res["error"]:
            return '<td class="erro">ERRO</td>'
        if res["drm_found"]:
            return '<td class="sim">SIM</td>'
        return '<td class="nao">NÃO</td>'

    table_rows = []

    for idx, (row, drm) in enumerate(zip(rows, results), start=1):
        table_rows.append(f"""
        <tr>
            <td>{idx}</td>
            {''.join(f"<td>{escape(row[h])}</td>" for h in headers)}
            <td>{escape(row.get("URL", ""))}</td>
            {status_cell(drm["URL"])}
            <td>{drm["URL"]["type"]}</td>
            <td>{escape(row.get("TIMESHIFT_URL", ""))}</td>
            {status_cell(drm["TIMESHIFT_URL"])}
            <td>{drm["TIMESHIFT_URL"]["type"]}</td>
        </tr>
        """)

    html = f"""
    <!DOCTYPE html>
    <html lang="pt-BR">
    <head>
        <meta charset="UTF-8">
        <title>Relatório de DRM</title>
        <style>
            body {{ font-family: Arial; background: #f5f5f5; padding: 20px; }}
            table {{ width: 100%; border-collapse: collapse; background: #fff; }}
            th, td {{ border: 1px solid #ddd; padding: 8px; text-align: center; }}
            th {{ background: #333; color: #fff; }}
            td.sim {{ background: #c6efce; color: #006100; font-weight: bold; }}
            td.nao {{ background: #ffc7ce; color: #9c0006; font-weight: bold; }}
            td.erro {{ background: #ffeb9c; color: #9c6500; font-weight: bold; }}
            td.na {{ background: #e7e6e6; color: #595959; }}
        </style>
    </head>
    <body>
        <h1>Relatório de Verificação de DRM</h1>
        <table>
            <thead>
                <tr>
                    <th>#</th>
                    {''.join(f"<th>{h}</th>" for h in headers)}
                    <th>URL</th>
                    <th>DRM (SIM/NÃO)</th>
                    <th>EXTENSÃO</th>
                    <th>TIMESHIFT_URL</th>
                    <th>DRM (SIM/NÃO)</th>
                    <th>EXTENSÃO</th>
                </tr>
            </thead>
            <tbody>
                {''.join(table_rows)}
            </tbody>
        </table>
    </body>
    </html>
    """

    output_file.write_text(html, encoding="utf-8")


def main():
    if len(sys.argv) != 2:
        print("Uso: python valid_drm.py <arquivo.csv>")
        sys.exit(1)

    csv_filename = sys.argv[1]
    script_dir = Path(__file__).resolve().parent
    output_html = script_dir / "relatorio.html"

    rows = read_csv(csv_filename)
    total = len(rows)
    results = [None] * total

    completed = 0
    lock = Lock()
    start_time = time.time()

    with ThreadPoolExecutor(max_workers=MAX_WORKERS) as executor:
        futures = {
            executor.submit(process_row, idx, row): idx
            for idx, row in enumerate(rows)
        }

        for future in as_completed(futures):
            idx, drm_result = future.result()
            results[idx] = drm_result

            with lock:
                completed += 1
                elapsed = time.time() - start_time
                avg = elapsed / completed
                remaining = avg * (total - completed)

                print(
                    f"[{completed}/{total}] "
                    f"Decorrido: {format_time(elapsed)} | "
                    f"ETA: {format_time(remaining)}"
                )

    generate_html_report(rows, results, output_html)

    total_time = time.time() - start_time
    print(f"\nProcesso concluído em {format_time(total_time)}")
    print(f"Relatório gerado: {output_html}")


if __name__ == "__main__":
    main()