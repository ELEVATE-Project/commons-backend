
# System Architecture

This document provides a comprehensive overview of the AI Vector Service architecture, including system components, data flow, and design decisions.

## **System Overview**

The AI Vector Service is a microservice-based application built on FastAPI that provides intelligent document processing and semantic search capabilities. The system uses vector embeddings to enable semantic similarity search across multiple document types.

## **Core Components**

### **1\. API Layer (app/api/)**

The API layer handles HTTP requests and responses using FastAPI.

#### **Endpoints Module (app/api/v1/endpoints/)**

* **documents.py**: Document management endpoints  
  * Upload, update, delete documents  
  * Similarity checking  
  * Prioritized and text-based search  
* **query.py**: Multilingual query processing  
  * Language detection and translation  
  * Priority-based search  
* **cache.py**: Cache management  
  * Clear cache operations

### **2\. Service Layer (app/services/)**

The service layer contains business logic and orchestrates operations.

#### **Document Operations (document\_operations/)**

* **base\_operation.py**: Base class for document operations  
* **upload\_service.py**: Handles document upload and processing  
* **update\_service.py**: Updates existing documents  
* **delete\_service.py**: Deletes documents from vector store  
* **metadata\_service.py**: Updates document metadata

#### **File Processors (file\_processors/)**

Each processor handles a specific file format:

* **base\_processor.py**: Abstract base class for file processors  
* **pdf\_processor.py**: PDF document processing  
* **docx\_processor.py**: Microsoft Word document processing  
* **text\_processor.py**: Plain text and markdown processing  
* **csv\_processor.py**: CSV file processing  
* **xlsx\_processor.py**: Excel spreadsheet processing

#### **Search Services**

* **query\_service.py**: Multilingual query processing with translation  
* **prioritized\_search\_service.py**: Multi-field weighted search  
* **text\_embedding\_search\_service.py**: Simple text embedding search  
* **similarity\_service.py**: Content similarity detection

#### **Other Services**

* **document\_processor.py**: Main document processing orchestrator  
* **url\_text\_extractor.py**: Extracts text from web URLs  
* **translation\_service.py**: Text translation service

### **3\. Core Layer (app/core/)**

The core layer provides foundational services and clients.

#### **Clients (core/clients/)**

* **qdrant.py**: Qdrant vector database client  
  * Collection management  
  * Batch upload operations  
  * Named vectors configuration  
* **redis\_cache.py**: Redis LRU cache implementation  
  * Query result caching  
  * Automatic eviction of old entries  
  * Configurable TTL and size limits  
* **embedding.py**: Sentence transformer embedding model  
  * Generates vector embeddings for text

#### **Database (core/database.py)**

* PostgreSQL database connection  
* Used for storing translation records

### **4\. Models (app/models/)**

* **api\_models.py**: Pydantic models for API requests/responses  
* **db\_models.py**: SQLAlchemy models for database tables

### **5\. Utilities (app/utils/)**

* **json\_handler.py**: Custom JSON response handling  
* **language\_utils.py**: Language detection and translation utilities

## **Data Flow**

### **Document Upload Flow**

```
1. Client uploads file
   ↓
2. API endpoint receives file + metadata
   ↓
3. DocumentProcessor validates file type
   ↓
4. Appropriate FileProcessor processes file
   ↓
5. Text is chunked using LangChain
   ↓
6. Embeddings generated for each chunk
   ↓
7. Multiple named vectors created:
   - text: chunk content embedding
   - title: document title embedding
   - summary: document summary embedding
   - tags: tags embedding
   - metadata: metadata embedding
   ↓
8. Points uploaded to Qdrant in batches
   ↓
9. Response returned to client
```

### **Search Flow (Prioritized Search)**

```
1. Client sends search query + filters
   ↓
2. Query embedding generated
   ↓
3. Search across all named vectors:
   - title vector search
   - text vector search
   - tags vector search
   - summary vector search
   - metadata vector search
   ↓
4. Apply filters (categories, organizations, etc.)
   ↓
5. Calculate weighted scores:
   Final Score = (W_title × S_title) +
                 (W_text × S_text) +
                 (W_tags × S_tags) +
                 (W_summary × S_summary) +
                 (W_metadata × S_metadata)
   ↓
6. Apply multi-field bonus (5% per additional field)
   ↓
7. Group by source_id, keep highest score
   ↓
8. Sort and return top_k results
```

