import sys
from pathlib import Path

# Make the project root importable (engine/, app/) however pytest is launched.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
