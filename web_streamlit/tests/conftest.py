"""Тесты импортируют только HTTP-клиент; Streamlit и реальный API не запускаются."""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
