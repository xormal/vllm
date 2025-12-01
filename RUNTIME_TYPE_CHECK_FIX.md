# Исправление ошибки "Subscripted generics cannot be used with class and instance checks"

## Проблема

Ошибка HTTP 500: `"Subscripted generics cannot be used with class and instance checks"` возникала при попытке использовать standard OpenAI tool format в `/v1/responses` endpoint.

**Причина:** Python не позволяет использовать subscripted generic types (например, `list[SomeType]`, `dict[str, int]`) в runtime проверках типов (`isinstance()`, `issubclass()`). Pydantic при валидации полей может пытаться выполнять такие проверки.

## Исправления

### 1. `vllm/entrypoints/openai/protocol.py`

#### Добавлен `from __future__ import annotations`
```python
# Строка 6
from __future__ import annotations
```
**Эффект:** Все type annotations обрабатываются как строки и не вычисляются во время импорта, предотвращая ошибки с generic types.

#### Добавлены необходимые импорты
```python
# Строки 10-11
from collections.abc import Mapping
from enum import Enum

# Строка 22
from openai.types.chat.chat_completion_tool_param import ChatCompletionToolParam
```

#### Определен TypeAlias для ResponsesTool
```python
# Строка 369
ResponsesTool: TypeAlias = Tool | ChatCompletionToolParam | Mapping
```
**Важно:** Использован явный `TypeAlias` annotation.

#### Изменен тип поля `tools` в ResponsesRequest
```python
# Было (строка 408):
tools: list[ResponsesTool] = Field(default_factory=list)

# Стало (строка 410):
tools: list[Any] = Field(default_factory=list)
```
**Эффект:** Pydantic не пытается валидировать union type `ResponsesTool` во время runtime. Вместо этого валидация происходит в методе `_normalize_request_tools()`.

### 2. `vllm/entrypoints/openai/serving_responses.py`

#### Добавлен `from __future__ import annotations`
```python
# Строка 4
from __future__ import annotations
```

#### Изменен тип параметра в `_convert_tool_to_responses_tool`
```python
# Было (строка 1606):
def _convert_tool_to_responses_tool(
    tool: ResponsesTool,
) -> Tool:

# Стало (строка 1606):
def _convert_tool_to_responses_tool(
    tool: Any,
) -> Tool:
```
**Эффект:** Избегаем возможных проблем с type checking для union type.

## Как работает исправление

1. **Pydantic validation:** Поле `tools` теперь имеет тип `list[Any]`, поэтому Pydantic не пытается валидировать каждый элемент против сложного union type
2. **Manual normalization:** После того как Pydantic принимает запрос, метод `_normalize_request_tools()` конвертирует каждый tool в правильный формат
3. **Runtime safety:** `from __future__ import annotations` гарантирует, что все аннотации типов обрабатываются как строки во время импорта

## Проверка исправлений

```bash
# Синтаксическая проверка
python3 -m py_compile vllm/entrypoints/openai/protocol.py
python3 -m py_compile vllm/entrypoints/openai/serving_responses.py

# Функциональная проверка
python3 test_bug_5_and_6_verbose.py
```

## Что изменилось для API

### До исправления:
- ❌ Стандартный OpenAI формат tools отклонялся с HTTP 500
- ❌ Ошибка: "Subscripted generics cannot be used with class and instance checks"

### После исправления:
- ✅ Стандартный OpenAI формат `{"type": "function", "function": {...}}` принимается
- ✅ Автоматическая конвертация в внутренний формат vLLM
- ✅ Обратная совместимость с внутренним форматом vLLM

## Дополнительные изменения

В diff также видны другие улучшения Responses API (добавленные ранее):
- Bug #5 fix: `ResponseToolCallDeltaEvent` с правильным типом `delta: dict[str, list[str]]`
- Bug #6 fix: поддержка стандартного OpenAI tool format
- Дополнительные event types для streaming
- Error handling improvements

## Применение на сервере

После внесения изменений в код на сервере `192.168.228.43:8000`:

1. Скопируйте измененные файлы на сервер
2. Перезапустите vLLM процесс
3. Проверьте работоспособность с помощью test script

```bash
# На сервере
systemctl restart vllm  # или другая команда перезапуска
```
