# Гайд по подключению Codex к vLLM

Документ описывает, как заменить Ollama на собственный сервер [vLLM](https://vllm.ai), сохранив OpenAI‑совместимый чат и возможность tool calling. Вся цепочка остаётся локальной: Codex обращается к эндпоинту `/v1/chat/completions`, vLLM стримит токены/размышления, а Codex отправляет результаты инструментов обратно в ту же сессию.

---

## 1. Что потребуется

| Компонент | Версия / примечания |
| --------- | ------------------- |
| vLLM | 0.5.5 и новее (функции появились в 0.4.2, но 0.5.x устраняет баги OpenAI API). |
| GPU | NVIDIA с драйвером CUDA 12.x (для крошечных моделей можно CPU). |
| Python | 3.10+ и отдельный virtualenv для vLLM. |
| Codex | Текущий репозиторий (CLI/TUI/Telegram). |

Перед стартом убедитесь, что `nvcc --version` и `python3 --version` работают.

---

## 2. Установка vLLM

```bash
python3 -m venv ~/venvs/vllm
source ~/venvs/vllm/bin/activate
pip install --upgrade pip wheel
pip install "vllm>=0.5.5" \
            transformers accelerate \
            "torch>=2.3" --extra-index-url https://download.pytorch.org/whl/cu121
```

> **Совет:** закрепите версии для воспроизводимости:
> ```text
> vllm==0.5.5
> torch==2.3.1+cu121
> ```

---

## 3. Запуск OpenAI-совместимого сервера vLLM

`vllm.entrypoints.openai.api_server` уже умеет OpenAI API. Включите флаги функции, чтобы Codex видел tool calling.

```bash
MODEL="meta-llama/Meta-Llama-3.1-70B-Instruct"
PORT=8001

python -m vllm.entrypoints.openai.api_server \
    --model "$MODEL" \
    --host 0.0.0.0 \
    --port "$PORT" \
    --max-num-seqs 16 \
    --tensor-parallel-size 2 \
    --enable-auto-tool-call \
    --response-role assistant \
    --trust-remote-code \
    --gpu-memory-utilization 0.90
```

Главные параметры:

| Флаг | Зачем |
| ---- | ----- |
| `--enable-auto-tool-call` | Включает OpenAI function calling, модель возвращает `tool_calls`. |
| `--response-role assistant` | Соответствует ожидаемому `role="assistant"`. |
| `--host/--port` | По умолчанию `localhost:8000`; задайте явные значения для конфигов. |
| `--tensor-parallel-size`, `--max-model-len` | Подгон под оборудование (контекст >128k требует paged-attention). |

Авторизация опциональна: добавьте `--api-key secret`, а в Codex пропишите `Authorization: Bearer secret` (см. §4.2).

---

## 4. Настройка Codex

Codex видит vLLM как ещё одного OpenAI‑совместимого провайдера. Добавьте запись в `~/.codex/config.toml`.

### 4.1 Провайдер

```toml
custom_model_provider = "vllm"
custom_model = "llama-3.1-tool"

[model_providers.vllm]
name = "Local vLLM"
base_url = "http://127.0.0.1:8001/v1"
wire_api = "chat"
request_max_retries = 0
stream_max_retries = 1

[model_providers.vllm.model_options]
temperature = 0.2
top_p = 0.9
max_output_tokens = 2048

#[model_providers.vllm.http_headers]
#Authorization = "Bearer secret"    # если в vLLM включён --api-key
```

### 4.2 Фичи

```toml
[features]
streamable_shell = true
web_search_request = true   # если нужны MCP с веб-поиском
```

`custom_model` должен совпадать с названием в `--model`. Пути Hugging Face указывайте полностью (`meta-llama/...'`).

---

## 5. Проверка tool calling

1. Запустите vLLM и дождитесь `Uvicorn running on http://0.0.0.0:8001`.
2. В Codex (CLI/TUI/Telegram) попросите действие, требующее shell, напр. “Создай файл hello.txt со словом hi”.
3. Ожидаемое поведение:
   - Codex отправляет запрос с `tools=[...]`.
   - vLLM отвечает `tool_calls` (видно в `tool log` CLI или WARN в Telegram).
   - Codex выполняет инструмент, стримит вывод и шлёт `tool_results`.

Если `tool_calls` нет:

| Симптом | Что проверить |
| ------- | ------------- |
| Модель игнорирует инструменты | Нужен инструкционный чекпойнт с поддержкой функций (Llama 3.1 Instruct и т.п.). |
| vLLM пишет “Tool calling disabled” | Проверьте аргументы запуска и версию ≥0.5.2. |
| 404/401 в Codex | Совпадает ли `base_url` c `http://HOST:PORT/v1` и заголовок `Authorization`. |

---

## 6. Варианты развёртывания

1. **Docker compose.** Пробросьте порт (`8001:8001`), в конфиге укажите IP контейнера.
2. **Reverse proxy.** Nginx/Caddy завершают TLS, проксируют `/v1`; в `base_url` используйте публичный https‑адрес.
3. **Авторизация.** Либо `--api-key`, либо защита на прокси. Codex умеет задавать заголовки в `[model_providers.NAME.http_headers]`.

---

## 7. Распространённые вопросы

| Проблема | Решение |
| -------- | ------- |
| `501 Not Implemented` | Вы попали на `/v1/completions`. Должен быть `/v1/chat/completions` и `wire_api="chat"`. |
| `tool_calls` есть, но Codex их не использует | Убедитесь, что профили не выключили `streamable_shell`, а инструкции не переопределяют `tool_choice`. |
| Codex слишком часто просит одобрения | Настройте `approval_policy`/`sandbox_mode` (см. `docs/config.md`). |
| Ошибка OOM на GPU | Уменьшите `--max-model-len`, `--gpu-memory-utilization` или выберите меньшую модель. |

---

## 8. Дальше больше

- **Производительность:** подберите `--max-num-seqs` и `--max-num-batched-tokens`, чтобы обслуживать несколько turn’ов.
- **Логи:** vLLM поддерживает `--log-dir`, а Codex — `suppress_event_logs` и `[env] RUST_LOG`.
- **Несколько моделей:** объявите несколько провайдеров (`vllm-70b`, `vllm-8b`) и переключайтесь через `/model` или `--model`.

Настроив связку, Codex воспринимает vLLM как OpenAI: доступны tool calling, reasoning stream и любой MCP-набор — только теперь всё работает на вашем железе.