### **Multilingual Query Flow**

```
1. Client sends query (any language)
   ↓
2. Language detection (English/Hindi)
   ↓
3. If Hindi: Translate to English
   ↓
4. Check Redis cache
   ↓
5. If cache miss:
   a. Generate query embedding
   b. Search Qdrant with priority filtering
   c. Process results
   d. If Hindi query: Include translations
   e. Cache response
   ↓
6. Return results to client
```

## **Vector Storage Strategy**

### **Named Vectors Architecture**

The system uses Qdrant's named vectors feature to store multiple embeddings per document chunk:

```
{
  "id": "chunk_uuid",
  "vectors": {
    "text": [0.1, 0.2, ...],      # Chunk content embedding
    "title": [0.3, 0.4, ...],     # Document title embedding
    "summary": [0.5, 0.6, ...],   # Document summary embedding
    "tags": [0.7, 0.8, ...],      # Tags embedding
    "metadata": [0.9, 1.0, ...]   # Metadata embedding
  },
  "payload": {
    "text": "chunk content",
    "title": "document title",
    "summary": "document summary",
    "tags": ["tag1", "tag2"],
    "metadata": {
      "source_id": "doc_123",
      "company_id": "company_1",
      "priority": "P1",
      "type": "pdf",
      ...
    }
  }
}
```

### **Benefits of Named Vectors**

1. **Multi-field Search**: Search across different document aspects simultaneously  
2. **Weighted Scoring**: Apply different weights to different fields  
3. **Flexible Querying**: Choose which vectors to search based on use case  
4. **Better Relevance**: Combine signals from multiple fields for better results

### **Collections**

1. **documents** (main collection)  
   * Stores all document chunks with named vectors  
   * Supports multi-field search  
2. **qa\_cache** (cache collection)  
   * Stores cached query-answer pairs  
   * Uses single vector for similarity matching

## **Caching Strategy**

### **Redis LRU Cache**

The system implements a Least Recently Used (LRU) cache using Redis:

#### **Cache Key Generation**

* Keys are generated using MD5 hash of query \+ filters  
* Format: query:\<md5\_hash\>

#### **Access Tracking**

* Uses Redis Sorted Set (lru:access\_list)  
* Scores are timestamps of last access  
* Automatically updates on cache hits

#### **Eviction Policy**

* When cache size exceeds REDIS\_MAX\_CACHE\_SIZE  
* Oldest entries (lowest timestamps) are removed  
* Both cache entry and access list entry deleted

#### **TTL (Time To Live)**

* Configurable via REDIS\_CACHE\_TTL  
* Default: 86400 seconds (24 hours)  
* Automatic expiration of stale data

#### **Cache Operations**

```
# Get from cache
cached_result = redis_cache.get(query)

# Set in cache
redis_cache.set(query, response)

# Clear all cache
redis_cache.clear()

# Remove specific entry
redis_cache.remove(query)
```

## **Search Architecture**

### **1\. Prioritized Multi-field Search**

**Purpose**: Comprehensive search across all document fields with weighted scoring

**Features**:

* Searches across 5 named vectors (title, text, tags, summary, metadata)  
* Configurable weights for each field  
* Multi-field bonus for documents matching multiple fields  
* Advanced filtering (categories, organizations, resource types, file types)  
* Returns unique documents (one per source\_id)

**Scoring Formula**:

```
Final_Score = (W_title × S_title) +
              (W_text × S_text) +
              (W_tags × S_tags) +
              (W_summary × S_summary) +
              (W_metadata × S_metadata) +
              (Multi_field_bonus)

Multi_field_bonus = 0.05 × (number_of_matching_fields - 1)
```

**Default Weights** (configurable in config.py):

* Title: 36%  
* Text: 27%  
* Tags: 14%  
* Summary: 14%  
* Metadata: 9%

### **2\. Text Embedding Search**

**Purpose**: Simple, fast text-based search

**Features**:

* Searches only the text vector  
* Returns top chunk per unique document  
* Configurable similarity threshold  
* Faster than prioritized search

### **3\. Multilingual Query Search**

**Purpose**: Support queries in multiple languages

**Features**:

* Automatic language detection  
* Translation to English for vector search  
* Priority-based filtering (P1, P2, P3)  
* Returns results with translations if needed  
* Redis caching for performance
