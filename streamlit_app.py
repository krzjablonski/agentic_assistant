import sys
from pathlib import Path

_src = Path(__file__).parent / "src"
if str(_src) not in sys.path:
    sys.path.insert(0, str(_src))

from dotenv import load_dotenv
from streamlit_ui.app import main

load_dotenv(override=True)

main()
