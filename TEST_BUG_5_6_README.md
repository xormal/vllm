# Bug #5 и #6 - Тестирование исправлений

## Быстрый старт

```bash
# Запустить тест
python test_bug_5_and_6_fixes.py

# С другим хостом/портом
python test_bug_5_and_6_fixes.py --host 192.168.228.43 --port 8000

# С подробным выводом
python test_bug_5_and_6_fixes.py --verbose
```

## Что проверяет тест

### ✅ Bug #5: Формат response.tool_call.delta

**Проверяет**:
- ✓ `delta` является `dict`, не `str`
- ✓ `delta.content` существует
- ✓ `delta.content` является `list`
- ✓ `delta.content[0]` является `str`
- ✓ Возможность собрать полный JSON из delta chunks

**Ожидаемый формат**:
```json
{
  "type": "response.tool_call.delta",
  "delta": {
    "content": ["<JSON string chunk>"]
  }
}
```

### ✅ Bug #6: Стандартный OpenAI формат tools

**Проверяет**:
- ✓ Сервер принимает формат `{"type": "function", "function": {...}}`
- ✓ Нет ошибки валидации `Field required` для `FunctionTool.name`
- ✓ HTTP 200/201, не 400

**Ожидаемый формат**:
```json
{
  "tools": [
    {
      "type": "function",
      "function": {
        "name": "calculator",
        "description": "...",
        "parameters": {...}
      }
    }
  ]
}
```

## Exit codes

| Code | Значение |
|------|----------|
| 0 | ✅ Все тесты пройдены |
| 1 | ❌ Некоторые тесты провалились |
| 2 | 🔌 Ошибка подключения к серверу |

## Интерпретация результатов

### ✅ Bug #5 исправлен

```
Testing Bug #5: response.tool_call.delta format
------------------------------------------------------------
  ✓ Found 3 response.tool_call.delta events
  ✓ All delta events have correct format (dict with content array)
  ✓ Bug #5 appears to be FIXED ✓
  ✓ Reconstructed tool call: list_files
```

### ❌ Bug #5 НЕ исправлен

```
Testing Bug #5: response.tool_call.delta format
------------------------------------------------------------
  ✓ Found 3 response.tool_call.delta events
  ✗ Delta event 1 type
    Error: delta is str, expected dict. Bug #5 NOT FIXED!
  ✗ Delta format validation
    Error: Some delta events have incorrect format. Bug #5 NOT FIXED!
```

### ✅ Bug #6 исправлен

```
Testing Bug #6: Standard OpenAI tool format
------------------------------------------------------------
  ✓ Standard OpenAI tool format accepted
  ✓ Response structure valid
```

### ❌ Bug #6 НЕ исправлен

```
Testing Bug #6: Standard OpenAI tool format
------------------------------------------------------------
  ✗ Standard OpenAI tool format
    Error: Server rejected standard format. Bug #6 NOT FIXED.
    Error: Field required for FunctionTool.name
```

## Требования

```bash
# Установить зависимости
pip install requests
```

## Использование в CI/CD

```yaml
# GitHub Actions
- name: Test Bug Fixes
  run: |
    python test_bug_5_and_6_fixes.py --host $SERVER_HOST --port $SERVER_PORT
  env:
    SERVER_HOST: localhost
    SERVER_PORT: 8000
```

```bash
# Jenkins
sh 'python test_bug_5_and_6_fixes.py'
```

```bash
# Простой bash скрипт
#!/bin/bash
python test_bug_5_and_6_fixes.py
if [ $? -eq 0 ]; then
  echo "✅ Tests passed"
else
  echo "❌ Tests failed"
  exit 1
fi
```

## Troubleshooting

### Ошибка: Connection refused

**Проблема**: Сервер не запущен или недоступен
```
✗ Server health
  Error: Cannot connect to server
```

**Решение**:
```bash
# Проверьте, что сервер запущен
curl http://192.168.228.43:8000/health

# Или запустите сервер
python -m vllm.entrypoints.openai.api_server \
  --model openai/gpt-oss-120b \
  --port 8000
```

### Предупреждение: No tool_call.delta events found

**Проблема**: Модель не вызвала tools
```
⚠ response.tool_call.delta events
  Warning: No tool_call.delta events found. Model may not have called tools.
```

**Решение**:
- Это нормально, если модель решила не вызывать tools
- Попробуйте другой prompt, который явно требует tool calling
- Проверьте, что модель поддерживает tool calling

### Ошибка: Request timeout

**Проблема**: Сервер слишком долго отвечает

**Решение**:
```bash
# Увеличьте timeout в коде (строка 60)
timeout=120  # было 60

# Или используйте более быструю модель
```

## Примеры вывода

### Все исправления применены ✅

```
============================================================
Bug #5 and Bug #6 Fix Verification Test
============================================================
Server: http://192.168.228.43:8000/v1
Time: 2025-11-25 18:00:00

Testing server health
------------------------------------------------------------
  ✓ Server is healthy

Testing Bug #6: Standard OpenAI tool format
------------------------------------------------------------
  ✓ Standard OpenAI tool format accepted
  ✓ Response structure valid

Testing Bug #5: response.tool_call.delta format
------------------------------------------------------------
  ✓ Found 3 response.tool_call.delta events
  ✓ All delta events have correct format (dict with content array)
  ✓ Bug #5 appears to be FIXED ✓
  ✓ Reconstructed tool call: list_files

============================================================
Test Summary:
  Passed:   7
  Failed:   0
  Warnings: 0
============================================================

✓ All tests passed!
```

### Исправления НЕ применены ❌

```
============================================================
Bug #5 and Bug #6 Fix Verification Test
============================================================
Server: http://192.168.228.43:8000/v1
Time: 2025-11-25 18:00:00

Testing server health
------------------------------------------------------------
  ✓ Server is healthy

Testing Bug #6: Standard OpenAI tool format
------------------------------------------------------------
  ✗ Standard OpenAI tool format
    Error: Server rejected standard format. Bug #6 NOT FIXED.
    Error: [{'type': 'missing', 'loc': ('body', 'tools', 0, 'FunctionTool', 'name')...

Testing Bug #5: response.tool_call.delta format
------------------------------------------------------------
  ✓ Found 3 response.tool_call.delta events
  ✗ Delta event 1 type
    Error: delta is str, expected dict. Bug #5 NOT FIXED!
  ✗ Delta format validation
    Error: Some delta events have incorrect format. Bug #5 NOT FIXED!

============================================================
Test Summary:
  Passed:   2
  Failed:   3
  Warnings: 0
============================================================

Errors:
  • Standard OpenAI tool format: Server rejected standard format...
  • Delta event 1 type: delta is str, expected dict...
  • Delta format validation: Some delta events have incorrect format...

✗ Some tests failed.
```

## Ссылки

- **Bug #5 описание**: BUG_5_TOOL_CALL_DELTA_FORMAT.md
- **Bug #5 анализ логов**: BUG_5_ANALYSIS_FROM_CODEX_LOGS.md
- **Полный отчет**: BUG_5_AND_6_COMPLETE_REPORT.md
- **Compliance report**: COMPLIANCE_PLAN_IMPLEMENTATION_REPORT.md
