import unittest

from lib.activities import (
    calculate_activity_stats,
    parse_activities,
    ride_stat_window,
)


def point(tst, lat=45.5, lon=-73.6):
    return {"_type": "location", "tst": tst, "lat": lat, "lon": lon}


def moving_points(start_tst, count, step_seconds=30, lat_step=0.0015):
    """Points that advance ~165m per step, well over the 10m stationary gate."""
    return [point(start_tst + i * step_seconds, 45.5 + i * lat_step)
            for i in range(count)]


def stationary_points(start_tst, count, step_seconds=30, lat=45.5):
    """Points that never move more than 10m, so they add no distance."""
    return [point(start_tst + i * step_seconds, lat) for i in range(count)]


class RideStatWindowTests(unittest.TestCase):
    """The stat window is the intersection of the declared window and the
    span of the GPS points, which resolves differently per activity type."""

    def test_marker_window_wider_than_points_clamps_to_fixes(self):
        # car/bike: markers fire before the first fix and after the last one
        ride = {"start": 1000, "end": 2000,
                "points": [point(1150), point(1800)]}
        self.assertEqual(ride_stat_window(ride), (1150, 1800))

    def test_movement_window_narrower_than_points_clamps_to_movement(self):
        # other: start/end are trimmed to movement, points keep the stationary
        # head and tail
        ride = {"start": 1150, "end": 1800,
                "points": [point(1000), point(1150), point(1800), point(2000)]}
        self.assertEqual(ride_stat_window(ride), (1150, 1800))

    def test_identical_window_and_points_is_unchanged(self):
        ride = {"start": 1000, "end": 2000,
                "points": [point(1000), point(2000)]}
        self.assertEqual(ride_stat_window(ride), (1000, 2000))

    def test_empty_points_falls_back_to_declared_window(self):
        self.assertEqual(
            ride_stat_window({"start": 1000, "end": 2000, "points": []}),
            (1000, 2000))

    def test_missing_points_key_falls_back_to_declared_window(self):
        self.assertEqual(
            ride_stat_window({"start": 1000, "end": 2000}), (1000, 2000))

    def test_single_point_ride_yields_zero_duration(self):
        ride = {"start": 1000, "end": 2000, "points": [point(1500)]}
        start, end = ride_stat_window(ride)
        self.assertEqual(end - start, 0)


class BikeRideDurationTests(unittest.TestCase):
    """Regression test built from the real ride of 2026-07-31.

    bike_start fired at 09:47:07, the first GPS fix landed at 09:49:41, the
    last fix at 10:33:54 and bike_end at 10:37:02. Duration must be measured
    between the fixes (2653s = 44m13s), not from the marker (2807s = 46m47s).
    """

    BIKE_START_MARKER = 1785505627
    FIRST_FIX = 1785505781
    LAST_FIX = 1785508434
    BIKE_END_MARKER = 1785508622

    def build(self):
        raw = [
            {"_type": "lwt", "custom": True, "activity": "bike_start",
             "tst": self.BIKE_START_MARKER},
            {"_type": "lwt", "custom": True, "activity": "bike_end",
             "tst": self.BIKE_END_MARKER},
        ]
        span = self.LAST_FIX - self.FIRST_FIX
        count = 90
        step = span // (count - 1)
        raw += moving_points(self.FIRST_FIX, count, step_seconds=step)
        # Pin the final point to the real last-fix timestamp
        raw[-1]["tst"] = self.LAST_FIX
        return raw

    def test_duration_spans_the_fixes_not_the_markers(self):
        _, activities = parse_activities(self.build())
        stats = calculate_activity_stats(activities)

        self.assertEqual(stats["bike"]["count"], 1)
        self.assertEqual(stats["bike"]["total_duration"],
                         self.LAST_FIX - self.FIRST_FIX)
        self.assertEqual(stats["bike"]["total_duration"], 2653)

    def test_marker_window_is_still_used_for_segmentation(self):
        _, activities = parse_activities(self.build())
        ride = activities["bike"][0]

        self.assertEqual(ride["start"], self.BIKE_START_MARKER)
        self.assertEqual(ride["end"], self.BIKE_END_MARKER)


class OtherRideDurationTests(unittest.TestCase):
    """Walking rides keep their stationary tail in 'points'. Measuring to
    points[-1] re-added the tail that find_movement_boundaries() trimmed."""

    def test_stationary_tail_is_excluded_from_duration(self):
        base = 1785600000
        walk = moving_points(base, 30)  # 30 fixes, 30s apart -> 870s of walking
        last_moving_tst = walk[-1]["tst"]
        # Stand still for 10 minutes at the end, still inside the same ride
        tail = stationary_points(last_moving_tst + 30, 20,
                                 lat=walk[-1]["lat"])

        _, activities = parse_activities(walk + tail)
        stats = calculate_activity_stats(activities)

        self.assertEqual(stats["other"]["count"], 1)
        ride = activities["other"][0]
        self.assertEqual(stats["other"]["total_duration"],
                         ride["end"] - ride["start"])
        self.assertEqual(stats["other"]["total_duration"],
                         last_moving_tst - walk[0]["tst"])
        # The tail is still present in points -- walking end detection needs it
        self.assertEqual(ride["points"][-1]["tst"], tail[-1]["tst"])

    def test_stationary_tail_does_not_deflate_average_speed(self):
        base = 1785600000
        walk = moving_points(base, 30)
        tail = stationary_points(walk[-1]["tst"] + 30, 20, lat=walk[-1]["lat"])

        _, with_tail = parse_activities(walk + tail)
        _, without_tail = parse_activities(list(walk))

        a = calculate_activity_stats(with_tail)["other"]
        b = calculate_activity_stats(without_tail)["other"]

        self.assertEqual(a["total_duration"], b["total_duration"])
        self.assertAlmostEqual(a["total_distance"], b["total_distance"], places=6)


if __name__ == "__main__":
    unittest.main()
