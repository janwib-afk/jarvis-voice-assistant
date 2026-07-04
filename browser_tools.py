"""
Jarvis V2 — Browser Tools
Web search via DuckDuckGo Lite, page visits via Playwright, URL opening.
"""

import html as html_module
import logging
import re
import webbrowser
import subprocess
from urllib.parse import unquote, parse_qs, urlparse, quote_plus
import httpx

logger = logging.getLogger("jarvis.browser")

# Maximal so viele Tabs gleichzeitig — der aelteste wird automatisch geschlossen.
MAX_TABS = 5

_pw = None
_browser = None
_context = None


def _bring_chromium_to_front():
    """Bring the Playwright Chromium window to the foreground on Windows."""
    try:
        subprocess.run([
            "powershell", "-Command",
            '(Get-Process -Name "chromium","chrome" -ErrorAction SilentlyContinue | '
            'Where-Object { $_.MainWindowHandle -ne 0 } | Select-Object -Last 1).MainWindowHandle | '
            'ForEach-Object { Add-Type "using System; using System.Runtime.InteropServices; '
            'public class W { [DllImport(\\\"user32.dll\\\")] public static extern bool SetForegroundWindow(IntPtr h); }"; '
            '[W]::SetForegroundWindow($_) }'
        ], capture_output=True, timeout=3)
    except Exception:
        logger.debug("Chromium-Fenster konnte nicht in den Vordergrund geholt werden", exc_info=True)


async def _get_browser():
    global _pw, _browser, _context
    # Auch relaunchen, wenn der Nutzer das Chromium-Fenster geschlossen hat.
    if _browser is None or not _browser.is_connected():
        # Lazy import: fehlendes Playwright darf den Server-Start nicht crashen,
        # sondern erst die Browser-Aktion mit klarer Meldung scheitern lassen.
        try:
            from playwright.async_api import async_playwright
        except ImportError:
            raise RuntimeError(
                "Playwright ist nicht installiert. "
                "Installiere es mit: pip install -r requirements.txt"
            )
        _browser = None
        _context = None
        if _pw is None:
            _pw = await async_playwright().start()
        _browser = await _pw.chromium.launch(headless=False, args=["--start-maximized"])
        _context = await _browser.new_context(
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36",
            no_viewport=True,
        )
    return _context


async def _new_page_capped():
    """Neuer Tab; schliesst vorher die aeltesten, wenn MAX_TABS erreicht ist.

    Aktionen laufen sequenziell pro WS-Session, daher kein Lock noetig.
    """
    global _browser, _context
    for attempt in range(2):
        ctx = await _get_browser()
        try:
            # ctx.pages enthaelt nur offene Tabs in Erstellungsreihenfolge —
            # vom Nutzer manuell geschlossene zaehlen nicht mit.
            while len(ctx.pages) >= MAX_TABS:
                await ctx.pages[0].close()
            return await ctx.new_page()
        except Exception:
            # Fenster wurde zwischen Check und Nutzung geschlossen: einmal neu starten.
            if attempt == 0:
                logger.warning("Browser nicht mehr erreichbar, starte neu", exc_info=True)
                _browser = None
                _context = None
            else:
                raise


async def search_and_read(query: str) -> dict:
    """Search DuckDuckGo in visible browser, click first result, read the page."""
    page = await _new_page_capped()
    try:
        # DuckDuckGo search (no cookie banner, no reCAPTCHA)
        search_url = f"https://duckduckgo.com/?q={quote_plus(query)}"
        await page.goto(search_url, timeout=15000)
        _bring_chromium_to_front()
        await page.wait_for_timeout(2000)

        # Click first organic result
        first_link = page.locator('[data-testid="result-title-a"]').first
        if await first_link.count() > 0:
            await first_link.click()
            await page.wait_for_timeout(3000)

            # Read page content
            title = await page.title()
            url = page.url
            text = await page.evaluate("""
                () => {
                    const selectors = ['main', 'article', '[role="main"]', '.content', '#content', 'body'];
                    for (const sel of selectors) {
                        const el = document.querySelector(sel);
                        if (el && el.innerText.trim().length > 100) {
                            return el.innerText.trim();
                        }
                    }
                    return document.body?.innerText?.trim() || '';
                }
            """)
            return {"title": title, "url": url, "content": text[:3000]}
        else:
            return {"title": "Keine Ergebnisse", "url": search_url, "content": "Keine Ergebnisse gefunden."}
    except Exception as e:
        return {"error": str(e), "url": query}
    finally:
        pass


# DuckDuckGos HTML-Endpoint: Treffer-Links tragen die Klasse result__a und
# verlinken meist ueber einen /l/?uddg=…-Redirect auf die eigentliche URL.
_DDG_RESULT_RE = re.compile(
    r'<a[^>]*class="[^"]*result__a[^"]*"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
    re.DOTALL,
)
_TAG_RE = re.compile(r"<[^>]+>")


