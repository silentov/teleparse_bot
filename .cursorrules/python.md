1. General Guidelines
    Write concise, readable, and efficient Python code.
    Adhere to PEP 8 standards strictly.
    Use Python 3.10+ features where appropriate (e.g., match/case, X | Y for unions, list[str] for type hints instead of List[str]).
    Prefer composition over inheritance.
2. Code Style & Formatting
    Follow the formatting style of Black (line length default 88).
    Use isort for import sorting (profile: black).
    Imports order: Standard Library -> Third Party -> Local/Application.
    Always use absolute imports unless relative imports are explicitly necessary for package structure.
3. Type Hinting
    Use type hints for all function arguments and return values.
    Do not use Any unless absolutely necessary; prefer specific types or generic TypeVars.
    Use Pydantic for data validation and settings management if the project involves APIs or configuration.
    Use modern union syntax: def func(x: int | None) -> str: ...
4. Documentation
    Write docstrings for all public modules, functions, classes, and methods.
    Use Google style or NumPy style docstrings (prefer Google style for simplicity).
    Example:

    def calculate_sum(a: int, b: int) -> int:    """Calculates the sum of two integers.    Args:        a (int): The first integer.        b (int): The second integer.    Returns:        int: The sum of a and b.    """    return a + b

5. Error Handling 
     Use specific exceptions rather than catching generic Exception.
     Prefer custom exception classes for domain-specific errors.
     Use logging module instead of print statements for debugging and info messages.
6. Testing 
     Assume pytest is used for testing.
     Tests should be located in a tests/ directory mirroring the src/ structure.
     Use fixtures for repetitive setup logic.
     Aim for high test coverage on critical business logic.
7. Project Structure 
     Follow the src-layout pattern (source code in src/ or a named package directory).
     Keep __init__.py files minimal; use them to expose public API.
     Manage dependencies via pyproject.toml (Poetry, PDM, or uv).
8. Specific Libraries (Customize based on your stack) 
     FastAPI: Use dependency injection, Pydantic models for request/response, and APIRouter for organization.
     Django: Use class-based views (CBV), keep logic in models or services, avoid fat views.
     Data Science: Use Pandas/Polars idiomatically; avoid iteration over rows where vectorized operations exist.
9. Security 
     Never hardcode secrets or credentials. Use environment variables (.env) or secret managers.
     Sanitize user inputs to prevent injection attacks (SQLi, XSS).
     