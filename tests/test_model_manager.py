"""Тесты Model Manager, языковых пакетов и подтверждения языка собеседника.

Без запуска моделей: проверяются чистые функции реестра, ответы движка
по состоянию диска и логика порогов определения языка.
"""

from __future__ import annotations

import contextlib
import io
import os
import sys
import unittest

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
APP = os.path.join(ROOT, "app")
TOOLS = os.path.join(ROOT, "tools")
QTAPP = os.path.join(APP, "qtapp")
for path in (APP, QTAPP, TOOLS):
    if path not in sys.path:
        sys.path.insert(0, path)

import live_translate  # noqa: E402
import model_registry as mreg  # noqa: E402


class RouteTests(unittest.TestCase):
    def test_direct_pair(self):
        self.assertEqual(mreg.route("es", "ru"),
                         ["Helsinki-NLP/opus-mt-es-ru"])
        self.assertEqual(mreg.route_kind("es", "ru"), "direct")

    def test_pivot_pair(self):
        chain = mreg.route("de", "ru")
        self.assertEqual(chain, ["Helsinki-NLP/opus-mt-de-en",
                                 "Helsinki-NLP/opus-mt-en-ru"])
        self.assertEqual(mreg.route_kind("de", "ru"), "pivot")

    def test_missing_pair(self):
        # ru->ja нет ни напрямую, ни через английский
        self.assertIsNone(mreg.route("ru", "ja"))
        self.assertEqual(mreg.route_kind("ru", "ja"), "none")

    def test_same_language_needs_nothing(self):
        self.assertEqual(mreg.route("ru", "ru"), [])


class PackTests(unittest.TestCase):
    def test_all_target_languages_have_packs(self):
        packs = mreg.all_packs("ru")
        codes = {p["code"] for p in packs}
        for code in ("en", "es", "de", "fr", "it", "zh", "ja", "hi", "ar"):
            self.assertIn(code, codes)

    def test_pack_lists_only_real_models(self):
        for pack in mreg.all_packs("ru"):
            for repo in pack["models"]:
                self.assertTrue(repo.startswith("Helsinki-NLP/opus-mt-"),
                                repo)

    def test_shared_models_are_not_duplicated(self):
        packs = mreg.all_packs("ru")
        shared = [tuple(p["shared_models"]) for p in packs]
        self.assertEqual(len(set(shared)), 1,
                         "ASR/TTS должны быть общими для всех пакетов")

    def test_pack_uses_shared_pivot(self):
        de = mreg.language_pack("de")
        self.assertIn("Helsinki-NLP/opus-mt-en-ru", de["models"])
        self.assertIn("Helsinki-NLP/opus-mt-de-en", de["models"])
        self.assertNotIn("Helsinki-NLP/opus-mt-en-ru",
                         mreg.language_pack("es")["models"])

    def test_characteristics_are_separate(self):
        # хинди: ASR и TTS есть, прямой перевод на русский — только через en
        hi = mreg.language_pack("hi")
        self.assertTrue(hi["asr_supported"])
        self.assertTrue(hi["tts_supported"])
        self.assertEqual(hi["to_user"]["kind"], "pivot")

    def test_chinese_tts_uses_mandarin_code(self):
        zh = mreg.language_pack("zh")
        self.assertEqual(zh["tts_language"], "zh-cn")


