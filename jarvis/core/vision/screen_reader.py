#!/usr/bin/env python3
"""Screen reader -- capture and understand screen content via Gemma 4 multimodal."""
import asyncio
import base64
import subprocess
import time
from pathlib import Path

import requests

GEMMA_URL = "http://localhost:8081/v1/chat/completions"


class ScreenReader:

    async def capture(self) -> str:
        """Take a screenshot, return path to PNG file."""
        path = f"/tmp/screen_{int(time.time())}.png"
        subprocess.run(["screencapture", "-x", path], timeout=5)
        return path

    async def understand(self, question: str = "What do you see?") -> str:
        """Screenshot + ask Gemma 4 multimodal."""
        path = await self.capture()
        try:
            with open(path, "rb") as f:
                b64 = base64.b64encode(f.read()).decode()

            payload = {
                "messages": [{
                    "role": "user",
                    "content": [
                        {
                            "type": "image_url",
                            "image_url": {"url": f"data:image/png;base64,{b64}"}
                        },
                        {"type": "text", "text": question}
                    ]
                }],
                "max_tokens": 600,
                "temperature": 0.1,
            }
            resp = requests.post(GEMMA_URL, json=payload, timeout=60)
            return resp.json()["choices"][0]["message"]["content"]
        except Exception as e:
            return f"[screen reader error: {e}]"
        finally:
            try:
                Path(path).unlink(missing_ok=True)
            except Exception:
                pass

    async def read_error_on_screen(self) -> str:
        return await self.understand(
            "Is there an error message visible on screen? "
            "If yes, return exactly what it says. If no error, return NONE."
        )

    async def find_element(self, description: str) -> str:
        return await self.understand(
            f"Where is '{description}' on screen? "
            f"Give pixel coordinates as 'x=N y=N'. If not found, say NOT_FOUND."
        )
