# Testing Guide

Comprehensive testing guide for the AI Vector Service project.

### **Test Dependencies**

Required packages (from requirements.txt):

* pytest \- Testing framework  
* pytest-cov \- Coverage reporting  
* pytest-asyncio \- Async test support

### **Test Structure**

```
tests/
├── __init__.py
├── conftest.py              # Shared fixtures and configuration
├── test_api.py              # API endpoint tests
└── logger/
    └── test_logger.py       # Test logging utilities
```

## **Running Tests**

### **Basic Test Execution**

```
# Run all tests
pytest

# Run with verbose output
pytest -v

# Run specific test file
pytest tests/test_api.py

# Run specific test class
pytest tests/test_api.py::TestHealthCheck

# Run specific test function
pytest tests/test_api.py::TestHealthCheck::test_health_check_success
```

### **Coverage Reports**

```
# Run tests with coverage
pytest --cov=app

# Generate HTML coverage report
pytest --cov=app --cov-report=html

# View coverage report
open htmlcov/index.html  # macOS
xdg-open htmlcov/index.html  # Linux
```

### **Coverage Output Formats**

```
# Terminal output with missing lines
pytest --cov=app --cov-report=term-missing

# XML report (for CI/CD)
pytest --cov=app --cov-report=xml

# HTML report (for detailed analysis)
pytest --cov=app --cov-report=html
```

### **Running Specific Tests**

```
# Run tests matching a pattern
pytest -k "health"

# Run tests with specific markers (if defined)
pytest -m "slow"

# Run failed tests from last run
pytest --lf

# Run failed tests first, then others
pytest --ff
```
