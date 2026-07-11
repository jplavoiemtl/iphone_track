import requests
import pytz
from datetime import datetime

from lib.markers import read_activity_markers_file


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

        start_utc = start_datetime.astimezone(pytz.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")
        end_utc = end_datetime.astimezone(pytz.UTC).strftime("%Y-%m-%dT%H:%M:%SZ")

        all_data = []
        upstream_status = "unavailable"

        locations_url = f"http://{server_ip}:{server_port}/api/0/locations"
        locations_params = {
            "user": user,
            "device": device_id,
            "from": start_utc,
            "to": end_utc
        }

        try:
            response = requests.get(locations_url, params=locations_params, timeout=30)
            if response.status_code == 200:
                data = response.json()
                if data.get("status") == 200 and isinstance(data.get("data"), list):
                    all_data.extend(data["data"])
                    upstream_status = "available"
            if upstream_status == "unavailable":
                print(f"[ERROR] OwnTracks returned HTTP {response.status_code}")
        except requests.RequestException as e:
            print(f"[ERROR] OwnTracks request failed: {str(e)}")
        except (AttributeError, TypeError, ValueError) as e:
            print(f"[ERROR] OwnTracks response was invalid: {str(e)}")

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
