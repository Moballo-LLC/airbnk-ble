# Contributing

## Development Setup

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements_test.txt
ruff check .
mypy custom_components/airbnk_ble
pytest
```
