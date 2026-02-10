import sys
import os

# Add the current directory to sys.path to allow imports from streamlit_cotizador
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

from streamlit_cotizador.app import main

if __name__ == "__main__":
    main()
