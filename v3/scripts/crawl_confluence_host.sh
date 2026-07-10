#!/usr/bin/env bash
# Crawl Confluence from HOST machine (bypasses Docker/Vouch SSO limitation on macOS)
# Requires: VPN connected, CONFLUENCE_TOKEN in .env
set -euo pipefail

cd "$(dirname "$0")/.."

# Load env vars
set -a; source .env; set +a

if [ -z "${CONFLUENCE_TOKEN:-}" ]; then
    echo "ERROR: CONFLUENCE_TOKEN not set in .env"
    exit 1
fi

HOST="https://confluence.utmn.ru"
HEADERS=(-H "Authorization: Bearer $CONFLUENCE_TOKEN" -H "Accept: application/json")

echo "=== Confluence Help (hardcoded pages) ==="

# Pages from ConfluenceHelpParser
PAGES=(
    "8037241:Карты доступа"
    "8037222:Корпоративная учетная запись"
    "62586931:Яндекс 360"
    "121923452:Единый личный кабинет ТюмГУ"
    "121906735:Основы работы с LMS"
    "8037245:Беспроводная сеть Wi-Fi"
)

for entry in "${PAGES[@]}"; do
    PAGE_ID="${entry%%:*}"
    TITLE="${entry##*:}"
    echo "  → $TITLE ($PAGE_ID)"

    JSON=$(curl -sf "${HEADERS[@]}" "$HOST/rest/api/content/$PAGE_ID?expand=body.export_view" 2>/dev/null || true)
    if [ -z "$JSON" ]; then
        echo "    SKIP (HTTP error)"
        continue
    fi

    BODY=$(echo "$JSON" | python3 -c "
import sys, json
data = json.load(sys.stdin)
html = data.get('body', {}).get('export_view', {}).get('value', '')
if len(html) > 50:
    from bs4 import BeautifulSoup
    soup = BeautifulSoup(html, 'html.parser')
    text = soup.get_text(separator=' ')
    if len(text.strip()) >= 100:
        print(text.strip())
" 2>/dev/null) || continue

    if [ -n "$BODY" ]; then
        echo "    Sending to kb-service..."
        curl -sf -X POST http://localhost:8005/api/v1/tools \
            -H "Content-Type: application/json" \
            -d "{\"jsonrpc\":\"2.0\",\"method\":\"store_document\",\"params\":{\"url\":\"$HOST/pages/viewpage.action?pageId=$PAGE_ID\",\"source_type\":\"confluence_help\"},\"id\":1}" > /dev/null
    fi
done

echo ""
echo "=== Confluence Study (all pages) ==="

SEARCH_URL="$HOST/rest/api/search?cql=space.key%3Dstudy+order+by+id&start=0&limit=100"

while [ -n "$SEARCH_URL" ]; do
    RESULT=$(curl -sf "${HEADERS[@]}" "$SEARCH_URL" 2>/dev/null || echo '{"results":[]}')
    echo "$RESULT" | python3 -c "
import sys, json, subprocess
data = json.load(sys.stdin)
results = data.get('results', [])
for r in results:
    content = r.get('content', {})
    page_id = content.get('id', '')
    title = content.get('title', 'Untitled')
    page_url = '$HOST' + content.get('_links', {}).get('webui', '')
    print(f'  → {title} ({page_id})')

    # Fetch page HTML
    import httpx
    token = '$CONFLUENCE_TOKEN'
    headers = {'Authorization': f'Bearer {token}', 'Accept': 'application/json'}
    try:
        resp = httpx.get(f'https://confluence.utmn.ru/rest/api/content/{page_id}?expand=body.export_view', headers=headers, timeout=15)
        if resp.status_code != 200:
            print('    SKIP (HTTP ' + str(resp.status_code) + ')')
            continue
        data = resp.json()
        html = data.get('body', {}).get('export_view', {}).get('value', '')
        if len(html) <= 50:
            print('    SKIP (empty body)')
            continue
        from bs4 import BeautifulSoup
        soup = BeautifulSoup(html, 'html.parser')
        text = soup.get_text(separator=' ')
        if len(text.strip()) < 100:
            print('    SKIP (too short)')
            continue
        # Store via kb-service
        subprocess.run([
            'curl', '-sf', '-X', 'POST', 'http://localhost:8005/api/v1/tools',
            '-H', 'Content-Type: application/json',
            '-d', json.dumps({
                'jsonrpc': '2.0',
                'method': 'store_document',
                'params': {'url': page_url, 'source_type': 'confluence_study'},
                'id': 1
            })
        ], capture_output=True)
        print('    Stored')
    except Exception as e:
        print(f'    ERROR: {e}')
" 2>&1

    # Check for next page
    NEXT=$(echo "$RESULT" | python3 -c "import sys,json; d=json.load(sys.stdin); print(d.get('_links',{}).get('next',''))" 2>/dev/null)
    SEARCH_URL="$NEXT"
    if [ -z "$SEARCH_URL" ] || [ "$SEARCH_URL" = "None" ]; then
        SEARCH_URL=""
    fi
done

echo ""
echo "=== Done ==="
