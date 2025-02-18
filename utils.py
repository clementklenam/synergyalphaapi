import logging
import math
from datetime import datetime
import numpy as np
import json

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
    """
    Clean MongoDB data: convert datetime, handle NaN/infinity values,
    and convert pandas DataFrames to dictionaries.
    Ensures all keys are strings for MongoDB compatibility.
    """
    if data is None:
        return None
    
    # Handle pandas DataFrames
    if hasattr(data, 'to_dict'):
        try:
            # Try converting to dict - handle different DataFrame formats
            if callable(data.to_dict):
                data = data.to_dict()
                # If it's a Series, it might return a simple dict
                if not isinstance(data, dict) or (isinstance(data, dict) and 'index' not in data):
                    data = {'values': data}
        except Exception as e:
            logging.error(f"Error converting DataFrame to dict: {e}")
            data = {}
    
    if isinstance(data, dict):
        # Process dictionary values recursively and ensure all keys are strings
        return {str(k): clean_mongo_data(v) for k, v in data.items()}
    
    elif isinstance(data, list):
        # Process list elements recursively
        return [clean_mongo_data(item) for item in data]
    
    elif isinstance(data, datetime):
        # Convert datetime to ISO format string
        return data.isoformat()
    
    elif isinstance(data, (float, int)):
        # Handle NaN and infinity
        try:
            if math.isnan(data) or math.isinf(data):
                return None
        except (TypeError, ValueError):
            # Handle case where isnan/isinf fails
            pass
        return data
    
    elif isinstance(data, np.datetime64):
        # Convert numpy datetime to string
        return str(data)
    
    elif hasattr(data, '__dict__'):
        # Handle custom objects by converting to dict
        return {str(k): clean_mongo_data(v) for k, v in data.__dict__.items()
                if not k.startswith('_')}
    
    # Return the data as is for strings, booleans, etc.
    return data