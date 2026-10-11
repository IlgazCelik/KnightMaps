import csv
import glob
import json
import os
import re

# 1. Find all JSON files matching the pattern
json_files = glob.glob('vectors/wifi_scan_*.json')

if not json_files:
    print("No files found matching 'wifi_scan_*.json'. Please check your path.")
    exit()

all_bssids = set()
file_records = []

# 2. First pass: Read all files to gather every unique BSSID and coordinate ID
for file_path in json_files:
    filename = os.path.basename(file_path)
    match = re.search(r'wifi_scan_(.+)\.json', filename)
    if not match:
        continue

    scan_id = match.group(1).replace('_', ',')

    with open(file_path, 'r', encoding='utf-8') as f:
        data = json.load(f)

    bssid_map = {item['bssid']: item['rssi'] for item in data}
    all_bssids.update(bssid_map.keys())

    file_records.append({'id': scan_id, 'bssid_map': bssid_map})

# Sort BSSIDs alphabetically for consistent feature column order
sorted_bssids = sorted(list(all_bssids))
file_records.sort(key=lambda x: x['id'])

# 3. Second pass: Write data to CSV (id as first column, BSSIDs as columns)
output_csv = 'wifi_scans_dataset.csv'
header = ['id'] + sorted_bssids

with open(output_csv, 'w', newline='', encoding='utf-8') as f:
    writer = csv.writer(f)
    writer.writerow(header)

    for record in file_records:
        row = [record['id']]
        bssid_map = record['bssid_map']

        for bssid in sorted_bssids:
            row.append(bssid_map.get(bssid, ''))

        writer.writerow(row)

print(
    f'Successfully processed {len(file_records)} files into {output_csv} with'
    f' {len(sorted_bssids)} BSSID feature columns.'
)