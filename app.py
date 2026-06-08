from __future__ import annotations

import json
import os
import subprocess
import sys
from http import HTTPStatus
from http.server import SimpleHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlparse


ROOT = Path(__file__).resolve().parent
STATIC_ROOT = ROOT / "static"
CATALOG_PATH = STATIC_ROOT / "data" / "catalog.json"
SOURCE_ROOT = Path(os.environ.get("CONTENT_SOURCE", r"D:\美股基本面分析"))


class DashboardHandler(SimpleHTTPRequestHandler):
    server_version = "FundamentalDashboard/1.0"
    extensions_map = {
        **SimpleHTTPRequestHandler.extensions_map,
        ".html": "text/html; charset=utf-8",
        ".css": "text/css; charset=utf-8",
        ".js": "application/javascript; charset=utf-8",
        ".json": "application/json; charset=utf-8",
    }

    def translate_path(self, path: str) -> str:
        parsed = urlparse(path)
        clean_path = unquote(parsed.path).lstrip("/")
        if clean_path in {"", "index.html"}:
            return str(STATIC_ROOT / "index.html")
        candidate = (STATIC_ROOT / clean_path).resolve()
        if not str(candidate).startswith(str(STATIC_ROOT.resolve())):
            return str(STATIC_ROOT / "index.html")
        return str(candidate)

    def end_headers(self) -> None:
        self.send_header("Access-Control-Allow-Origin", "*")
        self.send_header("Access-Control-Allow-Methods", "GET, POST, OPTIONS")
        self.send_header("Access-Control-Allow-Headers", "Content-Type")
        super().end_headers()

    def do_OPTIONS(self) -> None:
        self.send_response(HTTPStatus.NO_CONTENT)
        self.end_headers()

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path == "/api/catalog":
            self.write_json(load_catalog())
            return
        if parsed.path == "/api/health":
            self.write_json({"ok": True, "catalog_exists": CATALOG_PATH.exists(), "source_root": str(SOURCE_ROOT)})
            return
        super().do_GET()

    def do_POST(self) -> None:
        parsed = urlparse(self.path)
        if parsed.path != "/api/rebuild":
            self.send_error(HTTPStatus.NOT_FOUND, "unknown api endpoint")
            return
        self.rebuild_catalog()

    def rebuild_catalog(self) -> None:
        env = os.environ.copy()
        env["PYTHONIOENCODING"] = "utf-8"
        command = [
            sys.executable,
            str(ROOT / "tools" / "build_data.py"),
            "--source",
            str(SOURCE_ROOT),
            "--output",
            str(CATALOG_PATH),
        ]
        try:
            completed = subprocess.run(
                command,
                cwd=str(ROOT),
                env=env,
                capture_output=True,
                text=True,
                timeout=int(os.environ.get("REBUILD_TIMEOUT", "180")),
                check=False,
            )
        except subprocess.TimeoutExpired:
            self.write_json({"ok": False, "error": "更新超时，请缩小资料目录或在本机命令行运行构建脚本。"}, status=500)
            return

        stdout = completed.stdout.strip()
        stderr = completed.stderr.strip()
        payload: dict[str, object]
        try:
            payload = json.loads(stdout.splitlines()[-1]) if stdout else {}
        except json.JSONDecodeError:
            payload = {"stdout": stdout}
        payload["ok"] = completed.returncode == 0 and bool(payload.get("ok", True))
        payload["stderr"] = stderr
        payload["return_code"] = completed.returncode
        if completed.returncode != 0:
            self.write_json(payload, status=500)
            return
        market_command = [
            sys.executable,
            str(ROOT / "tools" / "build_market_data.py"),
            "--catalog",
            str(CATALOG_PATH),
        ]
        try:
            market_completed = subprocess.run(
                market_command,
                cwd=str(ROOT),
                env=env,
                capture_output=True,
                text=True,
                timeout=int(os.environ.get("MARKET_REBUILD_TIMEOUT", "540")),
                check=False,
            )
            market_stdout = market_completed.stdout.strip()
            try:
                payload["market"] = json.loads(market_stdout.splitlines()[-1]) if market_stdout else {}
            except json.JSONDecodeError:
                payload["market"] = {"stdout": market_stdout}
            payload["market_return_code"] = market_completed.returncode
            if market_completed.stderr.strip():
                payload["market_stderr"] = market_completed.stderr.strip()
        except subprocess.TimeoutExpired:
            payload["market"] = {"ok": False, "error": "市场数据更新超时，已保留上一次数据。"}
        self.write_json(payload)

    def write_json(self, payload: object, status: int = 200) -> None:
        body = json.dumps(payload, ensure_ascii=False, indent=2).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def load_catalog() -> dict[str, object]:
    if not CATALOG_PATH.exists():
        return {
            "generated_at": None,
            "source_root": str(SOURCE_ROOT),
            "stats": {"file_count": 0, "company_count": 0, "theme_count": 0, "total_size_bytes": 0, "file_type_counts": {}},
            "themes": [],
            "companies": [],
            "assets": [],
            "tabular_assets": [],
            "warning": "catalog.json 不存在，请点击更新或运行 tools/build_data.py。",
        }
    return json.loads(CATALOG_PATH.read_text(encoding="utf-8"))


def ensure_catalog() -> None:
    if CATALOG_PATH.exists() or not SOURCE_ROOT.exists():
        return
    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    subprocess.run(
        [sys.executable, str(ROOT / "tools" / "build_data.py"), "--source", str(SOURCE_ROOT), "--output", str(CATALOG_PATH)],
        cwd=str(ROOT),
        env=env,
        check=False,
    )


def main() -> int:
    ensure_catalog()
    port = int(os.environ.get("PORT", "8088"))
    address = os.environ.get("HOST", "127.0.0.1")
    server = ThreadingHTTPServer((address, port), DashboardHandler)
    print(f"美股基本面交互仪表盘已启动: http://{address}:{port}")
    print(f"资料源: {SOURCE_ROOT}")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