def _decode_ddg_href(href: str) -> str | None:
    """Loest den uddg-Redirect auf; laesst direkte http(s)-URLs unveraendert."""
    href = html_module.unescape(href.strip())
    if href.startswith("//"):
        href = "https:" + href
    try:
        parsed = urlparse(href)
    except ValueError:
        return None
    if "duckduckgo.com" in (parsed.netloc or "") and parsed.path.startswith("/l/"):
        uddg = parse_qs(parsed.query).get("uddg", [""])[0]
        href = unquote(uddg)
    if href.startswith("http://") or href.startswith("https://"):
        return href
    return None


def parse_ddg_html(html: str, limit: int = 4) -> list[dict]:
    """Extrahiert {title, url} aus einer html.duckduckgo.com-Ergebnisseite."""
    results = []
    for href, raw_title in _DDG_RESULT_RE.findall(html):
        url = _decode_ddg_href(href)
        if not url:
            continue
        title = html_module.unescape(_TAG_RE.sub("", raw_title)).strip()
        results.append({"title": title or url, "url": url})
        if len(results) >= limit:
            break
    return results


async def _search_links_fallback(query: str, limit: int) -> list[dict]:
    """Quellensuche ohne Browser: DuckDuckGos HTML-Endpoint via httpx.

    Greift, wenn Playwright/Chromium fehlt oder die Selektoren der
    JS-Suchseite nichts liefern — die Recherche bleibt damit nutzbar.
    """
    url = f"https://html.duckduckgo.com/html/?q={quote_plus(query)}"
    try:
        async with httpx.AsyncClient(
            timeout=10,
            headers={"User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64)"},
            follow_redirects=True,
        ) as client:
            resp = await client.get(url)
    except Exception:
        logger.warning("HTML-Fallback-Suche fehlgeschlagen", exc_info=True)
        return []
    if resp.status_code != 200:
        logger.warning("HTML-Fallback-Suche: Status %s", resp.status_code)
        return []
    return parse_ddg_html(resp.text, limit)


async def search_links(query: str, limit: int = 4) -> list[dict]:
    """Sammelt die ersten organischen DuckDuckGo-Treffer als {title, url}.

    Grundlage des Recherche-Modus: statt den ersten Treffer zu klicken
    (``search_and_read``) werden mehrere Quellen-Links eingesammelt.
    Liefert der sichtbare Browser nichts (fehlendes Chromium, geaenderte
    Selektoren), springt der HTML-Fallback ohne Browser ein.
    """
    results: list[dict] = []
    try:
        page = await _new_page_capped()
        search_url = f"https://duckduckgo.com/?q={quote_plus(query)}"
        await page.goto(search_url, timeout=15000)
        _bring_chromium_to_front()
        await page.wait_for_timeout(2000)

        links = page.locator('[data-testid="result-title-a"]')
        count = min(await links.count(), limit)
        for i in range(count):
            link = links.nth(i)
            href = await link.get_attribute("href")
            title = (await link.inner_text()).strip()
            if href and href.startswith("http"):
                results.append({"title": title or href, "url": href})
    except Exception:
        logger.warning("Browser-Suche nach Quellen-Links fehlgeschlagen", exc_info=True)

    if results:
        return results
    logger.info("Quellensuche: Browser lieferte nichts — nutze HTML-Fallback")
    return await _search_links_fallback(query, limit)


async def visit(url: str, max_chars: int = 5000) -> dict:
    """Visit a URL and extract main text content."""
    page = await _new_page_capped()
    try:
        await page.goto(url, timeout=15000, wait_until="domcontentloaded")
        text = await page.evaluate("""
            () => {
                const selectors = ['main', 'article', '[role="main"]', '.content', '#content', 'body'];
                for (const sel of selectors) {
                    const el = document.querySelector(sel);
                    if (el && el.innerText.trim().length > 100) {
                        return el.innerText.trim();
                    }
                }
                return document.body?.innerText?.trim() || '';
            }
        """)
        title = await page.title()
        return {"title": title, "url": url, "content": text[:max_chars]}
    except Exception as e:
        return {"error": str(e), "url": url}
    finally:
        await page.close()


async def fetch_news() -> str:
    """Fetch current world news from worldmonitor.app in visible browser."""
    page = await _new_page_capped()
    try:
        await page.goto("https://www.worldmonitor.app/", timeout=20000)
        _bring_chromium_to_front()
        await page.wait_for_timeout(6000)  # Wait for JS to render
        text = await page.evaluate("() => document.body.innerText")
        # Extract the news sections
        content = text[:4000]
        return f"World Monitor Nachrichten:\n{content}"
    except Exception as e:
        return f"News konnten nicht geladen werden: {e}"
    finally:
        pass  # Keep page open so user can see it


async def open_url(url: str):
    """Open URL in the Playwright browser and bring it to front."""
    page = await _new_page_capped()
    await page.goto(url, timeout=15000, wait_until="domcontentloaded")
    _bring_chromium_to_front()
    return {"success": True, "url": url}


def status() -> dict:
    """Passiver Zustand fuer /health — startet nichts, fragt nur Globals ab."""
    return {"connected": _browser is not None and _browser.is_connected()}


async def close():
    global _pw, _browser, _context
    if _browser:
        await _browser.close()
        _browser = None
        _context = None
    if _pw:
        await _pw.stop()
        _pw = None
