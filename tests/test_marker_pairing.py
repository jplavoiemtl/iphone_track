import io
import unittest
from datetime import datetime, timezone
from unittest.mock import patch

from lib.activities import parse_activities
from lib.markers import read_activity_markers_file


def marker(kind, event, timestamp):
    return {'_type': 'lwt', 'custom': True, 'activity': kind + '_' + event,
            'tst': timestamp}


class MarkerPairingTests(unittest.TestCase):
    def test_repeated_start_and_orphan_end_do_not_capture_morning(self):
        for kind in ('car', 'bike'):
            with self.subTest(kind=kind):
                fixes = [{'_type': 'location', 'tst': t, 'lat': 0, 'lon': t / 100000}
                         for t in range(100, 1601, 50)]
                events = [marker(kind, 'start', 500), marker(kind, 'end', 800),
                          marker(kind, 'start', 1000), marker(kind, 'start', 1250),
                          marker(kind, 'end', 1400), marker(kind, 'end', 1500)]
                warnings = []
                _, activities = parse_activities(list(reversed(fixes + events)), warnings)
                self.assertEqual([(r['start'], r['end']) for r in activities[kind]],
                                 [(500, 800), (1000, 1400)])
                self.assertEqual([w['tst'] for w in warnings], [1250, 1500])
                self.assertTrue(all(p['tst'] >= 500 for r in activities[kind]
                                    for p in r['points']))

    def test_orphan_end_does_not_invent_ride(self):
        warnings = []
        _, activities = parse_activities([marker('bike', 'end', 500)], warnings)
        self.assertEqual(activities['bike'], [])
        self.assertEqual(len(warnings), 1)

    def test_boundary_context_preserves_first_open_start(self):
        content = ('{"activity":"bike_start","tst":100}\n'
                   '{"activity":"bike_start","tst":200}\n'
                   '{"activity":"car_start","tst":50}\n'
                   '{"activity":"car_end","tst":150}\n'
                   '{"activity":"bike_end","tst":700}\n')
        with patch('lib.markers.os.path.exists', return_value=True), patch(
                'builtins.open', return_value=io.StringIO(content)):
            events = read_activity_markers_file(
                datetime.fromtimestamp(300, timezone.utc),
                datetime.fromtimestamp(800, timezone.utc))
        self.assertEqual([(m['activity'], m['tst']) for m in events],
                         [('bike_start', 100), ('bike_end', 700)])
        fixes = [{'_type': 'location', 'tst': t, 'lat': 0, 'lon': t / 100000}
                 for t in range(300, 701, 50)]
        _, activities = parse_activities(fixes + events)
        self.assertEqual(len(activities['bike']), 1)
        self.assertEqual(activities['bike'][0]['points'][0]['tst'], 300)

    def test_new_start_in_range_takes_precedence_over_stale_history(self):
        content = ('{"activity":"bike_start","tst":100}\n'
                   '{"activity":"bike_start","tst":400}\n'
                   '{"activity":"bike_end","tst":700}\n')
        with patch('lib.markers.os.path.exists', return_value=True), patch(
                'builtins.open', return_value=io.StringIO(content)):
            events = read_activity_markers_file(
                datetime.fromtimestamp(300, timezone.utc),
                datetime.fromtimestamp(800, timezone.utc))
        self.assertEqual([m['tst'] for m in events], [400, 700])


if __name__ == '__main__':
    unittest.main()
