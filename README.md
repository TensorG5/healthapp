# healthapp

Привет, сделал маленький веб-сервис используя Python с Flask и waitress: `GET /health` и access-лог в файл.
Упакован в Docker, запускается как служба systemd. Проверял на Debian 13 и Linux Mint 22.3.

## 1. Что установить заранее

```bash
sudo apt update
sudo apt install -y docker.io git make logrotate curl
sudo systemctl enable --now docker
sudo usermod -aG docker $USER      # чтобы make build работал без sudo
```

После `usermod` нужно выйти из сессии и зайти снова, иначе будет `permission denied` при `docker build`.
Цели Makefile, которые меняют систему (`deploy`, `run`, `logs`, `clean`), сами вызывают `sudo`.

Перед первым запуском проверьте, что порт 8080 свободен: `ss -ltn | grep 8080` (пустой вывод = свободен).
Если занят, поменяйте `APP_PORT` в `deploy/healthapp.env` до `make deploy` (см. раздел 6).

## 2. Сборка и развёртывание

```bash
git clone https://github.com/TensorG5/healthapp.git healthapp && cd healthapp
make build          # собрать образ healthapp:1.0
make deploy         # разложить файлы, включить и запустить службу
```

`make deploy` безопасно запускать повторно: существующий `/etc/healthapp/healthapp.env` не перезаписывается, остальное просто обновляется.

Что делает `make deploy`: создаёт на хосте системного пользователя и группу `healthapp` (UID/GID 10001), папку `/var/log/healthapp`,
кладёт на место unit-файл, env-файл и конфиг logrotate, делает `daemon-reload`, включает автозапуск и перезапускает службу.
Предупреждение `useradd warning: ... uid 10001 is greater than SYS_UID_MAX 999` безвредно: номер выбран намеренно выше системного диапазона, чтобы не пересечься с существующими пользователями.

## 3. Проверка

```bash
systemctl status healthapp          # active (running)
curl -i http://localhost:8080/health   # 200 {"status":"ok"}
curl -i http://localhost:8080/nope     # 404
sudo docker inspect --format '{{.State.Health.Status}}' healthapp   # healthy
```

Дополнительные проверки:

```bash
sudo docker exec healthapp id                                      # uid=10001(healthapp): не root
sudo docker inspect healthapp --format '{{.HostConfig.Memory}}'    # 134217728 (128 МБ)
sudo docker stats --no-stream healthapp                            # MEM USAGE / LIMIT
sudo systemctl stop healthapp && systemctl status healthapp        # inactive (dead)
sudo systemctl start healthapp
sudo reboot                                                        # после загрузки curl отвечает без лишних действий
```

Строка `Memory` в `systemctl status` относится к процессу `docker run` (клиенту), а не к контейнеру. Реальную память контейнера показывает `docker stats`.

## 4. Логи

- Access-лог: `/var/log/healthapp/access.log` (`make logs` или `sudo tail -f /var/log/healthapp/access.log`).
- Служебные сообщения сервиса: `sudo journalctl -u healthapp -f`.
  Без `sudo` `systemctl status` может написать `some journal files were not opened due to insufficient permissions`: это не ошибка, просто у пользователя нет доступа к части журнала.
- Формат: `2026-11-05T13:41:07+00:00 172.17.0.1 GET /health 200`.
  IP — адрес docker-шлюза (172.17.0.1), т.к. запрос приходит через NAT Docker. Часовой пояс в контейнере — UTC.
- Healthcheck Docker ходит на `/health` раз в 30 с (с адреса 127.0.0.1), поэтому такие строки в логе — норма.

## 5. Если контейнер упадёт

`Restart=always` + `RestartSec=5`: systemd поднимет службу через 5 секунд. Проверка:

```bash
sudo docker kill healthapp
sleep 7
systemctl status healthapp          # снова active (running), в логе "Scheduled restart job"
curl http://localhost:8080/health
```

В журнале (`sudo journalctl -u healthapp -n 15`) будет `status=137`: это 128 + 9, процесс убит сигналом SIGKILL.

В случае, если лог-файл недоступен для записи, сервис не падает, `/health` отвечает 503
`{"status":"error","reason":"log not writable"}`. Проверка: `sudo chmod 000 /var/log/healthapp`
(от root доступ всё равно есть, но контейнер работает как UID 10001, т.е. запись для него заблокирована), затем вернуть `sudo chmod 755 /var/log/healthapp`.
После возврата прав сервис снова отвечает 200 без перезапуска: доступность лога проверяется при каждом запросе.
Flask сортирует ключи JSON по алфавиту, поэтому в теле ответа порядок `reason`, `status`; для JSON это не важно.

## 6. Как поменять порт

```bash
sudo nano /etc/healthapp/healthapp.env     # APP_PORT=9090
sudo systemctl restart healthapp
curl http://localhost:9090/health
```

