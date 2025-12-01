# Bug Report #3: UnboundLocalError в SSE Streaming

## Дата: 2025-11-24 20:37:47
## Компонент: APIServer (pid=480331)
## Критичность: 🔴 CRITICAL - Streaming полностью не работает

---

## Проблема: UnboundLocalError - Неинициализированная переменная

**Файл:** `vllm/entrypoints/openai/api_server.py:753`

**Ошибка:**
```python
UnboundLocalError: cannot access local variable 'sequence_number' where it is not associated with a value
```

**Локация:**
```python
File "/mnt/d1/work/VLLM/vllm/vllm/entrypoints/openai/api_server.py", line 753, in _convert_stream_to_sse_events
    sequence_number += 1
    ^^^^^^^^^^^^^^^
```

---

## Причина

В функции `_convert_stream_to_sse_events()` переменная `sequence_number` используется в операции `+=` **ДО того**, как она была инициализирована в текущем scope.

**Проблемный паттерн:**
```python
async def _convert_stream_to_sse_events(...):
    try:
        # sequence_number НЕ инициализирована здесь

        async for event in generator:
            # ...
            sequence_number += 1  # ← ERROR! Переменная не существует
```

---

## Анализ кода

### Текущее состояние (в файлах):

**Файл на диске ИСПРАВЛЕН:**
```python
# api_server.py:698-732
async def _convert_stream_to_sse_events(...):
    try:
        sequence_validator = SSE_EVENT_VALIDATOR
        chunk_buffer = SSEChunkBuffer()
        sequence_number = 0  # ✅ ИНИЦИАЛИЗИРОВАНО на строке 708
        last_heartbeat = time.monotonic()

        async for event in generator:
            # ...
            sequence_number = seq + 1  # ✅ Присваивание, не +=
```

### Состояние на запущенном сервере (pid=480331):

**Сервер работает со СТАРОЙ версией кода:**
- Запущен до исправлений
- Содержит `sequence_number += 1` без инициализации
- Нужен ПЕРЕЗАПУСК

---

## Последствия

| Аспект | Статус |
|--------|--------|
| HTTP Response | ✅ 200 OK (отправляется) |
| SSE Stream | ❌ FAILS (прерывается) |
| Client получает данные | ❌ NO |
| Error в ASGI | ✅ ExceptionGroup |
| Все streaming requests | ❌ FAIL |

---

## Решение

### ✅ Код УЖЕ ИСПРАВЛЕН в файлах

Проверено:
- ✅ `sequence_number = 0` инициализирована на строке 708
- ✅ Используется `sequence_number = seq + 1` на строке 732 (не `+=`)

### ⚠️ ТРЕБУЕТСЯ: Перезапустить сервер

**Проблема:** Сервер (pid=480331) работает со старой версией кода.

**Команда перезапуска:**
```bash
# 1. Остановить текущий процесс
pkill -f "vllm.entrypoints.openai.api_server"
# или
kill -9 480331

# 2. Запустить с новым кодом
python -m vllm.entrypoints.openai.api_server \
    --model <YOUR_MODEL> \
    --host 0.0.0.0 \
    --port 8000
```

---

## Проверка исправления

После перезапуска проверить:

### 1. Логи должны быть чистыми:
```bash
# Не должно быть:
# ❌ UnboundLocalError: cannot access local variable 'sequence_number'
# ❌ ExceptionGroup: unhandled errors in a TaskGroup
```

### 2. Тестовый запрос:
```bash
curl -X POST http://localhost:8000/v1/responses \
  -H "Content-Type: application/json" \
  -H "Accept: text/event-stream" \
  -d '{
    "model": "your-model",
    "input": "Test streaming",
    "stream": true,
    "max_output_tokens": 50
  }'
```

**Ожидаемый результат:**
```
event: response.created
data: {"id":"resp_xxx",...}

event: response.output_text.delta
data: {"delta":{"content":[{"text":"..."}]},...}

...

data: [DONE]
```

### 3. Запустить compliance тесты:
```bash
pytest tests/compliance/test_openai_responses_api.py::test_streaming_responses_emits_done -v
```

---

## Дополнительная информация

### Другие warning'и в логах (не критичны):

```
UserWarning: To copy construct from a tensor, it is recommended to use sourceTensor.detach().clone()
```

Это предупреждения от xgrammar, не блокируют работу API. Относятся к tensor operations на GPU workers.

---

## Связь с предыдущими исправлениями

| Проблема | Файл | Статус |
|----------|------|--------|
| 1. NameError: `time` not defined | `api_server.py:10` | ✅ Fixed |
| 2. TypeError: unexpected `session` | `serving_responses.py:3236` | ✅ Fixed |
| 3. UnboundLocalError: `sequence_number` | `api_server.py:708` | ✅ Fixed в коде, ⚠️ нужен restart |

---

## Итог

**Статус:** ✅ Код исправлен корректно
**Действие:** ⚠️ **ПЕРЕЗАПУСТИТЬ СЕРВЕР** для применения исправлений

После перезапуска все streaming requests должны работать стабильно.
