"""Period management utilities for time series data."""


def get_period_hierarchy():
    """Get the hierarchical order of periods for upsampling validation"""
    return ["1min", "5min", "15min", "1h", "4h", "12h", "1d", "1w"]


def get_valid_periods(native_period):
    """Get list of valid periods that can be upsampled from the native period"""
    hierarchy = get_period_hierarchy()
    
    if native_period not in hierarchy:
        return hierarchy  # Default to all if unknown period
    
    native_index = hierarchy.index(native_period)
    return hierarchy[native_index:]  # Only periods >= native period


def get_period_index(period, period_list):
    """Get the index of a period in the list, return 0 if not found"""
    try:
        return period_list.index(period)
    except ValueError:
        return 0