Порт задаётся один раз: и для сервиса внутри контейнера, и для `-p` в unit-файле (systemd подставляет `${APP_PORT}` из env-файла).

Менять `LOG_PATH` без правки `-v` в unit-файле нельзя: папка логов на хосте (`/var/log/healthapp`) зафиксирована, а `LOG_PATH` задаёт путь внутри контейнера.

## 7. Ротация логов

Конфиг: `/etc/logrotate.d/healthapp` (раз в сутки, 7 файлов, сжатие, `missingok`).
Сервис **не держит файл открытым**: на каждую запись открывает его в режиме append и закрывает. Поэтому после ротации новые записи сами попадают в новый файл, сигналы и `copytruncate` не нужны.

Новый файл создаётся директивой `create 0640 healthapp healthapp`. Logrotate принимает имена, а не числовые GID,
поэтому на хосте и существует пользователь `healthapp` с тем же UID/GID 10001, что и в контейнере (его создаёт `make deploy`).
Так владелец нового файла совпадает с пользователем контейнера, и запись в него продолжается.
Сжатие идёт с `delaycompress`: `.gz` появляется только после второй ротации.

Как проверял:

```bash
curl -s localhost:8080/health
sudo logrotate -f /etc/logrotate.d/healthapp
ls -l /var/log/healthapp/        # access.log (новый, владелец healthapp) и access.log.1
curl -s localhost:8080/health
sudo cat /var/log/healthapp/access.log     # там только новые строки
```

## 8. Зачем нужен каждый пункт

**Docker**
- _Версия базового образа, не latest_: сборка воспроизводима, образ не изменится сам при выходе новой версии.
- _Многостадийная сборка_: pip и кэш остаются на первой стадии, в финальный образ идут только установленные пакеты. Образ меньше и безопаснее.
- _Не root_: при взломе сервиса атакующий не получает root в контейнере. UID фиксирован (10001), потому что владелец файлов на диске определяется числом, а не именем: с одинаковым номером в контейнере и на хосте контейнер может писать в папку логов.
- _.dockerignore_: в образ не попадают `.git`, кэши, лишние файлы. Сборка быстрее, секреты не утекают.
- _Том для логов_: файлы контейнера исчезают вместе с ним; логи на хосте переживают перезапуск и доступны logrotate.
- _HEALTHCHECK_ (бонус): Docker видит, отвечает ли сервис, а не только жив ли процесс.

**systemd**
- `Requires=docker.service` и `After=docker.service`: `Requires` задаёт зависимость (нет Docker — нет службы), `After` задаёт порядок (стартовать после Docker). Это разные вещи, поэтому нужны обе.
- `Restart=always`, `RestartSec=5`: автоперезапуск с паузой, чтобы не было «бешеного» цикла.
- `ExecStartPre=-docker rm -f`: убирает остатки старого контейнера с тем же именем (`-` = игнорировать ошибку, если его нет). В журнале при каждом старте будет `No such container: healthapp`: это не ошибка, контейнер уже удалил `--rm`.
- `docker run --rm --init`: `--rm` не копит остановленные контейнеры; `--init` нужен, потому что Python как PID 1 игнорирует SIGTERM, и `docker stop` ждал бы 10 с до SIGKILL.
- `ExecStop=docker stop`: корректная остановка контейнера.
- `SuccessExitStatus=143`: при штатной остановке `docker run` возвращает 143 (128 + 15, SIGTERM). Без этой строки systemd считал бы остановку сбоем, и после `systemctl stop` статус был бы `failed`, а не `inactive (dead)`.
- `EnvironmentFile`: настройки вне unit-файла; тот же файл отдаётся контейнеру через `--env-file`.
- `--memory 128m`: контейнер не съест всю память сервера.
- `systemctl enable` (делает `make deploy`): автозапуск после перезагрузки.

## 9. Что не сделано / сделал бы иначе

- Не реализован `/metrics` (Prometheus), бонус.
- Проверку на чистой Ubuntu 22.04/24.04 не проводил. Проверено на Debian 13 и Linux Mint 22.3 (основан на Ubuntu 24.04), где сервис разворачивается по этому README без правок. Отличий в пакетах и systemd не ожидаю, но подтвердить на самой Ubuntu не могу.
- Образ собирается на самом сервере; в реальности лучше собирать в CI и тянуть из registry.
- Версия образа (`healthapp:1.0`) и путь `/var/log/healthapp` прописаны в нескольких местах (Makefile и unit-файл), при смене их нужно править везде. Лучше вынести в одну переменную.
- `make clean` останавливает службу и удаляет образ, но не удаляет файлы в `/etc`, пользователя `healthapp` и папку логов: их нужно убирать вручную.
- Запросы healthcheck попадают в access-лог и добавляют шум.
- Для production: часовой пояс из настроек, ограничение CPU, `--read-only` файловая система контейнера.
- IP клиента в логе — адрес docker-шлюза; для реального IP нужен `--network host` или прокси с `X-Forwarded-For`.
