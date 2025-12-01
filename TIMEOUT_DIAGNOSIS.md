# Диагностика: Timeout при стриминге

## Проблема

Тест `test_codex_compatible.py` зависает после первого события `response.created`:

```
[Event #2] response.created (seq=1)
  Response ID: resp_c3526575974e4d8d801d7844031e4833

❌ UNEXPECTED ERROR: TimeoutError: timed out
```

Сервер:
- ✅ Отвечает на health check
- ✅ Принимает запрос (HTTP 200)
- ✅ Отправляет первое событие `response.created`
- ❌ Потом зависает - не отправляет больше событий

---

## Возможные причины

### 1. Модель зависает при генерации

**Симптомы**:
- Первое событие приходит быстро
- Потом тишина
- Нет ошибок в логах

**Причины**:
- Модель ждет GPU
- OOM (out of memory)
- Модель зациклилась
- Проблема с reasoning (модель пытается думать бесконечно)

**Проверка**:
```bash
# Проверить использование GPU
ssh alex@192.168.228.43 "nvidia-smi"

# Проверить логи модели
ssh alex@192.168.228.43 "journalctl -u vllm -n 200 --no-pager | tail -50"
```

### 2. Сервер ждет tool outputs

**Симптомы**:
- Сервер отправил tool call
- Ждет POST /tool_outputs
- Клиент не видит tool call (timeout раньше)

**Причины**:
- SSE события не доходят до клиента
- Буферизация на уровне сервера/прокси
- Сервер не отправляет heartbeat (ping)

**Проверка**:
```bash
# Проверить логи на наличие tool calls
ssh alex@192.168.228.43 "journalctl -u vllm -n 500 --no-pager | grep -i 'tool\|function'"
```

### 3. Буферизация SSE

**Симптомы**:
- События генерируются на сервере
- Но не доходят до клиента
- Приходят все сразу при disconnect

**Причины**:
- Reverse proxy буферизует
- Python буферизация
- uvicorn буферизация

**Проверка**:
```python
# Добавить flush в SSE generator
yield f"data: {json.dumps(event)}\n\n"
# Добавить:
sys.stdout.flush()  # или response.flush()
```

### 4. Compatibility mode блокирует события

**Симптомы**:
- Только первое событие
- Остальные фильтруются

**Причины**:
- Слишком агрессивная фильтрация в compatibility_mode
- Блокируются нужные события

**Проверка**:
```bash
# Попробовать БЕЗ compatibility mode
# Добавить в команду запуска:
--no-responses-compatibility-mode
```

---

## Шаги диагностики

### Шаг 1: Простой тест (без tools, без reasoning)

```bash
python3 test_simple_stream.py
```

**Ожидаемый результат**:
- Несколько событий `response.output_text.delta`
- Финальное `response.completed`

**Если НЕ работает**: Проблема в базовой генерации модели

**Если работает**: Проблема в tools или reasoning

### Шаг 2: Проверить логи сервера

```bash
./check_server_logs.sh
```

**Что искать**:
- Ошибки генерации
- OOM errors
- GPU errors
- Зависшие запросы
- Tool call события

### Шаг 3: Тест с tools но БЕЗ reasoning

Модифицировать `test_codex_compatible.py`:
```python
# Убрать reasoning
payload = create_codex_request(
    model=model,
    user_message="List all Python files in the current directory using ls command",
    reasoning_effort=None,  # ← УБРАТЬ reasoning
    conversation_id=conversation_id
)
```

### Шаг 4: Проверить heartbeat/ping

Сервер должен отправлять ping каждые 15 секунд (настройка по умолчанию).

```bash
# Запустить тест и ждать > 15 секунд
python3 test_codex_compatible.py

# Должны появиться :ping события или пустые data: {}
```

### Шаг 5: Увеличить timeout

Модифицировать test_codex_compatible.py:
```python
# Строка 457
with urllib.request.urlopen(req, timeout=120) as response:  # ← Было 60
```

---

## Быстрые фиксы

### Fix 1: Отключить reasoning

Если проблема в reasoning генерации:

```python
# В test_codex_compatible.py убрать:
reasoning_effort=None
# и
payload.pop("reasoning", None)
payload.pop("include", None)
```

### Fix 2: Отключить compatibility mode

Если compatibility_mode блокирует события:

```bash
# Перезапустить сервер с флагом:
--no-responses-compatibility-mode
```

### Fix 3: Добавить debug логирование

В api_server.py в SSE generator:
```python
async def sse_generator(...):
    for event in generator:
        logger.info(f"SSE: Sending event type={event.type}")  # ← Добавить
        yield f"data: {json.dumps(event_dict)}\n\n"
```

### Fix 4: Проверить model max_tokens

Возможно модель не может генерировать из-за лимитов:

```bash
# Проверить конфиг модели
ssh alex@192.168.228.43 "cat /mnt/d1/work/VLLM/vllm/vllm/config.py | grep max"
```

---

## Команды для проверки

### Проверка 1: Модель жива?

```bash
ssh alex@192.168.228.43 "ps aux | grep vllm | grep -v grep"
```

### Проверка 2: GPU используется?

```bash
ssh alex@192.168.228.43 "nvidia-smi"
```

### Проверка 3: Есть ли активные requests?

```bash
ssh alex@192.168.228.43 "journalctl -u vllm -n 50 --no-pager | grep -i 'request\|resp_'"
```

### Проверка 4: Логи за последние 2 минуты

```bash
ssh alex@192.168.228.43 "journalctl -u vllm --since '2 minutes ago' --no-pager"
```

---

## Следующие шаги

1. **Запустить test_simple_stream.py** - проверить базовую генерацию
2. **Проверить логи сервера** - найти ошибки
3. **Попробовать без reasoning** - исключить эту причину
4. **Увеличить timeout до 120s** - дать модели время
5. **Проверить GPU/память** - убедиться что ресурсы есть

---

## Ожидаемый вывод успешного теста

```
[Event #1] response.created
[Event #2] response.reasoning_text.delta: "User wants..."
[Event #3] response.reasoning_text.delta: "to list Python..."
...
[Event #20] response.output_item.added - function_call
  Name: shell
  Call ID: call_xxxxx
  Arguments: ''
[Event #30] response.function_call_arguments.delta: "{"
[Event #31] response.function_call_arguments.delta: "command"
...
[Event #50] response.output_item.done - function_call
  Call ID: call_xxxxx
  Arguments: {"command":["ls","*.py"]}
[Event #51] response.completed
```

Если не видим событий после #2, значит проблема в генерации.
