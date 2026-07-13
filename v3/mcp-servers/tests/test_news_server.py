import pytest

from src.public.news_server import _extract_items


_NEWS_HTML = """<!DOCTYPE html>
<html>
<head><title>News</title></head>
<body>
<div class="news-list">
  <div class="news-list__item">
    <h3 class="news-list__title"><a href="/news/stories/test-1/">Первая новость</a></h3>
    <span class="news-list__date">12 марта 2026</span>
  </div>
  <div class="news-list__item">
    <h3 class="news-list__title"><a href="/news/stories/test-2/">Вторая новость</a></h3>
    <span class="news-list__date">11 марта 2026</span>
  </div>
</div>
</body>
</html>"""

_EVENTS_HTML = """<!DOCTYPE html>
<html>
<head><title>Events</title></head>
<body>
<div class="news-list">
  <div class="news-list__item">
    <h3 class="news-list__title"><a href="/news/events/event-1/">День открытых дверей</a></h3>
    <span class="news-list__date">1 апреля 2026</span>
  </div>
  <div class="news-list__item">
    <h3 class="news-list__title"><a href="/news/events/event-2/">Научная конференция</a></h3>
    <span class="news-list__date">15 апреля 2026</span>
  </div>
</div>
</body>
</html>"""

_EMPTY_HTML = "<html><body><p>No content</p></body></html>"


class TestExtractItems:
    def test_extracts_news_items(self):
        items = _extract_items(_NEWS_HTML)
        assert len(items) == 2
        assert items[0]["title"] == "Первая новость"
        assert items[0]["url"] == "https://www.utmn.ru/news/stories/test-1/"

    def test_extracts_events_items(self):
        items = _extract_items(_EVENTS_HTML)
        assert len(items) == 2
        assert items[1]["title"] == "Научная конференция"

    def test_absolutizes_relative_urls(self):
        items = _extract_items(_NEWS_HTML)
        assert items[0]["url"].startswith("https://www.utmn.ru")

    def test_returns_empty_list_for_no_items(self):
        items = _extract_items(_EMPTY_HTML)
        assert items == []


@pytest.mark.asyncio
async def test_get_news_returns_markdown(httpx_mock):
    from src.public.news_server import get_news

    httpx_mock.add_response(
        url="https://www.utmn.ru/news/",
        html=_NEWS_HTML,
    )

    result = await get_news(limit=2)
    assert isinstance(result, str)
    assert "Первая новость" in result
    assert "Вторая новость" in result


@pytest.mark.asyncio
async def test_get_events_returns_markdown(httpx_mock):
    from src.public.news_server import get_events

    httpx_mock.add_response(
        url="https://www.utmn.ru/news/events/",
        html=_EVENTS_HTML,
    )

    result = await get_events(limit=2)
    assert isinstance(result, str)
    assert "День открытых дверей" in result


@pytest.mark.asyncio
async def test_get_news_fallback_on_empty(httpx_mock):
    from src.public.news_server import get_news

    httpx_mock.add_response(
        url="https://www.utmn.ru/news/",
        html=_EMPTY_HTML,
    )
    httpx_mock.add_response(
        url="https://www.utmn.ru/rss/",
        text="<rss><channel><item><title>RSS News</title><link>http://rss.link</link></item></channel></rss>",
    )

    result = await get_news(limit=2)
    assert isinstance(result, str) and len(result) > 0


@pytest.mark.asyncio
async def test_get_events_empty_returns_message(httpx_mock):
    from src.public.news_server import get_events

    httpx_mock.add_response(
        url="https://www.utmn.ru/news/events/",
        html=_EMPTY_HTML,
    )

    result = await get_events(limit=2)
    assert isinstance(result, str) and len(result) > 0
