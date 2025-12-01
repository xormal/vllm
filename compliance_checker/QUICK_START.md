# Quick Start Guide

## Быстрый запуск системы проверки соответствия

### 1. Установка зависимостей

```bash
cd compliance_checker
pip install -r requirements.txt
```

### 2. Настройка сервера

Отредактируйте `config.yaml`, если нужно изменить адрес сервера:

```yaml
server:
  base_url: "http://192.168.228.43:8000"  # ← Ваш сервер vLLM
```

### 3. Запуск проверки

```bash
# Полная проверка
python check_compliance.py

# Только эндпоинты
python check_compliance.py --endpoints-only

# Только стриминг
python check_compliance.py --streaming-only

# Только параметры
python check_compliance.py --parameters-only

# С подробным логированием
python check_compliance.py --verbose

# Пользовательская конфигурация
python check_compliance.py --config my_server.yaml
```

### 4. Просмотр отчетов

После выполнения проверки отчеты сохраняются в `compliance_reports/`:

- **JSON**: `compliance_report_YYYYMMDD_HHMMSS.json` - машиночитаемый формат
- **Markdown**: `compliance_report_YYYY-MM-DD.md` - для документации
- **HTML**: `compliance_report_YYYY-MM-DD.html` - откройте в браузере

### 5. Коды возврата

- **0** - проверка пройдена (compliance >= threshold)
- **1** - проверка провалена (compliance < threshold)
- **2** - критические ошибки
- **3** - сервер недоступен
- **4** - ошибка конфигурации

### 6. Интеграция в CI/CD

#### GitHub Actions

```yaml
- name: Check API Compliance
  run: |
    cd compliance_checker
    pip install -r requirements.txt
    python check_compliance.py --config ci.yaml
  continue-on-error: true
```

#### GitLab CI

```yaml
compliance_check:
  script:
    - cd compliance_checker
    - pip install -r requirements.txt
    - python check_compliance.py
  allow_failure: true
```

### 7. Примеры использования

#### Проверка перед деплоем

```bash
# Проверить критические эндпоинты
python check_compliance.py --critical-only

# Если провалено - не деплоить
if [ $? -ne 0 ]; then
    echo "Compliance check failed!"
    exit 1
fi
```

#### Ежедневная проверка

```bash
# Cron job: каждый день в 9:00
0 9 * * * cd /path/to/compliance_checker && python check_compliance.py --format html
```

#### Проверка после изменений

```bash
# После git commit
git diff --name-only | grep -q "entrypoints/openai" && python compliance_checker/check_compliance.py
```

### 8. Troubleshooting

#### Сервер недоступен

```bash
# Проверить доступность
curl http://192.168.228.43:8000/health

# Проверить модели
curl http://192.168.228.43:8000/v1/models
```

#### SSL ошибки

В `config.yaml` установите:

```yaml
server:
  verify_ssl: false
```

#### Timeout

Увеличьте таймаут в `config.yaml`:

```yaml
server:
  timeout: 60
```

#### Модель недоступна

Измените тестовую модель:

```yaml
testing:
  test_model: "your-model-name"
```

### 9. Настройка порогов

В `config.yaml` установите желаемые пороги:

```yaml
compliance:
  thresholds:
    overall: 70    # Общий процент
    endpoints: 60  # Эндпоинты
    events: 60     # События стриминга
```

### 10. Форматы отчетов

```bash
# Только JSON
python check_compliance.py --format json

# JSON + Markdown
python check_compliance.py --format json --format markdown

# Все форматы
python check_compliance.py --format json --format markdown --format html
```

## Структура отчета

### Console Output (Rich)

```
OpenAI Responses API Compliance Checker
Version: 1.0
Config: config.yaml

✓ Server is reachable

═══ Endpoint Checks ═══
✅ POST /v1/responses passed
✅ GET /v1/responses/{id} passed
...

═══ Compliance Summary ═══

┏━━━━━━━━━━━┳━━━━━━━┳━━━━━━━┳━━━━━━━┳━━━━━━━━━━━┓
┃ Category  ┃ Total ┃ Passed┃ Failed┃ Pass Rate ┃
┡━━━━━━━━━━━╇━━━━━━━╇━━━━━━━╇━━━━━━━╇━━━━━━━━━━━┩
│ Endpoints │     8 │     6 │     2 │     75.0% │
│ Streaming │     3 │     3 │     0 │    100.0% │
│ Parameters│    26 │    20 │     6 │     76.9% │
└───────────┴───────┴───────┴───────┴───────────┘

Overall Compliance Score: 74.0%
Spec Mapping Score: 74%

⚠ GOOD COMPLIANCE
```

### HTML Report

Профессиональный отчет с:
- 📊 Прогресс-бары
- 🎨 Цветовые индикаторы
- 📋 Таблицы результатов
- 💡 Рекомендации по улучшению
- 📈 Детальная статистика

### JSON Report

Полные данные для автоматической обработки:

```json
{
  "timestamp": "2025-11-24T23:51:42",
  "server_url": "http://192.168.228.43:8000",
  "checks": {
    "endpoints": {
      "total": 8,
      "passed": 6,
      "failed": 2,
      "pass_rate": 75.0,
      "results": {...}
    },
    "streaming": {...},
    "parameters": {...}
  }
}
```

## Что проверяется

### ✅ Эндпоинты (Endpoints)

- POST /v1/responses - создание ответа
- GET /v1/responses/{id} - получение ответа
- POST /v1/responses/{id}/cancel - отмена
- GET /v1/models - список моделей
- И другие...

### ✅ Стриминг (Streaming)

- Последовательность событий
- Структура событий
- Обязательные поля
- Формат delta (строка, не объект!)
- Reasoning события

### ✅ Параметры (Parameters)

- Типы данных
- Обязательные параметры
- Валидация значений
- Применение параметров в ответах
- Test values из спецификации

## Следующие шаги

1. **Запустите первую проверку**: `python check_compliance.py`
2. **Просмотрите HTML отчет**: Откройте `compliance_reports/compliance_report_*.html`
3. **Проанализируйте провалы**: Проверьте секции с failed
4. **Исправьте код**: Внесите изменения в vLLM
5. **Запустите повторно**: Проверьте улучшения

## Полезные команды

```bash
# Проверка здоровья сервера
python -c "from utils.api_client import APIClient; c = APIClient('http://192.168.228.43:8000'); print(c.check_health())"

# Быстрая проверка только критического
python check_compliance.py --critical-only --fail-fast

# Сохранить только JSON для CI
python check_compliance.py --format json --output /tmp/compliance

# Verbose режим для отладки
python check_compliance.py --verbose 2>&1 | tee compliance.log
```

## Контакты и поддержка

При возникновении проблем:
1. Проверьте `logs/compliance.log`
2. Запустите с `--verbose` флагом
3. Проверьте доступность сервера
4. Проверьте формат конфигурации

Удачи с проверкой соответствия! 🚀
