# SSE (Server-Sent Events) рекомендации

Чтобы поток Responses API был устойчивым:

1. Всегда отправляйте заголовок `Accept: text/event-stream` при `stream=true`.
2. SSE события приходят в формате:

   ```
   event: <тип события>
   data: {...json...}

   ```

3. Сеттеры `response.output_text.delta`, `response.tool_call.delta` и `response.error`
   могут чередоваться; `response.completed` завершает поток, а финальный `data: [DONE]`
   сигнализирует конец SSE. Мы также отправляем
   `Retry-After` при 429.
4. Клиент должен игнорировать повреждённые строки (сервер заменяет невалидные chunk’и).
5. Сервер валидирует каждый SSE event: если `type` не соответствует `response.*`
   или последовательный номер некорректен, поток завершится `response.error` с
   типом `stream_validation_error`.
6. Для снижения накладных расходов события буферизуются пачками (~16 КБ) перед
   отправкой. При простое дольше `responses_ping_interval_seconds` сервер шлёт
   `response.ping` (heartbeat), чтобы прокси не закрывали соединение. Пинги
   можно отключить (`--responses-ping-interval-seconds 0`).
