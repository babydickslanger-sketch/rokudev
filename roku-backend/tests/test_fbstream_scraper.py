import unittest
import base64
from unittest.mock import patch
from urllib.parse import parse_qs, urlparse

from scrapers import fbstream_scraper


EVENT_URL = "https://fbstream.is/live/stream/test-event"


class FakeResponse:
    def __init__(self, text: str, url: str = EVENT_URL, history=None):
        self.text = text
        self.url = url
        self.history = history or []

    def raise_for_status(self) -> None:
        pass


class FBStreamResolverTests(unittest.TestCase):
    @patch.object(fbstream_scraper.requests.Session, "get")
    def test_returns_direct_hls_source(self, get_page):
        get_page.return_value = FakeResponse(
            '<title>Test Match</title><video><source src="https://cdn.example/live.m3u8"></video>'
        )

        result = fbstream_scraper.get_fbstream_stream(EVENT_URL)

        self.assertEqual(result["streamUrl"], "https://cdn.example/live.m3u8")
        self.assertEqual(result["streamFormat"], "hls")
        get_page.assert_called_once()

    @patch.object(fbstream_scraper, "extract_stream_url")
    @patch.object(fbstream_scraper.requests.Session, "get")
    def test_resolves_supported_external_embed(self, get_page, extract_stream):
        get_page.return_value = FakeResponse(
            '<title>Provider Match</title><iframe src="https://provider.example/embed/123"></iframe>'
        )
        get_page.side_effect = [
            FakeResponse('<title>Provider Match</title><iframe src="https://provider.example/embed/123"></iframe>'),
            FakeResponse("<title>Embedded player</title>"),
        ]
        extract_stream.return_value = {
            "streamUrl": "https://cdn.example/master.m3u8",
            "streamFormat": "hls",
        }

        result = fbstream_scraper.get_fbstream_stream(EVENT_URL)

        self.assertEqual(result["streamUrl"], "https://cdn.example/master.m3u8")
        self.assertEqual(extract_stream.call_args.args[0], "https://provider.example/embed/123")

    @patch.object(fbstream_scraper.requests.Session, "get")
    def test_reports_event_without_playable_source(self, get_page):
        get_page.return_value = FakeResponse("<title>Test Match</title><p>No player</p>")

        with self.assertRaisesRegex(RuntimeError, "No direct HLS/MP4 source"):
            fbstream_scraper.get_fbstream_stream(EVENT_URL)

    @patch.object(fbstream_scraper.requests.Session, "get")
    def test_reports_tracking_redirect_instead_of_using_it_as_stream(self, get_page):
        get_page.return_value = FakeResponse(
            "<title>Advertisement</title>",
            url="https://mesclck.com/click?key=tracking",
            history=[object()],
        )

        with self.assertRaisesRegex(RuntimeError, "redirected to tracking host mesclck.com"):
            fbstream_scraper.get_fbstream_stream(EVENT_URL)

    def test_rejects_non_fbstream_url(self):
        with self.assertRaisesRegex(ValueError, "HTTPS FBStream event page"):
            fbstream_scraper.get_fbstream_stream("https://example.com/event")

    def test_builds_jwplayer_embed_url_from_event_config(self):
        page = (
            'const siteConfig = {"csrf":"csrf-value","csrf_ip":"ip-value",'
            '"sec_expires":"expiry","sec_hash":"hash"};'
            'const zmid = "zone"; const pid = 5; const edm = "fallafar.me";'
        )

        embed_url = fbstream_scraper._build_player_embed_url(page)
        parsed = urlparse(embed_url)

        self.assertEqual(parsed.hostname, "fallafar.me")
        self.assertEqual(parsed.path, "/sd0embed/sp")
        query = parse_qs(parsed.query)
        self.assertEqual(query["pid"], ["5"])
        self.assertEqual(query["v"], ["zone"])
        self.assertEqual(query["csrf"], ["csrf-value"])

    def test_decodes_player_source_lookup_path(self):
        encoded = base64.b64encode(b"source-lookup-token").decode("ascii")
        page_html = f'const a = D("{encoded}");'

        lookup_url = fbstream_scraper._extract_source_lookup_url(
            page_html, "https://fallafar.me/sd0embed/sp?pid=5"
        )

        self.assertEqual(lookup_url, "https://fallafar.me/sd0embed/source-lookup-token")


if __name__ == "__main__":
    unittest.main()