"""healthapp: GET /health + access-лог в файл."""
import logging
import os
from datetime import datetime

from flask import Flask, jsonify, request

# --- Настройки из переменных окружения (со значениями по умолчанию) ---
APP_HOST = os.getenv("APP_HOST", "0.0.0.0")
APP_PORT = int(os.getenv("APP_PORT", "8080"))
LOG_PATH = os.getenv("LOG_PATH", "/var/log/healthapp/access.log")
LOG_LEVEL = os.getenv("LOG_LEVEL", "INFO").upper()

# Служебные сообщения самого сервиса идут в stdout (их видно в `docker logs`)
logging.basicConfig(
    level=getattr(logging, LOG_LEVEL, logging.INFO),
    format="%(asctime)s %(levelname)s %(message)s",
)
log = logging.getLogger("healthapp")

app = Flask(__name__)


def log_writable() -> bool:
    """Проверяем, можно ли дописывать в лог-файл (нет папки / нет прав -> False)."""
    try:
        with open(LOG_PATH, "a"):
            return True
    except OSError:
        return False


@app.get("/health")
def health():
    if not log_writable():
        return jsonify(status="error", reason="log not writable"), 503
    return jsonify(status="ok")


@app.after_request
def write_access_log(response):
    """Одна строка на каждый запрос (в т.ч. 404). Сбой записи не роняет сервис."""
    ts = datetime.now().astimezone().isoformat(timespec="seconds")
    line = f"{ts} {request.remote_addr} {request.method} {request.path} {response.status_code}\n"
    try:
        # Открываем файл на время записи и сразу закрываем: после logrotate
        # следующая запись автоматически попадёт в НОВЫЙ файл.
        with open(LOG_PATH, "a", encoding="utf-8") as f:
            f.write(line)
    except OSError as exc:
        log.warning("cannot write access log %s: %s", LOG_PATH, exc)
    return response


def main():
    from waitress import serve

    log.info("starting on %s:%s, log file: %s", APP_HOST, APP_PORT, LOG_PATH)
    serve(app, host=APP_HOST, port=APP_PORT)


if __name__ == "__main__":
    main()
