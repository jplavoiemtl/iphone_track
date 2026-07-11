import unittest
from unittest.mock import Mock, patch

import requests

from lib.owntracks import fetch_owntracks_data


class FetchOwnTracksStatusTests(unittest.TestCase):
    def setUp(self):
        self.kwargs = {
            "start_date_str": "2026-07-11",
            "end_date_str": "2026-07-11",
            "server_ip": "example.invalid",
            "server_port": "8083",
            "return_status": True,
        }

    @patch("lib.owntracks.read_activity_markers_file", return_value=[])
    @patch("lib.owntracks.requests.get")
    def test_reachable_empty_response_is_available(self, get, _markers):
        response = Mock(status_code=200)
        response.json.return_value = {"status": 200, "data": []}
        get.return_value = response

        data, status = fetch_owntracks_data(**self.kwargs)

        self.assertIsNone(data)
        self.assertEqual(status, "available")

    @patch("lib.owntracks.read_activity_markers_file", return_value=[])
    @patch("lib.owntracks.requests.get")
    def test_request_failure_is_unavailable(self, get, _markers):
        get.side_effect = requests.ConnectionError("unreachable")

        data, status = fetch_owntracks_data(**self.kwargs)

        self.assertIsNone(data)
        self.assertEqual(status, "unavailable")

    @patch("lib.owntracks.read_activity_markers_file", return_value=[])
    @patch("lib.owntracks.requests.get")
    def test_legacy_caller_still_receives_data_only(self, get, _markers):
        response = Mock(status_code=200)
        response.json.return_value = {"status": 200, "data": []}
        get.return_value = response
        legacy_kwargs = dict(self.kwargs)
        legacy_kwargs.pop("return_status")

        self.assertIsNone(fetch_owntracks_data(**legacy_kwargs))


if __name__ == "__main__":
    unittest.main()
