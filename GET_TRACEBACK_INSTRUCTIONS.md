# Инструкция: Получение полного traceback ошибки

## Что было сделано

Добавлено детальное логирование исключений в 3 местах:

1. **api_server.py:952** - Exception в create_responses handler
2. **api_server.py:2525** - RequestValidationError (Pydantic ошибки)
3. **api_server.py:2549** - Все необработанные исключения

Теперь **полный traceback** будет выводиться в логи при любой ошибке.

---

## Шаги на сервере

### 1. Скопировать обновленный файл

```bash
# На вашей локальной машине (если нужно):
scp /Users/a0/Documents/py/VLLM/vllm/vllm/entrypoints/openai/api_server.py \
    alex@192.168.228.43:/mnt/d1/work/VLLM/vllm/vllm/entrypoints/openai/
```

Или если файлы уже синхронизированы через git/rsync - пропустите этот шаг.

### 2. Очистить Python cache (КРИТИЧЕСКИ ВАЖНО!)

```bash
ssh alex@192.168.228.43

cd /mnt/d1/work/VLLM/vllm

# Удалить все .pyc файлы
find . -type f -name "*.pyc" -delete

# Удалить все __pycache__ директории
find . -type d -name "__pycache__" -exec rm -rf {} + 2>/dev/null || true

echo "✓ Python cache cleared"
```

### 3. Перезапустить vLLM

```bash
# Найти процесс vLLM
ps aux | grep vllm | grep -v grep

# Вариант А: Если systemd
sudo systemctl restart vllm

# Вариант Б: Если процесс в терминале - убить и запустить заново
kill -9 <PID>
# затем запустить вашу команду запуска vLLM

# Вариант В: Если в tmux/screen
tmux attach  # или screen -r
# Ctrl+C чтобы остановить
# Запустить заново
```

### 4. Сделать тестовый запрос

```bash
# В НОВОМ терминале:
python3 test_bug_5_and_6_verbose.py
```

### 5. НЕМЕДЛЕННО проверить логи

**Сразу после запроса** выполните одну из команд:

#### Вариант А: Если vLLM запущен в терминале
Просто посмотрите вывод в терминале - там будет полный traceback.

#### Вариант Б: Если через systemd
```bash
journalctl -u vllm -n 500 --no-pager | grep -B 5 -A 50 "Traceback"
```

#### Вариант В: Если логи в файле
```bash
tail -n 1000 /var/log/vllm/*.log | grep -B 5 -A 50 "Traceback"
```

#### Вариант Г: Если не знаете где логи
```bash
# Найти процесс
PID=$(ps aux | grep vllm | grep -v grep | awk '{print $2}' | head -1)

# Посмотреть куда направлены stdout/stderr
ls -la /proc/$PID/fd/1 /proc/$PID/fd/2

# Следить за логами в реальном времени
tail -f /proc/$PID/fd/1 &  # stdout
tail -f /proc/$PID/fd/2 &  # stderr

# Сделать запрос и увидеть traceback
```

---

## Что искать в логах

Ищите блок, который начинается с:

```
ERROR:root:Exception in create_responses handler:
Traceback (most recent call last):
  File "...", line XXX, in create_responses
    ...
  File "...", line YYY, in ...
    ...
TypeError: Subscripted generics cannot be used with class and instance checks
```

**ИЛИ:**

```
ERROR:root:Unhandled exception occurred:
Traceback (most recent call last):
  File "...", line XXX, in ...
    ...
TypeError: Subscripted generics cannot be used with class and instance checks
```

**ИЛИ:**

```
ERROR:root:RequestValidationError occurred:
Traceback (most recent call last):
  File "...", line XXX, in ...
    ...
TypeError: Subscripted generics cannot be used with class and instance checks
```

---

## Что отправить обратно

**Пожалуйста, скопируйте ПОЛНЫЙ traceback**, включая:

1. **Все строки начиная с "Traceback"**
2. **Все строки "File ..." с номерами строк**
3. **Финальную строку с типом ошибки и сообщением**

Пример того, что нужно скопировать целиком:

```
ERROR:root:Exception in create_responses handler:
Traceback (most recent call last):
  File "/mnt/d1/work/VLLM/vllm/vllm/entrypoints/openai/api_server.py", line 949, in create_responses
    generator = await handler.create_responses(request, raw_request)
  File "/mnt/d1/work/VLLM/vllm/vllm/entrypoints/openai/serving_responses.py", line 1342, in create_responses
    self._normalize_request_tools(request)
  File "/mnt/d1/work/VLLM/vllm/vllm/entrypoints/openai/serving_responses.py", line 1600, in _normalize_request_tools
    normalized.append(self._convert_tool_to_responses_tool(tool))
  File "/mnt/d1/work/VLLM/vllm/vllm/entrypoints/openai/protocol.py", line 1234, in some_function
    if isinstance(obj, list[SomeType]):
TypeError: Subscripted generics cannot be used with class and instance checks
```

С этим traceback'ом я смогу найти **точную строку кода** с проблемой и исправить ее!

---

## Быстрая команда (все в одном)

```bash
ssh alex@192.168.228.43 "
cd /mnt/d1/work/VLLM/vllm && \
find . -name '*.pyc' -delete && \
find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true && \
sudo systemctl restart vllm && \
sleep 5 && \
journalctl -u vllm -n 200 --no-pager | tail -50
"
```

Затем в другом терминале:
```bash
python3 test_bug_5_and_6_verbose.py
```

И сразу после этого:
```bash
ssh alex@192.168.228.43 "journalctl -u vllm -n 500 --no-pager | grep -B 5 -A 50 Traceback"
```

---

## Что если traceback все еще не появляется?

Тогда ошибка происходит **ДО** того, как запрос попадает в наш код (например, в Pydantic парсинге FastAPI). В таком случае:

```bash
# Включить DEBUG уровень логирования
export VLLM_LOGGING_LEVEL=DEBUG
export PYTHONFAULTHANDLER=1

# Перезапустить vLLM с этими переменными окружения
```

Или добавьте в команду запуска vLLM:
```bash
python -X faulthandler -u -m vllm.entrypoints.openai.api_server ...
```
