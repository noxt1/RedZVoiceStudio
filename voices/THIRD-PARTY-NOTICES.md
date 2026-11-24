# Third-party notices — Auraloom Voice Studio

Всё, что лежит в папке `voices/`, свободно распространяется: исходные
код и модели взяты под свободными лицензиями, а готовые образцы
интонации (`voices/prompts/*.wav`) сгенерированы из них.

## Piper TTS — MIT License

Синтез речи и сам пакет `piper` (MIT).
Источник: <https://github.com/rhasspy/piper>

```
MIT License

Copyright (c) 2021 Michael Hansen

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```

## Голос Piper `es_MX-ald-medium` — Unlicense (public domain)

Модель: <https://huggingface.co/rhasspy/piper-voices/tree/main/es/es_MX/ald/medium>
Набор данных: <https://huggingface.co/datasets/rmcpantoja/Ald_Mexican_Spanish_speech_dataset>
Лицензия набора данных: <http://unlicense.org> — общественное достояние,
свободное использование и распространение без условий.

## Голос Piper `es_MX-claude-high` — Apache License 2.0

Модель: <https://huggingface.co/rhasspy/piper-voices/tree/main/es/es_MX/claude/high>
Набор данных: <https://huggingface.co/spaces/HirCoir/Piper-TTS-Spanish>
Лицензия набора данных: Apache-2.0. Код и веса разрешено
распространять свободно, при условии сохранения уведомления об
авторских правах.

Apache License 2.0 (кратко): <https://www.apache.org/licenses/LICENSE-2.0>

## Готовые образцы интонации `voices/prompts/*.wav`

Это заранее озвученные референсы интонации для 18 подсказок. Созданы
скриптом `tools/build_prompt_audio.py` из голоса `es_MX-claude-high`
(Apache-2.0) с помощью Piper (MIT), поэтому распространяются свободно
на условиях Apache-2.0.

Пересобрать:

```
python tools/build_prompt_audio.py
```

Проверить:

```
python tools/check_prompt_audio.py
```

Образцы нужны для того, чтобы пользователь слышал, как произносить
фразу, до записи. Записывать их вручную не требуется.
