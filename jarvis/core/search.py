import sys, os, requests
sys.path.insert(0, os.path.expanduser('~/jarvis'))
from bs4 import BeautifulSoup

def search(query: str, num_results: int = 3) -> str:
    """Fast requests-based search — for general tasks."""
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
        r = requests.get(
            f"https://html.duckduckgo.com/html/?q={query.replace(' ', '+')}",
            headers=headers, timeout=8
        )
        soup = BeautifulSoup(r.text, "html.parser")
        results = []
        for block in soup.select(".result__snippet"):
            text = block.get_text(strip=True)
            if text and len(text) > 40:
                results.append(text)
                if len(results) >= num_results:
                    break
        return "\n\n".join(results) if results else "No results found."
    except Exception as e:
        return f"Search error: {e}"

def browse(url: str) -> str:
    """Open real visible browser, grab content, close within 8 seconds."""
    try:
        from playwright.sync_api import sync_playwright
        with sync_playwright() as p:
            browser = p.chromium.launch(headless=False)
            page = browser.new_page()
            page.goto(url, timeout=12000, wait_until="domcontentloaded")
            page.wait_for_timeout(3000)
            html = page.content()
            browser.close()
        soup = BeautifulSoup(html, "html.parser")
        for tag in soup(["script", "style", "nav", "footer", "header"]):
            tag.decompose()
        return soup.get_text(separator="\n", strip=True)[:3000]
    except Exception as e:
        return f"Browse error: {e}"

def search_and_browse(query: str) -> str:
    """Search then open top result in real browser."""
    try:
        headers = {"User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36"}
        r = requests.get(
            f"https://html.duckduckgo.com/html/?q={query.replace(' ', '+')}",
            headers=headers, timeout=8
        )
        soup = BeautifulSoup(r.text, "html.parser")
        link = soup.select_one(".result__a")
        if link and link.get("href"):
            href = link["href"]
            # DDG wraps URLs — extract the real one
            if "uddg=" in href:
                from urllib.parse import unquote, urlparse, parse_qs
                real = parse_qs(urlparse(href).query).get("uddg", [None])[0]
                if real:
                    href = unquote(real)
            print(f"[Browser] Opening {href}")
            content = browse(href)
            if "Browse error" not in content:
                return content
        # fallback to snippets
        return search(query)
    except Exception as e:
        return f"Search and browse error: {e}"

if __name__ == "__main__":
    print(search_and_browse("blender python bpy add cube example"))
