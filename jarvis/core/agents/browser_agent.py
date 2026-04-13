#!/usr/bin/env python3
"""Browser automation agent using Safari via osascript."""
import asyncio
import subprocess


class BrowserAgent:
    async def navigate(self, url: str) -> str:
        subprocess.run(["osascript", "-e",
            f'tell application "Safari" to open location "{url}"'])
        await asyncio.sleep(2)
        return f"Navigated to {url}"

    async def get_page_text(self) -> str:
        result = subprocess.run(["osascript", "-e", """
            tell application "Safari"
                set pageText to do JavaScript "document.body.innerText.substring(0, 5000)" in document 1
                return pageText
            end tell
        """], capture_output=True, text=True, timeout=10)
        return result.stdout.strip() or "No text extracted"

    async def get_current_url(self) -> str:
        result = subprocess.run(["osascript", "-e", """
            tell application "Safari"
                return URL of document 1
            end tell
        """], capture_output=True, text=True, timeout=5)
        return result.stdout.strip()

    async def click_link(self, link_text: str) -> str:
        safe = link_text.replace("'", "\\'")
        script = f"""tell application "Safari"
            do JavaScript "var links=document.querySelectorAll('a');for(var l of links){{if(l.innerText.includes('{safe}')){{l.click();break;}}}}" in document 1
        end tell"""
        subprocess.run(["osascript", "-e", script], timeout=10)
        await asyncio.sleep(1)
        return f"Clicked link: {link_text}"

    async def fill_and_submit(self, selector: str, value: str) -> str:
        safe_val = value.replace("'", "\\'")
        safe_sel = selector.replace("'", "\\'")
        script = f"""tell application "Safari"
            do JavaScript "var el=document.querySelector('{safe_sel}');if(el){{el.value='{safe_val}';}}" in document 1
        end tell"""
        subprocess.run(["osascript", "-e", script], timeout=10)
        return f"Filled {selector} with {value}"

    async def screenshot(self) -> str:
        import time
        path = f"/tmp/browser_{int(time.time())}.png"
        subprocess.run(["screencapture", "-x", path])
        return path

    async def scroll_down(self) -> str:
        script = """tell application "Safari"
            do JavaScript "window.scrollBy(0, window.innerHeight)" in document 1
        end tell"""
        subprocess.run(["osascript", "-e", script], timeout=5)
        return "Scrolled down"


# Module-level convenience functions for TOOLS registry
_agent = BrowserAgent()

async def browser_navigate(url: str) -> str:
    return await _agent.navigate(url)

async def browser_get_page_text() -> str:
    return await _agent.get_page_text()

async def browser_get_current_url() -> str:
    return await _agent.get_current_url()

async def browser_click(link_text: str) -> str:
    return await _agent.click_link(link_text)

async def browser_fill_form(selector: str, value: str) -> str:
    return await _agent.fill_and_submit(selector, value)

async def browser_screenshot() -> str:
    path = await _agent.screenshot()
    return f"Screenshot saved: {path}"

async def browser_scroll_down() -> str:
    return await _agent.scroll_down()
