"""ЗАМЕР 4: СКВОЗНОЙ тест «говорю по-русски -> слышу себя на испанском».

Полный конвейер на реальных русских записях пользователя:
    микрофон (уже записано) -> Whisper RU -> перевод -> XTTS ES (клонированный голос)
    -> аудио на выход

Меряем задержку каждого этапа и итоговую.

Запуск (движок):
    "<engine>\\Scripts\\python.exe" research\\bench_end_to_end.py
"""

from __future__ import annotations

import glob
import os
import sys
import time

import numpy as np

WS = os.path.join(os.environ.get("LOCALAPPDATA", ""), "RedZVoiceStudio", "workspace")
REF = os.path.join(WS, "reference.wav")
HF = os.path.expanduser(r"~\.cache\huggingface\hub")
XTTS_SNAP = glob.glob(os.path.join(HF, "models--tts-hub--XTTS-v2", "snapshots", "*"))
XTTS_SNAP = XTTS_SNAP[0] if XTTS_SNAP else None
MT_MODEL = "Helsinki-NLP/opus-mt-ru-es"
SR = 16000


def patch_torchaudio():
    sys.path.insert(0, os.path.join(os.path.dirname(os.path.abspath(__file__)), "..", "tools"))
    import xtts_clone
    xtts_clone.patch_torchaudio()


def main() -> None:
    import soundfile as sf
    import torch

    patch_torchaudio()
    from faster_whisper import WhisperModel
    from transformers import AutoTokenizer, AutoModelForSeq2SeqLM
    from TTS.tts.configs.xtts_config import XttsConfig
    from TTS.tts.models.xtts import Xtts

    print("=== Загрузка трёх моделей ===")
    t0 = time.time()
    asr = WhisperModel("mobiuslabsgmbh/faster-whisper-large-v3-turbo",
                       device="cuda", compute_type="float16")
    print(f"  Whisper turbo:        {time.time() - t0:5.1f} с")

    t0 = time.time()
    tok = AutoTokenizer.from_pretrained(MT_MODEL)
    mt = AutoModelForSeq2SeqLM.from_pretrained(MT_MODEL, dtype=torch.float16).to("cuda").eval()
    print(f"  opus-mt-ru-es:        {time.time() - t0:5.1f} с")

    t0 = time.time()
    cfg = XttsConfig()
    cfg.load_json(os.path.join(XTTS_SNAP, "config.json"))
    tts = Xtts.init_from_config(cfg)
    tts.load_checkpoint(cfg, checkpoint_dir=XTTS_SNAP,
                        vocab_path=os.path.join(XTTS_SNAP, "vocab.json"))
    tts.cuda()
    print(f"  XTTS-v2:              {time.time() - t0:5.1f} с")

    # кэш голоса — считается один раз, дальше 0.03 с
    t0 = time.time()
    gpt_latent, spk_emb = tts.get_conditioning_latents(audio_path=[REF])
    print(f"  кэш голоса:           {time.time() - t0:5.1f} с\n")

    def translate(text: str) -> str:
        batch = tok([text], return_tensors="pt", padding=True).to("cuda")
        with torch.inference_mode():
            out = mt.generate(**batch, max_new_tokens=96, num_beams=1)
        return tok.batch_decode(out, skip_special_tokens=True)[0]

    files = sorted(glob.glob(os.path.join(WS, "voice_samples", "*.wav")))[:6]
    print("=== СКВОЗНОЙ ТЕСТ (реальные русские записи) ===")
    rows = []
    for path in files:
        audio, sr = sf.read(path, dtype="float32", always_2d=False)
        if audio.ndim > 1:
            audio = audio.mean(axis=1)
        # в реальности микрофон -> 16 кГц для Whisper
        if sr != SR:
            from scipy.signal import resample_poly
            from math import gcd
            g = gcd(int(sr), SR)
            audio = resample_poly(audio, SR // g, int(sr) // g).astype(np.float32)

        t0 = time.perf_counter()
        segs, _ = asr.transcribe(audio, language="ru", beam_size=1,
                                 vad_filter=False, condition_on_previous_text=False,
                                 no_speech_threshold=0.8, log_prob_threshold=-2.0)
        ru = " ".join(s.text.strip() for s in segs)
        t_asr = time.perf_counter() - t0

        t0 = time.perf_counter()
        es = translate(ru)
        t_tr = time.perf_counter() - t0

        t0 = time.perf_counter()
        chunks = tts.inference_stream(es, "es", gpt_latent, spk_emb,
                                      stream_chunk_size=20, temperature=0.7)
        first = None
        n_samples = 0
        for c in chunks:
            arr = c.detach().cpu().numpy()
            if first is None:
                first = time.perf_counter() - t0
            n_samples += arr.shape[-1]
        t_tts_total = time.perf_counter() - t0

        total = t_asr + t_tr + (first or 0)
        rows.append((t_asr, t_tr, first or 0, total))
        print(f"\n  {os.path.basename(path)}")
        print(f"    RU: {ru[:60]}")
        print(f"    ES: {es[:60]}")
        print(f"    ASR {t_asr * 1000:6.0f} мс | перевод {t_tr * 1000:5.0f} мс | "
              f"первый звук {(first or 0) * 1000:5.0f} мс")
        print(f"    >>> ДО ПЕРВОГО ЗВУКА: {total * 1000:.0f} мс "
              f"(аудио {n_samples / 24000:.1f} с, TTS всего {t_tts_total:.1f} с)")

    if rows:
        avg = lambda i: sum(r[i] for r in rows) / len(rows)  # noqa: E731
        print("\n=== СРЕДНИЕ ===")
        print(f"  ASR:               {avg(0) * 1000:6.0f} мс")
        print(f"  перевод:           {avg(1) * 1000:6.0f} мс")
        print(f"  TTS до 1-го звука: {avg(2) * 1000:6.0f} мс")
        print(f"  ИТОГО:             {avg(3) * 1000:6.0f} мс")


if __name__ == "__main__":
    main()
