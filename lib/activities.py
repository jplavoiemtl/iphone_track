from lib.geo import (
    haversine,
    haversine_with_stationary_detection,
    calculate_track_distance,
    find_movement_boundaries,
    detect_stationary_gap,
)


def parse_activities(raw_data):
    gps_points = []
    lwt_markers = []

    for item in raw_data:
        if item.get("_type") == "location":
            gps_points.append(item)
        elif item.get("_type") == "lwt" and item.get("custom") is True:
            lwt_markers.append(item)

    gps_points.sort(key=lambda x: x["tst"])
    lwt_markers.sort(key=lambda x: x["tst"])

    activities = {
        'car': [],
        'bike': [],
        'other': []
    }

    filtered_rides = {
        'car': 0,
        'bike': 0,
        'other': 0
    }

    active_activities = {}

    for marker in lwt_markers:
        activity_type = marker.get("activity", "")
        timestamp = marker["tst"]

        if activity_type == "car_start":
            active_activities['car'] = timestamp
        elif activity_type == "car_end":
            if 'car' in active_activities:
                start_time = active_activities.pop('car')
            else:
                start_time = gps_points[0]["tst"] if gps_points else timestamp
            activities['car'].append({
                'start': start_time,
                'end': timestamp,
                'points': []
            })
        elif activity_type == "bike_start":
            active_activities['bike'] = timestamp
        elif activity_type == "bike_end":
            if 'bike' in active_activities:
                start_time = active_activities.pop('bike')
            else:
                start_time = gps_points[0]["tst"] if gps_points else timestamp
            activities['bike'].append({
                'start': start_time,
                'end': timestamp,
                'points': []
            })

    if gps_points:
        last_timestamp = gps_points[-1]["tst"]
        for activity_type, start_time in active_activities.items():
            activities[activity_type].append({
                'start': start_time,
                'end': last_timestamp,
                'points': []
            })

    for point in gps_points:
        point_time = point["tst"]
        assigned = False

        for activity_type in ['car', 'bike']:
            for activity in activities[activity_type]:
                if activity['start'] <= point_time <= activity['end']:
                    activity['points'].append(point)
                    assigned = True
                    break
            if assigned:
                break

        if not assigned:
            activities['other'].append(point)

    for activity_type in ['car', 'bike']:
        original_count = len(activities[activity_type])
        activities[activity_type] = [ride for ride in activities[activity_type] if len(ride['points']) >= 5]
        filtered_rides[activity_type] = original_count - len(activities[activity_type])

    if activities['other']:
        try:
            activities['other'], filtered_rides['other'] = create_other_activity_rides(
                activities['other'], activities['car'] + activities['bike'])
        except Exception as e:
            print(f"[ERROR] Failed to process 'other' activities: {str(e)}")
            if activities['other']:
                activities['other'] = [{
                    'start': activities['other'][0]['tst'],
                    'end': activities['other'][-1]['tst'],
                    'points': activities['other']
                }]
                filtered_rides['other'] = 0
    else:
        filtered_rides['other'] = 0

    activities['_filtered_rides'] = filtered_rides
    return gps_points, activities


def process_other_ride(ride_points, min_duration_seconds):
    if not ride_points:
        return None

    start_idx, end_idx = find_movement_boundaries(ride_points)

    if start_idx is not None and end_idx is not None:
        movement_start_time = ride_points[start_idx]['tst']
        movement_end_time = ride_points[end_idx]['tst']
        movement_duration = movement_end_time - movement_start_time

        if movement_duration >= min_duration_seconds:
            ride_distance = calculate_track_distance(ride_points)
            if ride_distance >= 0.1:
                return {
                    'start': movement_start_time,
                    'end': movement_end_time,
                    'points': ride_points.copy()
                }
        return None
    else:
        fallback_duration = ride_points[-1]['tst'] - ride_points[0]['tst']
        if fallback_duration >= min_duration_seconds:
            ride_distance = calculate_track_distance(ride_points)
            if ride_distance >= 0.1:
                return {
                    'start': ride_points[0]['tst'],
                    'end': ride_points[-1]['tst'],
                    'points': ride_points.copy()
                }
        return None


def create_other_activity_rides(other_points, car_bike_activities):
    if not other_points:
        return [], 0

    try:
        all_activities = sorted(car_bike_activities, key=lambda x: x['start'])
        other_points.sort(key=lambda x: x['tst'])

        other_rides = []
        current_ride_points = []

        GAP_THRESHOLD_SECONDS = 30 * 60
        MIN_RIDE_DURATION = 5 * 60
        STATIONARY_THRESHOLD = 10

        for point in other_points:
            point_time = point['tst']
            should_start_new_ride = False

            if current_ride_points:
                last_point_time = current_ride_points[-1]['tst']

                for activity in all_activities:
                    if last_point_time < activity['start'] < point_time:
                        should_start_new_ride = True
                        break

                if not should_start_new_ride:
                    time_gap = point_time - last_point_time
                    if time_gap > GAP_THRESHOLD_SECONDS:
                        should_start_new_ride = True
                    elif not should_start_new_ride:
                        stationary_duration = detect_stationary_gap(
                            current_ride_points, GAP_THRESHOLD_SECONDS, STATIONARY_THRESHOLD)
                        if stationary_duration > GAP_THRESHOLD_SECONDS:
                            should_start_new_ride = True

            if should_start_new_ride and current_ride_points:
                processed_ride = process_other_ride(current_ride_points, MIN_RIDE_DURATION)
                if processed_ride:
                    other_rides.append(processed_ride)
                current_ride_points = []

            current_ride_points.append(point)

        if current_ride_points:
            processed_ride = process_other_ride(current_ride_points, MIN_RIDE_DURATION)
            if processed_ride:
                other_rides.append(processed_ride)

        original_count = len(other_rides)
        filtered_rides = [ride for ride in other_rides if len(ride['points']) >= 5]
        filtered_count = original_count - len(filtered_rides)

        return filtered_rides, filtered_count

    except Exception as e:
        print(f"[ERROR] Error in create_other_activity_rides: {str(e)}")
        if other_points:
            fallback_ride = [{
                'start': other_points[0]['tst'],
                'end': other_points[-1]['tst'],
                'points': other_points
            }]
            if len(other_points) >= 5:
                return fallback_ride, 0
            else:
                return [], 1
        return [], 0


def calculate_activity_stats(activities):
    stats = {}
    try:
        filtered_rides = activities.get('_filtered_rides', {'car': 0, 'bike': 0, 'other': 0})

        for activity_type, activity_data in activities.items():
            if activity_type == '_filtered_rides':
                continue

            total_distance = 0
            total_duration = 0
            total_points = 0

            for activity in activity_data:
                points = activity['points']
                activity_distance = calculate_track_distance(points)
                activity_duration = activity['end'] - activity['start']

                total_distance += activity_distance
                total_duration += activity_duration
                total_points += len(points)

            stats[activity_type] = {
                'count': len(activity_data),
                'total_distance': total_distance,
                'total_duration': total_duration,
                'total_points': total_points,
                'filtered_count': filtered_rides.get(activity_type, 0),
                'total_original_count': len(activity_data) + filtered_rides.get(activity_type, 0)
            }

        return stats

    except Exception as e:
        print(f"[ERROR] Error in calculate_activity_stats: {str(e)}")
        return {}
