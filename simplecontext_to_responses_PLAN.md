# simplecontext_to_responses_PLAN.md

План завершён: код уже поддерживает Responses для моделей без Harmony parser. Разделение контуров зашито в `OpenAIServingResponses`, и отдельный флаг `--simple-to-responses` не нужен. Ниже зафиксирован текущий статус и что важно учитывать при будущих правках.

## Что уже работает
- `SimpleContext` живёт в `vllm/entrypoints/context.py` и используется для негpт_oss моделей; он хранит последний `RequestOutput` и считает prompt/output/cached токены (см. методы `append_output` и поля счётчиков).
- В `vllm/entrypoints/openai/serving_responses.py` контекст выбирается по `self.use_harmony` (`model_type == "gpt_oss"`): для gpt-oss создаются `HarmonyContext`/`StreamingHarmonyContext`, иначе — `SimpleContext` (см. `create_responses`, блок вокруг построения генератора).
- Стриминг разведен: Harmony идёт через `_process_harmony_streaming_events`, простой путь — через `_process_simple_streaming_events` (оба в `serving_responses.py`). Они отдают SSE (`queued/created/in_progress`, дельты reasoning/text, финализацию, rate_limits.updated) и уважают `compatibility_mode` для Codex.
- Финальные ответы для негpт_oss собираются в `_make_response_output_items`, где `_parse_tool_calls_from_content` вытаскивает inline tool calls из текста. Стриминговый tool path и `/v1/responses/{id}/tool_outputs` остаются только в Harmony-контуре (`_await_tool_outputs`/`_resume_session_after_tool_call` проверяют тип контекста).
- Хранилище Responses (`ResponseSessionManager` + `ResponseStreamSession` в `serving_responses.py`) общее: учитывает оба контекста, совместимость с `previous_response_id`, ожидание tool outputs для Harmony и метрики байтов для SSE очереди.

## Памятка по тестам/регрессиям
- Смоук: `pytest tests/entrypoints/openai/test_serving_responses.py`.
- Совместимость/Codex: `python test_codex_compatible.py --host <host>`.
- Для Harmony/tool-пути дополнительно гонять `tests/entrypoints/openai/test_responses_function_call_parsing.py` и e2e по Responses (stream + tool_outputs), чтобы не поломать ожидания SSE.
