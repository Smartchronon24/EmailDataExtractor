import json
import pandas as pd
import os
from config import PROCESSED_DATA_PATH

def convert_json_to_csv(json_file_path):
    """Converts a JSON file to a CSV file."""
    # Handle the case where the path might have a prefix that doesn't exist relative to the current dir
    if not os.path.exists(json_file_path):
        # Try looking for just the filename in the current directory
        filename = os.path.basename(json_file_path)
        if os.path.exists(filename):
            json_file_path = filename
        else:
            print(f"File not found: {json_file_path}")
            return

    print(f"Converting {json_file_path} to CSV...")
    
    try:
        with open(json_file_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
        
        # Ensure data is a list of objects
        if isinstance(data, list):
            df = pd.json_normalize(data)
        elif isinstance(data, dict):
            df = pd.json_normalize([data])
        else:
            print(f"Unsupported JSON structure in {json_file_path}")
            return

        csv_file_path = json_file_path.replace('.json', '.csv')
        df.to_csv(csv_file_path, index=False)
        print(f"Successfully created: {csv_file_path}")

    except Exception as e:
        print(f"Error converting {json_file_path}: {e}")

if __name__ == "__main__":
    # Only convert processed emails as requested
    convert_json_to_csv(PROCESSED_DATA_PATH)
