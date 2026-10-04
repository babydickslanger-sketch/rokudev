from unittest import mock
from urllib.parse import parse_qs, urlparse
import unittest

from fastapi import HTTPException

from utils import playback_proxy
from utils.playback_proxy import (
    _PLAYBACK_SESSIONS,
    _decode_session_context,
    _describe_resource,
    _log_hls_key_diagnostics,
    _select_hls_variant,
    _is_fbstream_session,
    build_proxy_url,
    _claim_codec_probe,
    _log_hls_playlist_diagnostics,
    _log_transport_stream_diagnostics,
    _log_transport_stream_codecs,
    proxy_playback_request,
    register_playback_session,
    rewrite_m3u8_playlist,
    _safe_resource_url,
)


class FakeUpstreamResponse:
    def __init__(self, content: bytes, content_type: str, status_code: int = 200):
        self.content = content
        self.status_code = status_code
        self.headers = {"Content-Type": content_type}
        self.encoding = "utf-8"


class FakeRequest:
    headers = {}

    def url_for(self, name: str, **kwargs) -> str:
        if name == "fbstream_proxy":
            return f"http://backend.local/api/fbstream/proxy/{kwargs['playback_id']}"
        if name == "fbstream_proxy_named":
            return f"http://backend.local/api/fbstream/proxy/{kwargs['playback_id']}/{kwargs['resource_name']}"
        raise AssertionError(f"Unexpected route name: {name}")


