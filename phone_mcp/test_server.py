"""Tests du serveur MCP, en mode simulé (aucune commande Android exécutée).

Lancer : python -m unittest phone_mcp/test_server.py
"""

import json
import os
import threading
import unittest
import urllib.error
import urllib.request
from unittest import mock

os.environ["PHONE_MCP_DRY_RUN"] = "1"

import server  # noqa: E402  (doit être importé après PHONE_MCP_DRY_RUN)

TOKEN = "jeton-de-test-0123456789"

FAKE_SEARCH_PAGE = """<html><script>var ytInitialData = {"contents": {"sectionListRenderer": {"contents": [
  {"videoRenderer": {"videoId": "jfKfPfyJRdk",
    "title": {"runs": [{"text": "lofi hip hop radio"}]},
    "ownerText": {"runs": [{"text": "Lofi Girl"}]},
    "lengthText": {"simpleText": "LIVE"}}},
  {"videoRenderer": {"videoId": "5qap5aO4i9A",
    "title": {"runs": [{"text": "beats to sleep"}]},
    "ownerText": {"runs": [{"text": "Lofi Girl"}]},
    "lengthText": {"simpleText": "1:02:03"}}}
]}}};</script></html>"""


class ServerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.httpd = server.make_server("127.0.0.1", 0, TOKEN)
        cls.base = f"http://127.0.0.1:{cls.httpd.server_address[1]}"
        threading.Thread(target=cls.httpd.serve_forever, daemon=True).start()

    @classmethod
    def tearDownClass(cls):
        cls.httpd.shutdown()

    def setUp(self):
        server.dry_run_log.clear()

    def post(self, body, path=None):
        req = urllib.request.Request(
            self.base + (path or f"/{TOKEN}/mcp"),
            data=json.dumps(body).encode(),
            headers={"Content-Type": "application/json",
                     "Accept": "application/json, text/event-stream"},
        )
        try:
            with urllib.request.urlopen(req) as resp:
                raw = resp.read()
                return resp.status, json.loads(raw) if raw else None
        except urllib.error.HTTPError as e:
            return e.code, None

    def call(self, name, arguments):
        status, resp = self.post({"jsonrpc": "2.0", "id": 7, "method": "tools/call",
                                  "params": {"name": name, "arguments": arguments}})
        self.assertEqual(status, 200)
        return resp["result"]

    def test_wrong_token_is_rejected(self):
        status, _ = self.post({"jsonrpc": "2.0", "id": 1, "method": "ping"},
                              path="/mauvais-jeton/mcp")
        self.assertEqual(status, 404)

    def test_initialize_and_list_tools(self):
        status, resp = self.post({"jsonrpc": "2.0", "id": 1, "method": "initialize",
                                  "params": {"protocolVersion": "2025-06-18",
                                             "capabilities": {},
                                             "clientInfo": {"name": "t", "version": "1"}}})
        self.assertEqual(status, 200)
        self.assertEqual(resp["result"]["protocolVersion"], "2025-06-18")
        self.assertIn("tools", resp["result"]["capabilities"])

        status, resp = self.post({"jsonrpc": "2.0", "method": "notifications/initialized"})
        self.assertEqual(status, 202)

        status, resp = self.post({"jsonrpc": "2.0", "id": 2, "method": "tools/list"})
        names = {t["name"] for t in resp["result"]["tools"]}
        self.assertEqual(names, {"youtube_play", "youtube_search", "open_url", "set_volume"})

    def test_youtube_play_with_link_opens_video(self):
        result = self.call("youtube_play", {"query": "https://youtu.be/dQw4w9WgXcQ?t=3"})
        self.assertFalse(result["isError"])
        self.assertEqual(server.dry_run_log[0][-1], "https://www.youtube.com/watch?v=dQw4w9WgXcQ")

    def test_youtube_play_with_search_plays_first_result(self):
        with mock.patch.object(server, "fetch_search_page", return_value=FAKE_SEARCH_PAGE):
            result = self.call("youtube_play", {"query": "lofi"})
        self.assertFalse(result["isError"])
        self.assertIn("lofi hip hop radio", result["content"][0]["text"])
        self.assertEqual(server.dry_run_log[0][-1], "https://www.youtube.com/watch?v=jfKfPfyJRdk")

    def test_youtube_search_lists_results(self):
        with mock.patch.object(server, "fetch_search_page", return_value=FAKE_SEARCH_PAGE):
            result = self.call("youtube_search", {"query": "lofi"})
        text = result["content"][0]["text"]
        self.assertIn("1. lofi hip hop radio — Lofi Girl (LIVE) [id: jfKfPfyJRdk]", text)
        self.assertIn("2. beats to sleep", text)
        self.assertEqual(server.dry_run_log, [])  # la recherche ne lance rien

    def test_open_url_rejects_other_schemes(self):
        result = self.call("open_url", {"url": "tel:0600000000"})
        self.assertTrue(result["isError"])
        self.assertEqual(server.dry_run_log, [])

    def test_set_volume(self):
        result = self.call("set_volume", {"percent": 60})
        self.assertFalse(result["isError"])
        self.assertEqual(server.dry_run_log[0], ["termux-volume", "music", "9"])

    def test_extract_youtube_id(self):
        cases = {
            "https://www.youtube.com/watch?v=dQw4w9WgXcQ&list=x": "dQw4w9WgXcQ",
            "https://m.youtube.com/shorts/dQw4w9WgXcQ": "dQw4w9WgXcQ",
            "dQw4w9WgXcQ": "dQw4w9WgXcQ",
            "musique relaxante": None,
            "https://example.com/watch?v=dQw4w9WgXcQ": None,
        }
        for text, expected in cases.items():
            self.assertEqual(server.extract_youtube_id(text), expected, text)


if __name__ == "__main__":
    unittest.main()
