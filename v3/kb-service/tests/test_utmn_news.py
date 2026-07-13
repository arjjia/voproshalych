"""Тесты парсера новостного портала utmn.ru (news/events).

Сеть не нужна: тестируем синхронные вспомогательные методы на fixture-HTML,
воспроизводящем реальную структуру Bitrix-страницы.
"""

from kb.parsers.utmn_news import UtmnNewsParser

# Фрагмент list-страницы https://www.utmn.ru/news/stories/ (реальная структура)
LIST_HTML = """
<ul class="last-news_list unstyled last-news_list_page-news">
  <li class="news-page__el">
    <article id="bx_1_1368959" class="article hover image-bg ">
      <div class="article__image"><a href="/news/stories/obrazovanie/1368959/"></a></div>
      <div class="category">
        <div class="date">
          <div class="month">июл</div>
          <div class="day"><a href="/news/stories/?ACTIVE_FROM=13.07.2026;13.07.2026"> 13 </a></div>
          <div class="year">2026</div>
        </div>
        <div class="category_title"><a href="/news/stories/obrazovanie/">Образование</a></div>
      </div>
      <div class="article_title long-string very-long-string">
        <a href="/news/stories/obrazovanie/1368959/">Не только пыльные страницы</a>
      </div>
      <a href="/news/stories/obrazovanie/1368959/" class="full"></a>
    </article>
  </li>
  <li class="news-page__el">
    <article id="bx_1_1369757" class="article hover ">
      <div class="category">
        <div class="date">
          <div class="month">июл</div>
          <div class="day"><a href="/news/stories/?ACTIVE_FROM=13.07.2026;13.07.2026"> 13 </a></div>
          <div class="year">2026</div>
        </div>
        <div class="category_title"><a href="/news/stories/nauka-i-innovatsii/">Наука</a></div>
      </div>
      <div class="article_title long-string very-long-string">
        <a href="/news/stories/nauka-i-innovatsii/1369757/">Опять отмена?</a>
      </div>
    </article>
  </li>
</ul>
"""

ARTICLE_HTML = """
<html><head><title>Не только пыльные страницы</title></head>
<body>
<header>Шапка сайта</header>
<nav>Меню</nav>
<article>
  <h1>Не только пыльные страницы</h1>
  <p>Студенты-филологи проходят архивную практику.</p>
  <p>Второй абзац текста новости.</p>
</article>
<footer>Подвал</footer>
<script>var x = 1;</script>
</body></html>
"""


def test_parse_list_extracts_items():
    parser = UtmnNewsParser(kind="news")
    items = parser._parse_list(LIST_HTML, "https://www.utmn.ru/news/stories/")

    assert len(items) == 2
    first = items[0]
    assert first["title"] == "Не только пыльные страницы"
    assert first["url"] == "https://www.utmn.ru/news/stories/obrazovanie/1368959/"
    assert first["category"] == "Образование"
    assert "13" in first["date"] and "июл" in first["date"] and "2026" in first["date"]


def test_parse_list_absolutizes_relative_urls():
    parser = UtmnNewsParser(kind="news")
    items = parser._parse_list(LIST_HTML, "https://www.utmn.ru/news/stories/")
    assert items[0]["url"].startswith("https://www.utmn.ru/")


def test_extract_date():
    parser = UtmnNewsParser(kind="news")
    soup_article = UtmnNewsParser  # noqa: F841 (placeholder for readability)
    from bs4 import BeautifulSoup

    article = BeautifulSoup(LIST_HTML, "html.parser").select_one(
        "li.news-page__el article"
    )
    date = UtmnNewsParser._extract_date(article)
    assert "13" in date
    assert "июл" in date
    assert "2026" in date


def test_extract_article_text_strips_chrome():
    text = UtmnNewsParser._extract_article_text(ARTICLE_HTML)
    assert "Студенты-филологи" in text
    assert "Второй абзац" in text
    # шапка/меню/подвал/скрипты выкинуты
    assert "Шапка сайта" not in text
    assert "Подвал" not in text
    assert "var x" not in text


def test_to_document_contains_metadata_and_body():
    parser = UtmnNewsParser(kind="news")
    item = {
        "url": "https://www.utmn.ru/news/stories/obrazovanie/1368959/",
        "title": "Не только пыльные страницы",
        "category": "Образование",
        "date": "13 июл 2026",
        "full_text": "Студенты-филологи проходят архивную практику.",
    }
    doc = parser._to_document(item)

    assert doc.source_type == "news"
    assert doc.url == item["url"]
    assert doc.title == "Не только пыльные страницы"
    assert "Категория: Образование" in doc.text_content
    assert "Дата: 13 июл 2026" in doc.text_content
    assert "Студенты-филологи" in doc.text_content


def test_with_pagen():
    base = "https://www.utmn.ru/news/stories/"
    assert UtmnNewsParser._with_pagen(base, 2) == "https://www.utmn.ru/news/stories/?PAGEN_1=2"
    base_q = "https://www.utmn.ru/news/stories/?foo=bar"
    assert UtmnNewsParser._with_pagen(base_q, 3) == "https://www.utmn.ru/news/stories/?foo=bar&PAGEN_1=3"


def test_source_type_differs_for_events():
    assert UtmnNewsParser(kind="news").get_source_type() == "news"
    assert UtmnNewsParser(kind="events").get_source_type() == "events"


def test_invalid_kind_raises():
    try:
        UtmnNewsParser(kind="nope")
    except ValueError:
        return
    raise AssertionError("Ожидался ValueError для неизвестного kind")
