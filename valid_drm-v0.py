import csv
import sys
import requests
from pathlib import Path
from urllib.parse import urlparse
from html import escape


CSV_DRM_FIELDS = ["URL", "TIMESHIFT_URL"]


def read_csv(csv_filename: str) -> list[dict]:
    """
    Lê um CSV com cabeçalho e retorna uma lista de dicionários (linhas).
    """
    script_dir = Path(__file__).resolve().parent
    csv_path = script_dir / csv_filename

    if not csv_path.exists():
        raise FileNotFoundError(f"Arquivo CSV não encontrado: {csv_path}")

    with csv_path.open(newline="", encoding="utf-8") as f:
        reader = csv.DictReader(f)
        return list(reader)


def check_manifest(url: str) -> dict:
    """
    Verifica DRM em uma URL de manifest.
    """
    if not url:
        return {
            "checked": False,
            "type": "-",
            "drm_found": False,
            "error": None,
        }

    result = {
        "checked": True,
        "type": "UNKNOWN",
        "drm_found": False,
        "error": None,
    }

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
            result["drm_found"] = "#EXT-X-KEY" in content

    except requests.RequestException as e:
        result["error"] = str(e)

    return result


def generate_html_report(rows: list[dict], results: list[dict], output_file: Path):
    """
    Gera relatório HTML com dados do CSV + resultado DRM.
    """
    headers = [h for h in rows[0].keys() if h not in CSV_DRM_FIELDS]

    table_rows = []

    for idx, (row, drm_result) in enumerate(zip(rows, results), start=1):
        url_res = drm_result["URL"]
        ts_res = drm_result["TIMESHIFT_URL"]

        def format_status(res):
            if not res["checked"]:
                return "-"
            if res["error"]:
                return "ERRO"
            return "SIM" if res["drm_found"] else "NÃO"

        table_rows.append(f"""
            <tr>
                <td>{idx}</td>
                {''.join(f"<td>{escape(row[h])}</td>" for h in headers)}
                <td>{escape(row.get("URL", ""))}</td>
                <td>{format_status(url_res)}</td>
                <td>{url_res["type"]}</td>
                <td>{escape(row.get("TIMESHIFT_URL", ""))}</td>
                <td>{format_status(ts_res)}</td>
                <td>{ts_res["type"]}</td>
            </tr>
        """)

    html = f"""
    <!DOCTYPE html>
    <html lang="pt-BR">
    <head>
        <meta charset="UTF-8">
        <title>Relatório de Verificação de DRM</title>
        <style>
            body {{ font-family: Arial, sans-serif; background: #f5f5f5; padding: 20px; }}
            table {{ border-collapse: collapse; width: 100%; background: #fff; }}
            th, td {{ border: 1px solid #ddd; padding: 8px; }}
            th {{ background: #333; color: #fff; }}
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
                    <th>DRM (URL)</th>
                    <th>Tipo</th>
                    <th>TIMESHIFT_URL</th>
                    <th>DRM (TS)</th>
                    <th>Tipo</th>
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
        print("Uso: python check_drm.py <arquivo.csv>")
        sys.exit(1)

    csv_filename = sys.argv[1]
    script_dir = Path(__file__).resolve().parent
    output_html = script_dir / "relatorio.html"

    rows = read_csv(csv_filename)

    results = []

    for row in rows:
        drm_results = {}
        for field in CSV_DRM_FIELDS:
            drm_results[field] = check_manifest(row.get(field, "").strip())
        results.append(drm_results)

    generate_html_report(rows, results, output_html)

    print(f"Relatório HTML gerado com sucesso: {output_html}")


if __name__ == "__main__":
    main()
