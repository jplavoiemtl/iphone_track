import json
import os


def read_activity_markers_file(start_datetime, end_datetime):
    try:
        script_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
        markers_file = os.path.join(script_dir, "GPS_activity_markers.json")

        if not os.path.exists(markers_file):
            return []

        start_timestamp = int(start_datetime.timestamp())
        end_timestamp = int(end_datetime.timestamp())

        lwt_items = []

        with open(markers_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line:
                    continue
                try:
                    marker = json.loads(line)
                    if "activity" in marker and "tst" in marker:
                        marker_timestamp = marker["tst"]
                        activity = marker["activity"]
                        if start_timestamp <= marker_timestamp <= end_timestamp:
                            full_marker = {
                                "_type": "lwt",
                                "tst": marker_timestamp,
                                "custom": True,
                                "activity": activity
                            }
                            lwt_items.append(full_marker)
                except json.JSONDecodeError:
                    continue
                except Exception:
                    continue

        lwt_items.sort(key=lambda x: x["tst"])
        return lwt_items

    except Exception as e:
        print(f"[ERROR] Error reading activity markers file: {str(e)}")
        return []
