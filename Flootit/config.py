"""Configuration constants for the Flood-It bot."""

CLICK_DELAY_MS = 300           # Delay between auto-clicks (milliseconds)
LOOKAHEAD_DEPTH = 3            # Lookahead depth (applies full sequence per window)
COLOR_DISTANCE_THRESHOLD = 50  # Max Euclidean distance for color matching
REGION_FILE = "region.json"    # Persist selected region between runs
CALIBRATION_FILE = "calibration.json"  # Persist button positions
