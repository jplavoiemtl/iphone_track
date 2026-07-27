import requests
import pytz
from datetime import datetime, timedelta

from lib.markers import read_activity_markers_file

# The recorder needs roughly 5 seconds per day of data, so a wide range in a
# single request runs past the timeout. Fetch in slices instead.
CHUNK_DAYS = 3
REQUEST_TIMEOUT = 60


def fetch_owntracks_data(start_date_str, end_date_str, start_time="00:00", end_time="23:59",
                         server_ip=None, server_port=None,
                         user="owntrcks", device_id="", target_timezone=None,
                         default_timezone="America/Montreal", return_status=False):
    try:
        time_fmt = "%Y-%m-%d %H:%M:%S" if len(start_time) > 5 else "%Y-%m-%d %H:%M"
        start_datetime = datetime.strptime(f"{start_date_str} {start_time}", time_fmt)
        time_fmt = "%Y-%m-%d %H:%M:%S" if len(end_time) > 5 else "%Y-%m-%d %H:%M"
        end_datetime = datetime.strptime(f"{end_date_str} {end_time}", time_fmt)

        if target_timezone:
            local_tz = target_timezone
        else:
            local_tz = pytz.timezone(default_timezone)

        start_datetime = local_tz.localize(start_datetime)
        end_datetime = local_tz.localize(end_datetime)

        all_data = []
        upstream_status = "available"
        seen_points = set()

        locations_url = f"http://{server_ip}:{server_port}/api/0/locations"

        # Chunk boundaries overlap by design: a duplicated point is harmless
        # (deduplicated below), a dropped one would not be.
        chunk_start = start_datetime
        while True:
            chunk_end = min(chunk_start + timedelta(days=CHUNK_DAYS), end_datetime)
            if chunk_end < chunk_start:
                chunk_end = chunk_start
            locations_params = {
                "user": user,
                "device": device_id,
                "from": chunk_start.astimezone(pytz.UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "to": chunk_end.astimezone(pytz.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
            }

            chunk_ok = False
            try:
                response = requests.get(locations_url, params=locations_params,
                                        timeout=REQUEST_TIMEOUT)
                if response.status_code == 200:
                    data = response.json()
                    if data.get("status") == 200 and isinstance(data.get("data"), list):
                        for item in data["data"]:
                            key = (item.get("tst"), item.get("lat"), item.get("lon"))
                            if key in seen_points:
                                continue
                            seen_points.add(key)
                            all_data.append(item)
                        chunk_ok = True
                if not chunk_ok:
                    print(f"[ERROR] OwnTracks returned HTTP {response.status_code}")
            except requests.RequestException as e:
                print(f"[ERROR] OwnTracks request failed: {str(e)}")
            except (AttributeError, TypeError, ValueError) as e:
                print(f"[ERROR] OwnTracks response was invalid: {str(e)}")

            # A partial track is worse than a clear failure - stop here.
            if not chunk_ok:
                upstream_status = "unavailable"
                break

            if chunk_end >= end_datetime:
                break
            chunk_start = chunk_end

        if upstream_status == "unavailable":
            if return_status:
                return None, upstream_status
            return None

        lwt_data = read_activity_markers_file(start_datetime, end_datetime)
        if lwt_data:
            all_data.extend(lwt_data)

        result = all_data if all_data else None
        if return_status:
            return result, upstream_status
        return result

    except Exception as e:
        print(f"[ERROR] Failed to fetch data: {str(e)}")
        if return_status:
            return None, "unavailable"
        return None
