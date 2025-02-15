import json
import numpy as np
from datetime import datetime
import math

class CustomJSONEncoder(json.JSONEncoder):
    def default(self, obj):
        if isinstance(obj, (np.integer, np.floating)):
            return float(obj)
        elif isinstance(obj, np.ndarray):
            return obj.tolist()
        elif isinstance(obj, datetime):
            return obj.isoformat()
        elif math.isnan(float(obj)) if isinstance(obj, (float, int)) else False:
            return None
        return super().default(obj)

def clean_mongo_data(data):
    """Clean data retrieved from MongoDB to handle non-JSON serializable values"""
    if isinstance(data, dict):
        return {k: clean_mongo_data(v) for k, v in data.items()}
    elif isinstance(data, list):
        return [clean_mongo_data(item) for item in data]
    elif isinstance(data, (float, np.floating)) and (math.isnan(data) or math.isinf(data)):
        return None
    elif isinstance(data, (np.integer, np.floating)):
        return float(data)
    elif isinstance(data, datetime):
        return data.isoformat()
    return data