class PlaybackProxyTests(unittest.TestCase):
    def setUp(self):
        _PLAYBACK_SESSIONS.clear()

    def test_register_playback_session_returns_proxied_url(self):
        stream_info = {
            "title": "Test Event",
            "streamUrl": "https://cdn.example/live/master.m3u8?token=abc",
            "streamFormat": "hls",
            "httpHeaders": {"Referer": "https://fbstream.is/event/test"},
            "extractor": "playwright",
        }

        payload = register_playback_session(FakeRequest(), "https://fbstream.is/event/test", stream_info)

        self.assertTrue(payload["streamUrl"].startswith("http://backend.local/api/fbstream/proxy/"))
        self.assertEqual(payload["playbackUrl"], payload["streamUrl"])
        self.assertEqual(payload["directStreamUrl"], stream_info["streamUrl"])
        self.assertEqual(payload["proxyMode"], "hls-rewrite")

        query = parse_qs(urlparse(payload["streamUrl"]).query)
        self.assertEqual(query["url"][0], stream_info["streamUrl"])
        decoded_context = _decode_session_context(query["ctx"][0])
        self.assertEqual(decoded_context["sourcePageUrl"], "https://fbstream.is/event/test")
        self.assertEqual(decoded_context["httpHeaders"]["Referer"], "https://fbstream.is/event/test")

    def test_rewrite_m3u8_playlist_rewrites_segments_and_keys(self):
        playlist = """#EXTM3U
#EXT-X-VERSION:3
#EXT-X-KEY:METHOD=AES-128,URI=\"key.key\"
#EXTINF:6.0,
segment1.ts
#EXTINF:6.0,
https://cdn.example/segment2.ts
"""

        rewritten = rewrite_m3u8_playlist(
            playlist,
            "https://cdn.example/live/master.m3u8?token=abc",
            lambda url: f"http://backend.local/proxy?url={url}",
        )

        self.assertIn('URI="http://backend.local/proxy?url=https://cdn.example/live/key.key"', rewritten)
        self.assertIn("http://backend.local/proxy?url=https://cdn.example/live/segment1.ts", rewritten)
        self.assertIn("http://backend.local/proxy?url=https://cdn.example/segment2.ts", rewritten)

    def test_hls_master_selects_highest_variant_under_roku_height_limit(self):
        master = """#EXTM3U
#EXT-X-VERSION:4
#EXT-X-INDEPENDENT-SEGMENTS
#EXT-X-STREAM-INF:BANDWIDTH=3750000,RESOLUTION=1280x720,CODECS="avc1.4d401f,mp4a.40.2"
high.m3u8
#EXT-X-STREAM-INF:BANDWIDTH=1200000,RESOLUTION=864x480,CODECS="avc1.4d401f,mp4a.40.2"
mid.m3u8
#EXT-X-STREAM-INF:BANDWIDTH=550000,RESOLUTION=432x240,CODECS="avc1.4d4015,mp4a.40.2"
low.m3u8
"""

        selected_playlist, selected = _select_hls_variant(master, 486)

        self.assertEqual(selected, {
            "resolution": "864x480",
            "bandwidth": "1200000",
            "codecs": "avc1.4d401f,mp4a.40.2",
        })
        self.assertIn("#EXT-X-VERSION:4", selected_playlist)
        self.assertIn("#EXT-X-INDEPENDENT-SEGMENTS", selected_playlist)
        self.assertIn("mid.m3u8", selected_playlist)
        self.assertNotIn("high.m3u8", selected_playlist)
        self.assertNotIn("low.m3u8", selected_playlist)

    def test_hls_variant_selection_leaves_unknown_or_over_limit_master_unchanged(self):
        master = """#EXTM3U
#EXT-X-STREAM-INF:BANDWIDTH=3750000,RESOLUTION=1280x720
high.m3u8
"""

        selected_playlist, selected = _select_hls_variant(master, 486)

        self.assertIsNone(selected)
        self.assertEqual(selected_playlist, master)

    def test_only_fbstream_playback_sessions_use_roku_variant_cap(self):
        self.assertTrue(_is_fbstream_session({"sourcePageUrl": "https://fbstream.is/live/event"}))
        self.assertFalse(_is_fbstream_session({"sourcePageUrl": "https://movie.example/title"}))

    def test_hls_diagnostics_log_codecs_and_key_method_without_key_uri(self):
        playlist = """#EXTM3U
#EXT-X-VERSION:3
#EXT-X-STREAM-INF:BANDWIDTH=2400000,RESOLUTION=1280x720,CODECS="avc1.64001f,mp4a.40.2"
variant.m3u8
#EXT-X-KEY:METHOD=AES-128,URI="https://cdn.example/private-key?token=secret"
"""

        with self.assertLogs(playback_proxy.logger, level="INFO") as captured:
            _log_hls_playlist_diagnostics("playback123", playlist)

        output = "\n".join(captured.output)
        self.assertIn("avc1.64001f,mp4a.40.2", output)
        self.assertIn("'METHOD': 'AES-128'", output)
        self.assertNotIn("private-key", output)
        self.assertNotIn("token=secret", output)

    def test_hls_diagnostics_correlate_key_and_encrypted_segment_requests(self):
        playlist = """#EXTM3U
#EXT-X-TARGETDURATION:6
#EXT-X-MEDIA-SEQUENCE:25
#EXT-X-KEY:METHOD=AES-128,URI="key.bin",IV=0x00000000000000000000000000000019
#EXTINF:6.0,
segment.ts
"""
        session = {"hlsResources": {}}

        _log_hls_playlist_diagnostics(
            "playback123",
            playlist,
            "https://cdn.example/live/index.m3u8?token=private",
            session,
        )

        key = _describe_resource(session, "https://cdn.example/live/key.bin")
        segment = _describe_resource(session, "https://cdn.example/live/segment.ts")
        self.assertEqual(key["kind"], "key")
        self.assertEqual(key["method"], "AES-128")
        self.assertEqual(segment["kind"], "segment")
        self.assertEqual(segment["encryption"]["METHOD"], "AES-128")
        self.assertEqual(segment["encryption"]["IV"], "0x00000000000000000000000000000019")

    def test_resource_logging_redacts_query_values(self):
        self.assertEqual(
            _safe_resource_url("https://cdn.example/live/segment.ts?token=secret&sig=private"),
            "https://cdn.example/live/segment.ts?<redacted>",
        )

    def test_key_and_transport_stream_diagnostics_report_encryption_readiness(self):
        with self.assertLogs(playback_proxy.logger, level="INFO") as captured:
            _log_hls_key_diagnostics("playback123", "https://cdn.example/key?token=secret", b"1234567890123456", {
                "method": "AES-128",
                "keyformat": "identity",
            })
            _log_transport_stream_diagnostics("playback123", b"\x47" + b"\0" * 187, {
                "METHOD": "AES-128",
                "IV": "0x01",
            })

        output = "\n".join(captured.output)
        self.assertIn("valid_length=True", output)
        self.assertIn("encrypted=True", output)
        self.assertIn("sync_byte_valid=True", output)
        self.assertNotIn("token=secret", output)

    @mock.patch.object(playback_proxy.shutil, "which", return_value="ffprobe")
    @mock.patch.object(
        playback_proxy.subprocess,
        "run",
        return_value=mock.Mock(
            returncode=0,
            stdout=b'{"streams":[{"codec_type":"video","codec_name":"h264","width":1280,"height":720}]}',
            stderr=b"",
        ),
    )
    def test_transport_stream_codec_probe_logs_stream_details(self, run_probe, _which):
        with self.assertLogs(playback_proxy.logger, level="INFO") as captured:
            _log_transport_stream_codecs("playback123", b"transport stream")

        run_probe.assert_called_once()
        self.assertIn("'codec_name': 'h264'", captured.output[0])
        self.assertIn("'width': 1280", captured.output[0])

    def test_codec_probe_is_claimed_only_once_per_session(self):
        _PLAYBACK_SESSIONS["playback123"] = {"playbackId": "playback123"}

        self.assertTrue(_claim_codec_probe("playback123"))
        self.assertFalse(_claim_codec_probe("playback123"))

    def test_build_proxy_url_embeds_context_for_recovery(self):
        session = {
            "playbackId": "playback123",
            "sourcePageUrl": "https://fbstream.is/event/test",
            "directStreamUrl": "https://cdn.example/live/master.m3u8?token=abc",
            "streamFormat": "hls",
            "title": "Test Event",
            "httpHeaders": {"Referer": "https://fbstream.is/event/test", "User-Agent": "Test UA"},
            "extractor": "playwright",
        }

        proxied = build_proxy_url(
            FakeRequest(),
            "playback123",
            "https://cdn.example/live/segment1.ts?token=abc",
            session=session,
            include_target_url=True,
        )

        parsed = urlparse(proxied)
        query = parse_qs(parsed.query)
        self.assertEqual(query["url"][0], "https://cdn.example/live/segment1.ts?token=abc")
        decoded_context = _decode_session_context(query["ctx"][0])
        self.assertEqual(decoded_context["directStreamUrl"], session["directStreamUrl"])
        self.assertEqual(decoded_context["httpHeaders"]["User-Agent"], "Test UA")

    def test_proxy_restores_session_from_context_after_memory_loss(self):
        stream_info = {
            "title": "Test Event",
            "streamUrl": "https://cdn.example/live/master.m3u8?token=abc",
            "streamFormat": "hls",
            "httpHeaders": {"Referer": "https://fbstream.is/event/test", "User-Agent": "Test UA"},
            "extractor": "playwright",
        }
        payload = register_playback_session(FakeRequest(), "https://fbstream.is/event/test", stream_info)
        playback_id = payload["playbackId"]
        query = parse_qs(urlparse(payload["streamUrl"]).query)
        ctx = query["ctx"][0]

        # Simulate the session vanishing (restart, eviction, or expiry) mid-playback.
        _PLAYBACK_SESSIONS.clear()

        with self.assertRaises(HTTPException) as raised:
            proxy_playback_request(FakeRequest(), playback_id, stream_info["streamUrl"], None, None)
        self.assertEqual(raised.exception.status_code, 404)

        captured = {}

        def fake_fetch(request, session, upstream_url):
            captured["headers"] = dict(session.get("httpHeaders") or {})
            captured["url"] = upstream_url
            return FakeUpstreamResponse(b"#EXTM3U\n#EXTINF:6.0,\nsegment1.ts\n", "application/vnd.apple.mpegurl")

        with mock.patch.object(playback_proxy, "_fetch_upstream_resource", side_effect=fake_fetch):
            response = proxy_playback_request(FakeRequest(), playback_id, stream_info["streamUrl"], None, ctx)

        self.assertEqual(response.status_code, 200)
        self.assertEqual(captured["url"], stream_info["streamUrl"])
        self.assertEqual(captured["headers"]["User-Agent"], "Test UA")
        self.assertEqual(captured["headers"]["Referer"], "https://fbstream.is/event/test")
        self.assertIn(playback_id, _PLAYBACK_SESSIONS)

        body = response.body.decode("utf-8")
        segment_line = [line for line in body.splitlines() if "segment1.ts" in line][0]
        segment_query = parse_qs(urlparse(segment_line).query)
        self.assertEqual(segment_query["url"][0], "https://cdn.example/live/segment1.ts")
        self.assertEqual(_decode_session_context(segment_query["ctx"][0])["directStreamUrl"], stream_info["streamUrl"])

    def test_proxy_rejects_garbage_context_token(self):
        with self.assertRaises(HTTPException) as raised:
            proxy_playback_request(FakeRequest(), "missing", "https://cdn.example/live/master.m3u8", None, "!!!not-base64!!!")
        self.assertEqual(raised.exception.status_code, 404)


if __name__ == "__main__":
    unittest.main()
