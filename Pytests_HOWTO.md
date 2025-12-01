# Pytests HOWTO

Минимальные инструкции по запуску проверок перед отправкой изменений. Тесты
выполняются на сервере, но здесь указаны команды/мишени, которые должны
проходить.

## Responses API

- **Streaming & session unit tests**

  ```bash
  python3 -m pytest tests/entrypoints/openai/test_serving_responses.py
  ```

  Покрывает `response.tool_call.delta`, `ResponseSessionManager`, ожидание
  `tool_outputs`, лимиты `max_stream_event_bytes`/`responses_stream_buffer_max_bytes`
  и завершение стримингов после disconnect.

- **Интеграционные проверки (из CLI/watchdog):**
  1. Запустите OpenAI-совместимый фронтенд (`python -m vllm.entrypoints.openai.api_server ...`).
  2. Отправьте стриминговый `/v1/responses` запрос с `tools=[...]` и
     подтвердите, что в SSE идут события `response.tool_call.delta`.
  3. Передайте результаты через
     `curl -X POST /v1/responses/{id}/tool_outputs -d '{"tool_call_id": "...", ...}'`
     и убедитесь, что поток продолжился до `response.completed`.

- **API helper tests (headers, SSE errors)**

  ```bash
  python3 -m pytest tests/entrypoints/openai/test_api_server_helpers.py
  ```

  Проверяет SSE декодер и то, что `_convert_stream_to_sse_events` вызывает
  очистку сессии при отмене.

- **Edge cases (rate limit, store, includes)**

  ```bash
  python3 -m pytest tests/entrypoints/openai/test_serving_responses.py::test_store_response_ttl_eviction
  python3 -m pytest tests/entrypoints/openai/test_serving_responses.py::test_validate_include_computer_call_flag
  python3 -m pytest tests/entrypoints/openai/test_serving_responses.py::test_compat_mode_rejects_extra_fields
  ```

## Compliance Suite

End-to-end tests for OpenAI compatibility (requires a running server).

1. Export environment variables:

   ```bash
   export VLLM_COMPLIANCE_BASE_URL="http://localhost:8000/v1"
   export VLLM_COMPLIANCE_MODEL="gpt-4o-mini"
   export VLLM_COMPLIANCE_API_KEY="YOUR_API_KEY"     # optional
   export VLLM_COMPLIANCE_ORG="example-org"           # optional
   ```

2. Run the suite:

   ```bash
   python3 -m pytest tests/compliance/test_openai_responses_api.py
   ```

The tests are marked `@pytest.mark.compliance` and will be skipped automatically
if the required environment variables are not set.

## Общие заметки

- Все команды запускаются от корня репозитория.
- Используйте `python3` (версия 3.12+) и заранее установите dev-зависимости
  (`pip install -r requirements/dev.txt`) на сервере тестирования.
