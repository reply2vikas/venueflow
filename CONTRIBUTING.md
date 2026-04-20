# Contributing to VenueFlow

## Code Standards

All Python code must follow these standards:

### Docstrings
Every module, class, and public function must have a Google-style docstring:

```python
def my_function(param: str) -> int:
    """One-line summary.

    Longer description if needed.

    Args:
        param: Description of the parameter.

    Returns:
        Description of the return value.

    Raises:
        ValueError: If param is empty.
    """
```

### Type Hints
All function signatures must have complete type hints:
```python
async def get_zones(zone_id: str) -> List[ZoneDensityResponse]:
```

### Imports
Order: stdlib → third-party → local. One blank line between groups.

### Testing
- Every public function must have at least one test
- Tests must be fully independent (no shared state)
- All external APIs must be mocked

## Running Tests
```bash
pytest tests/ -v --cov=api --cov-report=term-missing
```

## Running Linting
```bash
ruff check api/ tests/
```
