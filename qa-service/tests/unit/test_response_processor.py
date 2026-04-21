"""Unit тесты для response_processor."""

import pytest

from qa.services.response_processor import (
    clean_markdown,
    extract_links,
    format_answer,
    process_llm_response,
)


class TestCleanMarkdown:
    """Тесты для clean_markdown."""

    def test_removes_headers(self):
        result = clean_markdown("## Заголовок\nТекст")
        assert "##" not in result
        assert "Заголовок" in result
        assert "Текст" in result

    def test_removes_bold(self):
        result = clean_markdown("Это **важный** текст")
        assert "важный" in result
        assert "**" not in result

    def test_removes_italic(self):
        result = clean_markdown("Это *курсивный* текст")
        assert "курсивный" in result
        assert "*" not in result

    def test_removes_code_blocks(self):
        result = clean_markdown("До\n```\nкод\n```\nПосле")
        assert "код" not in result
        assert "До" in result
        assert "После" in result

    def test_removes_inline_code(self):
        result = clean_markdown("Используйте `pip install`")
        assert "pip install" in result
        assert "`" not in result

    def test_removes_bullet_lists(self):
        result = clean_markdown("- пункт 1\n- пункт 2")
        assert "пункт 1" in result
        assert "пункт 2" in result
        assert "- " not in result

    def test_removes_numbered_lists(self):
        result = clean_markdown("1. первый\n2. второй")
        assert "первый" in result
        assert "второй" in result
        assert "1." not in result
        assert "2." not in result

    def test_removes_links(self):
        result = clean_markdown("Сайт [ТюмГУ](https://utmn.ru)")
        assert "ТюмГУ" in result
        assert "https://utmn.ru" in result
        assert "[" not in result
        assert "]" not in result

    def test_removes_entity_tags(self):
        result = clean_markdown("Текст <entity:12345> метка")
        assert "<entity:" not in result
        assert "Текст" in result
        assert "метка" in result

    def test_removes_cite_markers(self):
        result = clean_markdown("Ответ【3†L3-L5】 текст")
        assert "【" not in result
        assert "Ответ" in result
        assert "текст" in result

    def test_collapses_multiple_newlines(self):
        result = clean_markdown("Строка1\n\n\n\nСтрока2")
        assert "\n\n\n" not in result
        assert "Строка1" in result
        assert "Строка2" in result

    def test_empty_string(self):
        result = clean_markdown("")
        assert result == ""

    def test_no_markdown(self):
        text = "Обычный текст без форматирования"
        assert clean_markdown(text) == text


class TestExtractLinks:
    """Тесты для extract_links."""

    def test_extracts_podrobne_url(self):
        text = "Ответ на вопрос.\nПодробнее: https://utmn.ru/page1"
        clean, urls = extract_links(text)
        assert "https://utmn.ru/page1" in urls
        assert "Подробнее:" not in clean

    def test_bare_url_on_own_line_not_extracted(self):
        text = "Смотрите:\nhttps://sveden.utmn.ru/info"
        clean, urls = extract_links(text)
        assert "https://sveden.utmn.ru/info" not in urls

    def test_url_with_podrobne_extracted(self):
        text = "Подробнее: https://sveden.utmn.ru/info"
        clean, urls = extract_links(text)
        assert "https://sveden.utmn.ru/info" in urls

    def test_skips_references_header(self):
        text = "Ответ\nReferences\nhttps://example.com"
        clean, urls = extract_links(text)
        assert "References" not in clean

    def test_deduplicates_urls(self):
        text = (
            "Подробнее: https://utmn.ru/a\n"
            "Подробнее: https://utmn.ru/a\n"
            "Подробнее: https://utmn.ru/b"
        )
        _, urls = extract_links(text)
        assert urls.count("https://utmn.ru/a") == 1

    def test_no_urls(self):
        text = "Просто текст без ссылок"
        clean, urls = extract_links(text)
        assert urls == []
        assert clean == text


class TestFormatAnswer:
    """Тесты для format_answer."""

    def test_short_text_unchanged(self):
        text = "Короткий ответ"
        assert format_answer(text) == text

    def test_truncates_long_text(self):
        text = "Абзац\n\n" + "x" * 2000
        result = format_answer(text, max_length=500)
        assert len(result) <= 500

    def test_respects_paragraph_boundary(self):
        paragraphs = []
        for i in range(10):
            paragraphs.append(f"Абзац {i} " * 20)
        text = "\n\n".join(paragraphs)
        result = format_answer(text, max_length=200)
        assert len(result) <= 200


class TestProcessLlmResponse:
    """Тесты для process_llm_response (полный пайплайн)."""

    def test_full_pipeline(self):
        raw = (
            "## Ответ\n\n"
            "Студенты могут **получить справку** через портал.\n\n"
            "Подробнее: https://utmn.ru/help"
        )
        answer, links = process_llm_response(raw)
        assert "##" not in answer
        assert "**" not in answer
        assert "получить справку" in answer
        assert "https://utmn.ru/help" in links

    def test_empty_input(self):
        answer, links = process_llm_response("")
        assert answer == ""
        assert links == []
