import pytest


_HTML_PAGE = """<!DOCTYPE html>
<html>
<head><title>Test Page</title></head>
<body>
<nav>Menu</nav>
<main>
  <h1>Hello World</h1>
  <p>This is a test page content.</p>
</main>
<footer>Footer text</footer>
</body>
</html>"""


@pytest.mark.asyncio
async def test_fetch_url_returns_title_and_content(httpx_mock):
    from src.public.fetch_server import fetch_url

    httpx_mock.add_response(
        url="https://example.com/test",
        html=_HTML_PAGE,
    )

    result = await fetch_url("https://example.com/test")
    assert "Test Page" in result
    assert "Hello World" in result
    assert "test page content" in result
    assert "Footer text" not in result
    assert "Menu" not in result


@pytest.mark.asyncio
async def test_fetch_url_auto_adds_https(httpx_mock):
    from src.public.fetch_server import fetch_url

    httpx_mock.add_response(
        url="https://example.com/page",
        html=_HTML_PAGE,
    )

    result = await fetch_url("example.com/page")
    assert "Test Page" in result


@pytest.mark.asyncio
async def test_fetch_url_http_error(httpx_mock):
    from src.public.fetch_server import fetch_url

    httpx_mock.add_response(
        url="https://example.com/404",
        status_code=404,
    )

    result = await fetch_url("https://example.com/404")
    assert "404" in result or "ошибк" in result.lower()


@pytest.mark.asyncio
async def test_fetch_url_non_html(httpx_mock):
    from src.public.fetch_server import fetch_url

    httpx_mock.add_response(
        url="https://example.com/file.txt",
        headers={"content-type": "text/plain"},
        text="plain text content here",
    )

    result = await fetch_url("https://example.com/file.txt")
    assert "plain text content" in result
    assert "Content from" in result


@pytest.mark.asyncio
async def test_fetch_url_honors_max_length(httpx_mock):
    from src.public.fetch_server import fetch_url

    long_text = "<html><body><p>" + "A" * 2000 + "</p></body></html>"

    httpx_mock.add_response(
        url="https://example.com/long",
        html=long_text,
    )

    result = await fetch_url("https://example.com/long", max_length=100)
    assert len(result) > 0
    assert "источник" in result.lower() or "source" in result.lower() or "error" in result.lower()
