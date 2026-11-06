# healthapp

Маленький веб-сервис (Python/Flask + waitress): `GET /health` и access-лог в файл.
Упакован в Docker, запускается как служба systemd. Проверено на: _(впишите, на чём реально проверяли, напр. Ubuntu 24.04)_.

## 1. Что установить заранее

```bash
sudo apt update
sudo apt install -y docker.io make logrotate curl
sudo systemctl enable --now docker
```

## 2. Сборка и развёртывание

```bash
git clone <ссылка-на-репозиторий> healthapp && cd healthapp
make build          # собрать образ healthapp:1.0
make deploy         # разложить файлы, включить и запустить службу
```

`make deploy` безопасно запускать повторно: существующий `/etc/healthapp/healthapp.env` не перезаписывается, остальное просто обновляется.

## 3. Проверка

```bash
systemctl status healthapp          # active (running)
curl -i http://localhost:8080/health   # 200 {"status":"ok"}
curl -i http://localhost:8080/nope     # 404
sudo docker inspect --format '{{.State.Health.Status}}' healthapp   # healthy
```

## 4. Логи

- Access-лог: `/var/log/healthapp/access.log` (`make logs` или `sudo tail -f /var/log/healthapp/access.log`).
- Служебные сообщения сервиса: `sudo journalctl -u healthapp -f`.
- Формат: `2026-11-05T13:41:07+00:00 172.17.0.1 GET /health 200`.
  IP — адрес docker-шлюза (172.17.0.1), т.к. запрос приходит через NAT Docker. Часовой пояс в контейнере — UTC.
- Healthcheck Docker ходит на `/health` раз в 30 с, поэтому такие строки в логе — норма.

## 5. Если контейнер упадёт

`Restart=always` + `RestartSec=5`: systemd поднимет службу через 5 секунд. Проверка:

```bash
sudo docker kill healthapp
sleep 7
systemctl status healthapp          # снова active (running), в логе "Scheduled restart job"
curl http://localhost:8080/health
```

Если лог-файл недоступен для записи, сервис не падает, `/health` отвечает 503
`{"status":"error","reason":"log not writable"}`. Проверка: `sudo chmod 000 /var/log/healthapp`
(от root доступ всё равно есть, но контейнер работает как UID 10001, т.е. запись для него заблокирована), затем вернуть `sudo chmod 755 /var/log/healthapp`.

## 6. Как поменять порт

```bash
sudo nano /etc/healthapp/healthapp.env     # APP_PORT=9090
sudo systemctl restart healthapp
curl http://localhost:9090/health
```

Порт задаётся один раз: и для сервиса внутри контейнера, и для `-p` в unit-файле.

## 7. Ротация логов

Конфиг: `/etc/logrotate.d/healthapp` (раз в сутки, 7 файлов, сжатие, `missingok`).
Сервис **не держит файл открытым**: на каждую запись открывает его в режиме append и закрывает. Поэтому после ротации новые записи сами попадают в новый файл, сигналы и `copytruncate` не нужны.

Как проверял:

```bash
curl -s localhost:8080/health
sudo logrotate -f /etc/logrotate.d/healthapp
ls -l /var/log/healthapp/        # access.log (новый, пустой) и access.log.1
curl -s localhost:8080/health
sudo cat /var/log/healthapp/access.log     # там только новая строка
```

## 8. Зачем нужен каждый пункт

**Docker**
- _Версия базового образа, не latest_: сборка воспроизводима, образ не изменится сам при выходе новой версии.
- _Многостадийная сборка_: pip и кэш остаются на первой стадии, в финальный образ идут только установленные пакеты. Образ меньше и безопаснее.
- _Не root_: при взломе сервиса атакующий не получает root в контейнере. UID фиксирован (10001), чтобы выдать этому UID права на папку логов на хосте.
- _.dockerignore_: в образ не попадают `.git`, кэши, лишние файлы. Сборка быстрее, секреты не утекают.
- _Том для логов_: файлы контейнера исчезают вместе с ним; логи на хосте переживают перезапуск и доступны logrotate.
- _HEALTHCHECK_ (бонус): Docker видит, отвечает ли сервис, а не только жив ли процесс.

**systemd**
- `Requires/After=docker.service`: служба стартует после Docker и не работает без него.
- `Restart=always`, `RestartSec=5`: автоперезапуск с паузой, чтобы не было «бешеного» цикла.
- `ExecStartPre=-docker rm -f`: убирает остатки старого контейнера с тем же именем (`-` = игнорировать ошибку, если его нет).
- `docker run --rm --init`: `--rm` не копит остановленные контейнеры; `--init` нужен, потому что Python как PID 1 игнорирует SIGTERM, и `docker stop` ждал бы 10 с до SIGKILL.
- `ExecStop=docker stop`: корректная остановка контейнера.
- `EnvironmentFile`: настройки вне unit-файла; тот же файл отдаётся контейнеру через `--env-file`.
- `--memory 128m`: контейнер не съест всю память сервера.
- `systemctl enable` (делает `make deploy`): автозапуск после перезагрузки.

## 9. Что не сделано / сделал бы иначе

- Не реализован `/metrics` (Prometheus), бонус.
- Реальная проверка на чистой Ubuntu: _(впишите честно, что проверили, а что нет)_.
- Образ собирается на самом сервере; в реальности лучше собирать в CI и тянуть из registry.
- Для production: часовой пояс из настроек, ограничение CPU, `--read-only` файловая система контейнера.
- IP клиента в логе — адрес docker-шлюза; для реального IP нужен `--network host` или прокси с `X-Forwarded-For`.
