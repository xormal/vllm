## Цели
1) Код должен импортироваться и работать с transformers==4.57.x.
2) Код должен импортироваться и работать с transformers==5.0.0.dev0.
3) Не ломать существующее поведение и API vLLM.
4) Обеспечить безопасные fallback’ы там, где API/модули изменились.

---

# Общие правила патчей

## 1) Safe-import pattern для transformers импортов
Во всех местах прямых импортов из transformers использовать:

```python
try:
    from transformers.<module> import <name>
except ImportError:
    # transformers v5 мог переместить/удалить модуль
    <name> = None

Добавить комментарии вида:

# COMPAT: transformers v4/v5 safe import


⸻

2) Attribute-safe access (feature detect)

Ни в одном месте нельзя вызывать метод/атрибут напрямую без проверки, т.к. в v5 структура tokenizers и моделей могла измениться:

Всегда так:

if hasattr(obj, "some_attr"):
    val = obj.some_attr
else:
    val = fallback_value

3) Unified tokenizer fallback helper

Создать helper:

def get_all_special_tokens_extended(tokenizer):
    if hasattr(tokenizer, "all_special_tokens_extended"):
        return tokenizer.all_special_tokens_extended
    elif hasattr(tokenizer, "all_special_tokens"):
        return tuple(tokenizer.all_special_tokens)
    else:
        return ()

и использовать везде, где ранее было tokenizer.all_special_tokens_extended.

⸻

Конкретные патчи по модулям

A) configuration_utils / internal config imports

Везде где используется:

from transformers.configuration_utils import ...

заменить на:

try:
    from transformers.configuration_utils import ALLOWED_LAYER_TYPES, PretrainedConfig
except ImportError:
    # transformers v5 removed/refactored these
    ALLOWED_LAYER_TYPES = None
    from transformers import PretrainedConfig  # fallback

Патчировать:
	•	vllm/config/model.py
	•	vllm/transformers_utils/config.py

⸻

B) modeling_utils / modeling_rope_utils

В местах:

from transformers.modeling_utils import ... 
from transformers.modeling_rope_utils import ...

заменить на safe imports:

try:
    from transformers.modeling_utils import ...
except ImportError:
    ...
try:
    from transformers.modeling_rope_utils import ...
except ImportError:
    ...

и использовать if <name> is not None: guard’ы перед использованием.

Патчировать:
	•	vllm/model_executor/models/*
	•	vllm/transformers_utils/configs/*.py

⸻

C) Tokenizer API changes

В transformers v5 токенизация унифицирована, старые поля могут отсутствовать.
Заменить все прямые обращения:

tokenizer.all_special_tokens_extended

на:

specials = get_all_special_tokens_extended(tokenizer)

Где нет helper’а — добавить его из общего раздела.

Файлы:
	•	vllm/transformers_utils/tokenizer.py
	•	vllm/transformers_utils/detokenizer_utils.py
	•	async utils

⸻

D) AutoConfig / AutoModel / from_pretrained kwargs

В transformers v5 изменены параметры аутентификации для .from_pretrained.
Патч:

orig_kwargs = {...}
kwargs = {}
if "use_auth_token" in orig_kwargs:
    kwargs["token"] = orig_kwargs.pop("use_auth_token")
cfg = AutoConfig.from_pretrained(model_name, **kwargs, **orig_kwargs)

и то же для AutoModel loader’ов.

Патчировать:
	•	vllm/model_executor/model_loader/*
	•	vllm/transformers_utils/config.py

⸻

E) Image / Feature Extractor API

В v5 AutoFeatureExtractor был заменён на AutoImageProcessor.
Патчировать:

try:
    from transformers import AutoImageProcessor
except ImportError:
    AutoImageProcessor = None
try:
    from transformers import AutoFeatureExtractor
except ImportError:
    AutoFeatureExtractor = None  # fallback

и в моделях использовать:

processor_cls = AutoImageProcessor or AutoFeatureExtractor
if processor_cls is None:
    raise RuntimeError("Image processor unavailable")

Файлы:
	•	vllm/model_executor/models/* (vision/multimodal)

⸻

F) Chat template util safe import

v5 мог удалить/переместить:

from transformers.utils.chat_template_utils import ...

Патч:

try:
    from transformers.utils.chat_template_utils import ...
except ImportError:
    ...

Файлы:
	•	vllm/entrypoints/chat_utils.py

⸻

G) dynamic_module_utils / SAFE_WEIGHTS_INDEX_NAME

Проверить и обернуть:

try:
    from transformers import dynamic_module_utils
except ImportError:
    dynamic_module_utils = None

и то же для SAFE_WEIGHTS_INDEX_NAME.

⸻

H) Vision / video / multimodal utils

Где используются:

from transformers.image_processing_utils_fast import ...
from transformers.video_processing_utils import ...

заменить на safe imports с fallback:

try:
    from transformers import image_processing_utils_fast
except ImportError:
    image_processing_utils_fast = None
try:
    from transformers import video_processing_utils
except ImportError:
    video_processing_utils = None

и guard’ы перед использованием.

⸻

Smoke-тесты (после патча)

1) transformers import sweep

python3 - << 'PY'
import importlib
mods = [
    "transformers.configuration_utils",
    "transformers.modeling_utils",
    "transformers.modeling_rope_utils",
    "transformers.tokenization_utils_base",
]
for m in mods:
    try:
        importlib.import_module(m)
        print("OK", m)
    except Exception as e:
        print("FAIL", m, e)
PY

2) Tokenizer & Config load

python3 - << 'PY'
from vllm.transformers_utils.tokenizer import get_tokenizer
from vllm.transformers_utils import config as vcfg
tok = get_tokenizer("gpt2", trust_remote_code=False)
cfg_dict, cfg = vcfg.HfConfigParser().parse("gpt2", trust_remote_code=False)
print(tok.__class__, cfg)
PY

3) Model loader interface

python3 - << 'PY'
from vllm.model_executor.model_loader.gguf_loader import AutoModelForCausalLM
print(AutoModelForCausalLM)
PY

4) Vision/Multimodal processor test

python3 - << 'PY'
try:
    from transformers import AutoImageProcessor
    print("AutoImageProcessor:", AutoImageProcessor)
except Exception as e:
    print("vision import error", e)
PY


⸻

Общие проверки совместимости
	•	Все прямые импорты internal (configuration_utils, modeling_rope_utils и т.д.) должны быть guarded.
	•	Никто не должен падать с AttributeError на отсутствующий токенизатор атрибут.
	•	.from_pretrained должен работать с обоих версий transformers.
	•	Vision/FeatureExtractor API должен gracefully fallback.
transformers v5 значительно реорганизует токенизацию и modular API, поэтому все такие места должны быть safe-wrapped.  ￼

⸻

Ожидаемый результат

Codex должен вернуть:

✔ Full git-patch with safe imports + guards
✔ List of modified files + changed lines
✔ Smoke test results for both transformers 4.x and 5.x

⸻


📘 Transformers v5 Migration Guide — кратко для кодовых агентов

Источник: официальные релизные заметки и миграционный гайд (предстоящий) по Transformers v5.  ￼

⸻

🚀 1) Общее представление о версии v5
	•	Это первый крупный мажорный релиз после ветки 4.x и результат ~800+ коммитов.  ￼
	•	Основной фокус — модульность, более чистая архитектура, унификация API, улучшенная производительность.  ￼
	•	Команда намеренно минимизирует breaking changes, но они всё равно присутствуют и будут документированы.  ￼

⸻

🧩 2) Основные breaking-changes и их смысл

🔹 Unified Tokenizer Backend
	•	Удаляется разделение «fast» / «slow» токенизаторов — остаётся единый backend.
	•	Старые атрибуты/методы токенизаторов могут быть удалены или перепакованы.
👉 Примечание: функции вроде all_special_tokens_extended могут быть убраны или реорганизованы.
Рекомендуется использовать all_special_tokens с fallback.  ￼

⸻

🔹 Internal Modules Refactoring
	•	Некоторые внутренние модули, которые раньше были доступны через прямые пути (например configuration_utils, modeling_utils), могут быть перемещены или удалены.
👉 Код, который зависит от них напрямую, должен использовать try/except safe-imports или API-обёртки.  ￼

⸻

🔹 Model Weight & Quantization Changes
	•	Путь загрузки весов пересмотрен, а квантование становится первоклассным API в библиотеке.
👉 Некоторые внутренние методы загрузки/инициализации могут измениться.  ￼

⸻

🔹 Image/Feature Extractor API
	•	API для обработки изображений/фичеров (например AutoFeatureExtractor) может быть заменён/переименован в AutoImageProcessor или иметь другие изменения.
👉 Код должен делать safe-import и fallback, если старые классы недоступны.  ￼

⸻

🔹 Deprecation Cleanup
	•	Большое количество устаревших/deprecated методов и параметров может быть удалено.
👉 Рекомендуется использовать новые предпочтительные API там, где это возможно.  ￼

⸻

🔹 Backend Focus & Support Changes
	•	Transformers v5 делает ставку на PyTorch-only поддержку (TensorFlow/Flax уходят в сторону).
👉 Если код ранее использовал мульти-бэкенды, это нужно учесть.  ￼

⸻

🛠 3) Практические правила миграции (для автоматической адаптации)

⚠️ A. Safe Imports вместо прямых

Использовать структуру:

try:
    from transformers.<module> import <name>
except ImportError:
    <name> = None

вместо прямых импортов нестабильных/внутренних модулей.  ￼

⸻

✔ B. Unified Tokenizer Helpers

Чтобы быть безопасным для 4.x и 5:

def safe_all_special_tokens(tokenizer):
    if hasattr(tokenizer, "all_special_tokens_extended"):
        return tokenizer.all_special_tokens_extended
    return tuple(getattr(tokenizer, "all_special_tokens", ()))

Это покрывает изменения API токенизатора.  ￼

⸻

🔁 C. Updated from_pretrained kwargs

Вместо прямого use_auth_token, преобразовать:

if "use_auth_token" in kwargs:
    kwargs["token"] = kwargs.pop("use_auth_token")

для обеспечения совместимости с новой параметризацией.  ￼

⸻

🔄 D. Image/Feature Processor Fallbacks

Использовать:

try:
    from transformers import AutoImageProcessor
except ImportError:
    AutoImageProcessor = None

и аналогично для AutoFeatureExtractor, чтобы поддерживать оба API.  ￼

⸻

🔍 4) Что НЕ стоит делать

❌ Полагаться на internal модульные пути, которые перестали быть публичными.
❌ Вызывать атрибуты токенизатора без проверки наличия.
❌ Жёстко использовать устаревшие параметры .from_pretrained.

⸻

🧪 5) Мини-чеклист после миграции

Проверь:

✔ Код успешно импортируется с transformers 4.57.x и transformers 5.
✔ Токенизатор и модели загружаются без AttributeError.
✔ Все fallback механизмы работают корректно.
✔ Мультимодальные пути (Vision/FeatureExtractor/etc.) безопасно работают или падают с понятным сообщением.
✔ Нет прямых ошибок от внутренних модулей transformers.  ￼

⸻

📎 Ключевые изменения в Transformers v5

Категория	Изменение	Рекомендация
Tokenizer	Unified backend	Использовать безопасные атрибуты
Internal modules	Перемещение/удаление	Safe-import и fallback
from_pretrained kwargs	Префиксы изменены	Переназначить use_auth_token → token
Image processing	AutoImageProcessor	Safe-import AutoImageProcessor/Extractor
Backend support	PyTorch-only	Учесть в конфигурации


⸻

📌 Источники на будущее

📌 План релиза v5 и миграционный гайд в работе — ожидается полная документация после релиза.  ￼
📌 Изменения описаны также в Release Notes RC.  ￼

⸻


🛠 Таблица правил миграции Transformers 4 → 5

(с конкретными функциями/параметрами)

Старый API (4.x)	Что изменилось/удалено в v5	Новый API / Как адаптировать	Пример кода изменения
use_auth_token аргумент в from_pretrained	Заменён на token	Везде переименовать	python\n# old\nAutoModel.from_pretrained(name, use_auth_token="hf_...")\n# new\nAutoModel.from_pretrained(name, token="hf_...")\n
load_in_4bit=True, load_in_8bit=True	Удалено — новый quantization_config	Использовать BitsAndBytesConfig	python\nfrom transformers import BitsAndBytesConfig\nquant_cfg = BitsAndBytesConfig(load_in_4bit=True)\nmodel = AutoModel.from_pretrained(name, quantization_config=quant_cfg)\n
AutoFeatureExtractor	Deprecated → заменён	AutoImageProcessor	python\ntry:\n    from transformers import AutoImageProcessor\nexcept ImportError:\n    AutoImageProcessor = None\n
encode_plus, batch_encode_plus	Deprecated в пользу единого вызова	Использовать tokenizer(text) / tokenizer([...])	python\n# v4\nout = tokenizer.encode_plus(text)\n# v5\nout = tokenizer(text)\n
apply_chat_template возвращал только input_ids	Теперь возвращает BatchEncoding	Новый вызов с return_tensors="pt"	python\nout = tokenizer.apply_chat_template(msgs, return_tensors="pt")\n
Internal imports like configuration_utils	Могут быть перемещены/удалены	Safe-import через try/except	python\ntry:\n    from transformers.configuration_utils import ALLOWED_LAYER_TYPES\nexcept ImportError:\n    ALLOWED_LAYER_TYPES = None\n
Separate “fast”/“slow” tokenizer distinctions	Удалены, unified backend	Не использовать slow/fast специфичные props	python\n# avoid reliance on fast/slow attributes\ntokens = tokenizer(text)\n
TensorFlow/Flax model classes (TFAutoModel, FlaxAutoModel)	Удалены	Использовать PyTorch AutoModel	python\nmodel = AutoModel.from_pretrained(name)\n
TRANSFORMERS_CACHE env variable	Deprecated	USE HF_HOME instead	bash\nexport HF_HOME=/path/to/cache\n
Model config methods like SomeConfig.from_other_config()	Removed	Use SomeConfig(**other_config.to_dict())	python\ncfg = SomeConfig(**other_config.to_dict())\n
Explicit decode / batch_decode distinction	Unified	Use decode consistently	python\ntokens = tokenizer.decode(ids)\n
Legacy CLI commands (transformers-cli)	Replaced	New CLI uses transformers ...	bash\ntransformers login\ntransformers download\n


⸻

🧠 Расширенные пояснения по ключевым изменениям

✅ Authentication аргумент

➡️ use_auth_token → token
Многие вызовы from_pretrained ломаются, если оставить старый параметр.
Код-правило:

if "use_auth_token" in kwargs:
    kwargs["token"] = kwargs.pop("use_auth_token")

— обеспечит совместимость с обоими версиями.  ￼

⸻

⚡ Quantization API

В transformers v5 убраны старые параметризации quantization (load_in_4bit, load_in_8bit).
Нужно создавать объект BitsAndBytesConfig и передавать его как quantization_config.  ￼

⸻

📸 Image/Feature Processing

AutoFeatureExtractor теперь deprecated и заменяется на AutoImageProcessor.
Код должен делать безопасный import:

try:
    from transformers import AutoImageProcessor
except ImportError:
    AutoImageProcessor = None

— fallback обеспечит работу с обеих версий.  ￼

⸻

✂ Internal / reorganized modules

Модули вроде configuration_utils, modeling_utils могли быть перемещены или удалены.
Правило: безопасный import с fallback:

try:
    from transformers.configuration_utils import ALLOWED_LAYER_TYPES
except ImportError:
    ALLOWED_LAYER_TYPES = None

— это гарантирует, что код не упадёт на module not found.  ￼

⸻

🧰 Tokenizer simplification

Убраны различия между fast/slow токенизаторами, и API унифицировано.
Это значит, что код не должен опираться на специфичные fast/slow атрибуты — использовать обобщённые методы tokenizer(text) и безопасные helpers.  ￼

⸻

📜 Environment variables

Новый стандарт кеш-директории — HF_HOME вместо TRANSFORMERS_CACHE.
Это изменение учтено уже в предупреждениях в 4.x и будет обязательным в v5.  ￼

⸻

📌 Быстрые правила для автоматических исправлений (Codex-ready)

🧾 Safe import

try:
    from transformers.some_module import Something
except ImportError:
    Something = None

🧠 Safe tokenizer attributes

def safe_all_special_tokens(tokenizer):
    if hasattr(tokenizer, "all_special_tokens_extended"):
        return tokenizer.all_special_tokens_extended
    return tuple(getattr(tokenizer, "all_special_tokens", []))

🔑 Mapping use_auth_token

if "use_auth_token" in kwargs:
    kwargs["token"] = kwargs.pop("use_auth_token")

🧪 Image processor fallback

try:
    from transformers import AutoImageProcessor
except ImportError:
    AutoImageProcessor = None


⸻

📊 Проверка после миграции

Запусти тесты на обеих версиях transformers:

✔ AutoModel.from_pretrained(...) работает с token=
✔ токенизация через tokenizer(text)
✔ quantization через BitsAndBytesConfig
✔ image processing fallback
✔ internal imports не кидают ImportError

⸻
