# Developer Guide

This guide provides detailed instructions for developers who want to contribute to or extend the AI Vector Service.

## **Development Setup**

### **Prerequisites**

* Python 3.8 or higher  
* pip (Python package manager)  
* Git  
* Qdrant (vector database)  
* Redis (cache server)  
* PostgreSQL (optional, for translation features)

### **Setting Up Development Environment**

#### **1\. Clone the Repository**

```
git clone <repository-url>
cd ai-vector-service
```

#### 

#### 

#### 

#### **2\. Create Virtual Environment**

```
# Create virtual environment
python3 -m venv .venv

# Activate virtual environment
# On macOS/Linux:
source .venv/bin/activate
```

#### **3\. Install Dependencies**

```
# Install all dependencies
pip install -r requirements.txt

# Verify installation
pip list
```

#### **4\. Install Qdrant**

**Option 1: Using Docker (Recommended)**

```
docker pull qdrant/qdrant
docker run -p 6333:6333 -p 6334:6334 \-v qdrant_data:/qdrant/storage qdrant/qdrant
```

**Option 2: Local Installation**

Follow instructions at: [https://qdrant.tech/documentation/quick-start/](https://qdrant.tech/documentation/quick-start/)

#### **5\. Install Redis**

**On macOS:**

```
brew install redis
brew services start redis
```

**On Ubuntu/Debian:**

```
sudo apt-get install redis-server
sudo systemctl start redis
```

**Using Docker:**

```
docker run -d -p 6379:6379 redis:latest
```

#### **6\. Install PostgreSQL (Optional)**

**On macOS:**

```
brew install postgresql
brew services start postgresql
```

**On Ubuntu/Debian:**

```
sudo apt-get install postgresql
sudo systemctl start postgresql
```

#### **7\. Configure Environment**

```
# Copy sample environment file
cp .env.sample .env

# Edit .env with your configuration
nano .env  # or use your preferred editor
```

**Minimum Configuration:**

```
# Qdrant
QDRANT_HOST=127.0.0.1
QDRANT_PORT=6333

# Redis
REDIS_HOST=localhost
REDIS_PORT=6379

# Environment
ENVIRONMENT=local
```

#### **8\. Verify Setup**

```
# Start the application
python -m uvicorn app.main:app --reload

# In another terminal, test health endpoint
curl http://localhost:8000/api/health
```

Expected output:

```
{
  "status": "healthy",
  "services": {
    "qdrant": "connected",
    "redis": "connected"
  }
}
```

## 

## 

## **Project Structure**

```
ai-vector-service/
├── app/                          # Main application package
│   ├── api/                      # API layer
│   │   └── v1/                   # API version 1
│   │       ├── endpoints/        # API endpoint handlers
│   │       │   ├── documents.py  # Document management endpoints
│   │       │   ├── query.py      # Query endpoints
│   │       │   └── cache.py      # Cache management endpoints
│   │       └── api.py            # API router configuration
│   │
│   ├── core/                     # Core functionality
│   │   ├── clients/              # External service clients
│   │   │   ├── qdrant.py         # Qdrant client and operations
│   │   │   ├── redis_cache.py    # Redis cache implementation
│   │   │   └── embedding.py      # Embedding model wrapper
│   │   └── database.py           # Database connection
│   │
│   ├── models/                   # Data models
│   │   ├── api_models.py         # Pydantic models for API
│   │   └── db_models.py          # SQLAlchemy models for DB
│   │
│   ├── services/                 # Business logic
│   │   ├── document_operations/  # Document CRUD operations
│   │   │   ├── base_operation.py
│   │   │   ├── upload_service.py
│   │   │   ├── update_service.py
│   │   │   ├── delete_service.py
│   │   │   └── metadata_service.py
│   │   │
│   │   ├── file_processors/      # File format processors
│   │   │   ├── base_processor.py
│   │   │   ├── pdf_processor.py
│   │   │   ├── docx_processor.py
│   │   │   ├── text_processor.py
│   │   │   ├── csv_processor.py
│   │   │   └── xlsx_processor.py
│   │   │
│   │   ├── document_processor.py # Main document processor
│   │   ├── query_service.py      # Query processing
│   │   ├── prioritized_search_service.py
│   │   ├── text_embedding_search_service.py
│   │   ├── similarity_service.py
│   │   └── url_text_extractor.py
│   │
│   ├── utils/                    # Utility functions
│   │   ├── json_handler.py
│   │   └── language_utils.py
│   │
│   ├── config.py                 # Configuration settings
│   └── main.py                   # Application entry point
│
├── tests/                        # Test suite
│   ├── conftest.py               # Test configuration
│   ├── test_api.py               # API tests
│   └── logger/                   # Test logging
│
├── scripts/                      # Utility scripts
│   ├── insert_document.py        # Document insertion script
│   ├── data_insert_script.py     # Batch data insertion
│   └── quick_insert_example.py   # Quick test script
│
├── .env.sample                   # Environment variables template
├── .gitignore                    # Git ignore rules
├── requirements.txt              # Python dependencies
├── pytest.ini                    # Pytest configuration
└── README.md                     # Project documentation
```

## **Development Workflow**

### **1\. Create a Feature Branch**

```
git checkout -b feature/your-feature-name
```

### **2\. Make Changes**

Edit code, add features, fix bugs, etc.

### **3\. Run Tests**

```
# Run all tests
pytest

# Run specific test file
pytest tests/test_api.py

# Run with coverage
pytest --cov=app --cov-report=html
```

### **4\. Check Code Quality**

```
# Format code (if using black)
black app/

# Check linting (if using flake8)
flake8 app/

# Type checking (if using mypy)
mypy app/
```

### **5\. Commit Changes**

```
git add .
git commit -m "feat: add new feature description"
```

### **6\. Push and Create Pull Request**

```
git push origin feature/your-feature-name
```

## **Code Style and Standards**

### **Python Style Guide**

Follow PEP 8 style guide:

* Use 4 spaces for indentation  
* Maximum line length: 100 characters  
* Use descriptive variable names  
* Add docstrings to all functions and classes

### **Naming Conventions**

* **Files**: snake\_case.py  
* **Classes**: PascalCase  
* **Functions**: snake\_case  
* **Constants**: UPPER\_CASE  
* **Private methods**: \_leading\_underscore

### **Example Code Style**

```
from typing import List, Dict, Any
import logging

logger = logging.getLogger(__name__)

class DocumentProcessor:
    """Process documents and generate embeddings.

    This class handles document upload, processing, and storage
    in the vector database.
    """

    def __init__(self):
        """Initialize the document processor."""
        self.chunk_size = settings.CHUNK_SIZE
        self.chunk_overlap = settings.CHUNK_OVERLAP

    def process_document(
        self,
        file_path: str,
        metadata: Dict[str, Any]
    ) -> List[Dict[str, Any]]:
        """Process a document and return chunks.

        Args:
            file_path: Path to the document file
            metadata: Document metadata

        Returns:
            List of document chunks with embeddings

        Raises:
            ValueError: If file format is not supported
        """
        logger.info(f"Processing document: {file_path}")

        # Implementation here

        return chunks
```

```

```

## **Testing**

### **Running Tests**

```
# Run all tests
pytest

# Run with verbose output
pytest -v

# Run specific test file
pytest tests/test_api.py

# Run specific test function
pytest tests/test_api.py::test_upload_document

# Run with coverage
pytest --cov=app --cov-report=html

# View coverage report
open htmlcov/index.html
```

### **Writing Tests**

Create test files in the tests/ directory:

```
import pytest
from fastapi.testclient import TestClient
from app.main import app

client = TestClient(app)

def test_health_check():
    """Test health check endpoint."""
    response = client.get("/api/health")
    assert response.status_code == 200
    assert response.json()["status"] == "healthy"

def test_upload_document():
    """Test document upload."""
    with open("test_file.pdf", "rb") as f:
        files = {"file": f}
        data = {"source_id": "test_001", "priority": "P1"}
        response = client.post("/api/documents", files=files, data=data)

    assert response.status_code == 201
    assert "chunks_created" in response.json()

@pytest.fixture
def sample_document():
    """Fixture for sample document."""
    return {
        "source_id": "test_doc",
        "content": "Sample content",
        "metadata": {"type": "pdf"}
    }

def test_with_fixture(sample_document):
    """Test using fixture."""
    assert sample_document["source_id"] == "test_doc"
```

## 

## 

## 

## **Debugging**

### **Logging**

The application uses Python's built-in logging:

```
import logging

logger = logging.getLogger(__name__)

# Log levels
logger.debug("Debug message")
logger.info("Info message")
logger.warning("Warning message")
logger.error("Error message")
logger.critical("Critical message")
```

### **Debug Mode**

Run the application in debug mode:

```
# With uvicorn reload
python -m uvicorn app.main:app --reload --log-level debug

# With Python debugger
python -m pdb -m uvicorn app.main:app
```

### **Using Debugger**

Add breakpoints in code:

```
import pdb

def some_function():
    # Code here
    pdb.set_trace()  # Breakpoint
    # More code
```

### 

### **Checking Qdrant**

```
# View Qdrant dashboard
open http://localhost:6333/dashboard

# Check collections via API
curl http://localhost:6333/collections
```

### **Checking Redis**

```
# Connect to Redis CLI
redis-cli

# Check keys
KEYS *

# Get specific key
GET query:abc123

# Clear all keys
FLUSHALL
```

## **Common Development Tasks**

### **Running the Application**

```
# Development mode with auto-reload
python -m uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Production mode
python -m uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4
```

### **Updating Dependencies**

```
# Add new dependency
pip install package-name

# Update requirements.txt
pip freeze > requirements.txt

# Install from requirements.txt
pip install -r requirements.txt
```

### **Database Migrations (if using Alembic)**

```
# Create migration
alembic revision --autogenerate -m "description"

# Apply migration
alembic upgrade head

# Rollback migration
alembic downgrade -1
```

### **Clearing Test Data**

```
# Clear Qdrant collections
python scripts/clear_collections.py

# Clear Redis cache
redis-cli FLUSHALL

# Clear PostgreSQL data
psql -d ai_vector_service -c "TRUNCATE TABLE translation_records;"
```

### **Generating API Documentation**

FastAPI automatically generates API documentation:

* Swagger UI: [http://localhost:8000/docs](http://localhost:8000/docs)  
* ReDoc: [http://localhost:8000/redoc](http://localhost:8000/redoc)  
* OpenAPI JSON: [http://localhost:8000/openapi.json](http://localhost:8000/openapi.json)

### **Performance Profiling**

```
import cProfile
import pstats

def profile_function():
    profiler = cProfile.Profile()
    profiler.enable()

    # Code to profile

    profiler.disable()
    stats = pstats.Stats(profiler)
    stats.sort_stats('cumulative')
    stats.print_stats()
```

## **Environment Variables**

All configuration is in .env file:

```
# Qdrant Configuration
QDRANT_HOST=127.0.0.1
QDRANT_PORT=6333
COLLECTION_NAME=documents
QA_CACHE_COLLECTION=qa_cache

# Redis Configuration
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_PASSWORD=
REDIS_CACHE_TTL=86400
REDIS_MAX_CACHE_SIZE=1000

# Model Configuration
EMBEDDING_MODEL=all-MiniLM-L6-v2
LLAMA_MODEL_ID=meta.llama3-70b-instruct-v1:0

# Chunking Configuration
CHUNK_SIZE=3000
CHUNK_OVERLAP=500
MARKDOWN_CHUNK_SIZE=3500
MARKDOWN_CHUNK_OVERLAP=800

# Search Configuration
SIMILARITY_THRESHOLD=0.40
VECTOR_SEARCH_LIMIT=1
DEFAULT_SEARCH_TOP_K=10
MAX_SEARCH_TOP_K=100

# Database Configuration
POSTGRES_DATABASE_URI=postgresql://user:pass@localhost:5432/ai_vector_service

# Environment
ENVIRONMENT=local
```

## 

## **Troubleshooting**

### **Common Issues**

**Issue: Import errors**

```
# Solution: Ensure virtual environment is activated
source .venv/bin/activate
pip install -r requirements.txt
```

**Issue: Qdrant connection failed**

```
# Solution: Check if Qdrant is running
curl http://localhost:6333/collections

# Start Qdrant if not running
docker start qdrant  # if using Docker
```

**Issue: Redis connection failed**

```
# Solution: Check if Redis is running
redis-cli ping

# Start Redis if not running
brew services start redis  # macOS
sudo systemctl start redis  # Linux
```

**Issue: Tests failing**

```
# Solution: Clear test data
redis-cli FLUSHALL
# Restart Qdrant
```