class CatalogTests(unittest.TestCase):
    def setUp(self):
        self.engine = live_translate.Engine()

    def test_catalog_has_all_three_types(self):
        cat = self.engine.catalog()
        types = {m["type"] for m in cat}
        self.assertEqual(types, {"asr", "mt", "tts"})

    def test_catalog_marks_installed_es_ru(self):
        row = next(m for m in self.engine.catalog()
                   if m["id"] == "Helsinki-NLP/opus-mt-es-ru")
        self.assertTrue(row["installed"])
        self.assertGreater(row["disk_mb"], 0)
        self.assertEqual(row["direction"], "es->ru")

    def test_catalog_states_are_known(self):
        allowed = {"NOT INSTALLED", "STOPPED", "READY", "DOWNLOADING"}
        for m in self.engine.catalog():
            self.assertIn(m["state"], allowed)
            self.assertFalse(m["installed"] and m["state"] == "NOT INSTALLED")

    def test_verify_detects_missing_model(self):
        res = self.engine.verify_repo("Helsinki-NLP/opus-mt-does-not-exist")
        self.assertFalse(res["ok"])
        self.assertTrue(res["missing"])

    def test_packs_report_missing_models(self):
        # тест не зависит от того, какие модели сейчас стоят на диске
        packs = self.engine.packs()
        en = next(p for p in packs if p["code"] == "en")
        self.assertIn(en["status"], {"PARTIAL", "READY"})
        for repo in en["missing"]:
            self.assertFalse(mreg.installed(repo))
        self.assertEqual(en["status"] == "READY", not en["missing"])
        self.assertEqual(en["missing_mb"],
                         len(en["missing"]) * mreg.MT_REPO_SIZE_MB)

    def test_packs_share_installed_asr(self):
        for pack in self.engine.packs():
            self.assertTrue(pack["asr_installed"])

    def test_shared_pivot_model_is_visible_in_packs(self):
        # en-ru нужен и пакету en, и (через en) немецкому — общий ресурс.
        packs = self.engine.packs()
        en = next(p for p in packs if p["code"] == "en")
        de = next(p for p in packs if p["code"] == "de")
        en_ids = [m["id"] for m in en["models"]]
        de_ids = [m["id"] for m in de["models"]]
        self.assertIn("Helsinki-NLP/opus-mt-en-ru", en_ids)
        self.assertIn("Helsinki-NLP/opus-mt-en-ru", de_ids)


class PeerLangTests(unittest.TestCase):
    def setUp(self):
        self.engine = live_translate.Engine()
        self.engine.peer_lang = "auto"
        self.engine.peer_lang_confirmed = ""

    def detect(self, code="es", prob=0.9, dur=2.0, words=4):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            return self.engine._detect_peer_lang(code, prob, dur, words)

    def test_accepts_confident_fragment(self):
        ok, _ = self.detect()
        self.assertTrue(ok)
        self.assertEqual(self.engine.peer_lang_confirmed, "es")

    def test_rejects_short_fragment(self):
        ok, reason = self.detect(dur=0.5)
        self.assertFalse(ok)
        self.assertIn("короткий", reason)

    def test_rejects_single_word(self):
        ok, reason = self.detect(words=1)
        self.assertFalse(ok)
        self.assertIn("слов", reason)

    def test_rejects_low_confidence(self):
        ok, reason = self.detect(prob=0.3)
        self.assertFalse(ok)
        self.assertIn("уверенность", reason)

    def test_language_switch_needs_second_hit(self):
        self.detect(code="es")
        ok, reason = self.detect(code="en")
        self.assertFalse(ok, "одна фраза не должна менять язык разговора")
        ok2, _ = self.detect(code="en")
        self.assertTrue(ok2)
        self.assertEqual(self.engine.peer_lang_confirmed, "en")

    def test_same_language_not_switched(self):
        self.detect(code="es")
        ok, _ = self.detect(code="es")
        self.assertTrue(ok)
        self.assertEqual(self.engine.peer_lang_confirmed, "es")

    def test_manual_choice_sets_confirmed_language(self):
        with contextlib.redirect_stdout(io.StringIO()):
            code = self.engine.set_peer_lang("en")
        self.assertEqual(code, "en")
        self.assertEqual(self.engine.peer_lang_confirmed, "en")
        # ручной выбор не перезаписывается автоопределением
        self.assertEqual(self.engine.peer_lang, "en")


class PackageTests(unittest.TestCase):
    def test_download_package_skips_installed(self):
        engine = live_translate.Engine()
        calls = []
        engine.download_repos = lambda repos, req, label="": (
            calls.extend(repos) or True)
        with contextlib.redirect_stdout(io.StringIO()):
            ok = engine.download_package("es")
        self.assertTrue(ok)
        # es->ru уже стоит; download_repos всё равно получает список
        self.assertEqual(calls, ["Helsinki-NLP/opus-mt-es-ru"])

    def test_download_package_unknown_language(self):
        engine = live_translate.Engine()
        with contextlib.redirect_stdout(io.StringIO()):
            self.assertFalse(engine.download_package("xx"))


if __name__ == "__main__":
    unittest.main()
