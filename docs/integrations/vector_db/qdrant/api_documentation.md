# API Documentation

Complete API reference for the AI Vector Service.

## **Base URL**

```
Local: http://localhost:8000/api
```

## **Health Check**

### **GET /health**

Check the health status of the service and its dependencies.

**Response**

```
{
  "status": "healthy",
  "services": {
    "qdrant": "connected",
    "redis": "connected"
  }
}
```

**Status Codes**

* 200: Service is healthy  
* 503: Service is unhealthy (Qdrant or Redis connection failed)

---

## **Document Management**

### **POST /documents**

Upload and process a new document.

**Request**

Content-Type: multipart/form-data

| Field | Type | Required | Description |
| :---- | :---- | :---- | :---- |
| file | File | Yes | Document file (PDF, DOCX, TXT, CSV, XLSX) |
| priority | String | No | Priority level (P1, P2, P3). Default: P1 |
| source\_id | String | No | Unique identifier for the document source |
| company\_id | String | No | Company identifier for multi-tenant scenarios |
| title | String | No | Document title |
| summary | String | No | Document summary |
| metadata | JSON String | No | Additional metadata as JSON object |
| tags | JSON Array or CSV | No | Tags as JSON array or comma-separated string |

**Example Request (cURL)**

```
curl -X POST "http://localhost:8000/api/documents" \
  -F "file=@document.pdf" \
  -F "priority=P1" \
  -F "source_id=doc_123" \
  -F "company_id=company_1" \
  -F "title=Machine Learning Guide" \
  -F "summary=Comprehensive guide to ML algorithms" \
  -F 'tags=["AI", "ML", "Tutorial"]' \
  -F 'metadata={"author": "John Doe", "department": "Engineering"}'
```

**Response**

```
{
  "message": "Document processed successfully",
  "source_id": "doc_123",
  "chunks_created": 15,
  "metadata": {
    "type": "pdf",
    "priority": "P1",
    "company_id": "company_1"
  }
}
```

**Status Codes**

* 201: Document created successfully  
* 400: Invalid request (bad file format, invalid metadata)  
* 500: Server error during processing

---

### **PUT /documents/{source\_id}**

Update existing documents by replacing all documents with the same source\_id.

**Path Parameters**

* source\_id (string): Source identifier of documents to update

**Request**

Content-Type: multipart/form-data

| Field | Type | Required | Description |
| :---- | :---- | :---- | :---- |
| file | File | Yes | New document file |
| priority | String | No | Priority level. Default: P1 |
| metadata | JSON String | No | Updated metadata |
| company\_id | String | No | Company identifier |

**Example Request**

```
curl -X PUT "http://localhost:8000/api/documents/doc_123" \
  -F "file=@updated_document.pdf" \
  -F "priority=P2" \
  -F "company_id=company_1"
```

**Response**

```
{
  "message": "Documents updated successfully",
  "source_id": "doc_123",
  "deleted_count": 15,
  "created_count": 18
}
```

---

### **PUT /documents/{source\_id}/upsert**

Upsert documents \- update if exists, create if not.

**Path Parameters**

* source\_id (string): Source identifier

**Request**

Same as PUT /documents/{source\_id}

**Response**

```
{
  "message": "Documents upserted successfully",
  "source_id": "doc_123",
  "operation": "updated",
  "chunks_count": 18
}
```

---

### **PATCH /documents/{source\_id}/metadata**

Update only metadata of documents without reprocessing content.

**Path Parameters**

* source\_id (string): Source identifier

**Request**

Content-Type: multipart/form-data

| Field | Type | Required | Description |
| :---- | :---- | :---- | :---- |
| metadata\_updates | JSON String | Yes | Metadata fields to update |
| company\_id | String | No | Company identifier |

**Example Request**

```
curl -X PATCH "http://localhost:8000/api/documents/doc_123/metadata" \
  -F 'metadata_updates={"author": "Jane Smith", "version": "2.0"}' \
  -F "company_id=company_1"
```

**Response**

```
{
  "message": "Metadata updated successfully",
  "source_id": "doc_123",
  "updated_count": 15,
  "updated_fields": ["author", "version"]
}
```

---

### **DELETE /documents/{source\_id}**

Delete all documents with the specified source\_id.

**Path Parameters**

* source\_id (string): Source identifier

**Request**

Content-Type: multipart/form-data

| Field | Type | Required | Description |
| :---- | :---- | :---- | :---- |
| company\_id | String | No | Company identifier for filtering |

**Example Request**

```
curl -X DELETE "http://localhost:8000/api/documents/doc_123" \
  -F "company_id=company_1"
```

**Response**

```
{
  "message": "Documents deleted successfully",
  "source_id": "doc_123",
  "deleted_count": 15
}
```

**Status Codes**

* 200: Documents deleted successfully  
* 404: No documents found with the given source\_id  
* 500: Server error during deletion

---

## **Search Operations**

### **POST /documents/search**

Perform prioritized multi-field search with weighted scoring.

**Request**

Content-Type: application/json

```
{
  "query": "machine learning algorithms",
  "top_k": 10,
  "categories": ["AI", "ML"],
  "organizations": ["company_1"],
  "resource_type": ["Tutorial"],
  "file_type": ["pdf"]
}
```

**Request Fields**

| Field | Type | Required | Default | Description |
| :---- | :---- | :---- | :---- | :---- |
| query | String | No | null | Search query text. If not provided, returns all unique documents |
| top\_k | Integer | No | 10 | Number of top results to return (max: 100\) |
| categories | Array\[String\] | No | null | Filter by tags (OR condition) |
| organizations | Array\[String\] | No | null | Filter by metadata.company (OR condition) |
| resource\_type | Array\[String\] | No | null | Filter by metadata.KEY ENTITIES (OR condition) |
| file\_type | Array\[String\] | No | null | Filter by metadata.type (OR condition) |

**Response**

```
{
  "query": "machine learning algorithms",
  "total_results": 10,
  "top_k": 10,
  "results": [
    {
      "id": "chunk_uuid_1",
      "text": "Machine learning algorithms are...",
      "title": "ML Guide",
      "summary": "Comprehensive ML guide",
      "tags": ["AI", "ML"],
      "metadata": {
        "source_id": "doc_123",
        "company_id": "company_1",
        "type": "pdf",
        "priority": "P1"
      },
      "source_id": "doc_123",
      "score": 0.89,
      "field_scores": {
        "title": 0.92,
        "text": 0.87,
        "tags": 0.85,
        "summary": 0.88,
        "metadata": 0.75
      }
    }
  ],
  "search_config": {
    "priority_order": ["title", "text", "tags", "summary", "metadata"],
    "weights": {
      "title": 0.36,
      "text": 0.27,
      "tags": 0.14,
      "summary": 0.14,
      "metadata": 0.09
    }
  }
}
```

**Scoring Formula**

```
Final_Score = (W_title × S_title) + (W_text × S_text) +
              (W_tags × S_tags) + (W_summary × S_summary) +
              (W_metadata × S_metadata) + Multi_field_bonus

Multi_field_bonus = 0.05 × (matching_fields - 1)
```

**Status Codes**

* 200: Search completed successfully  
* 422: Invalid request (top\_k \<= 0\)  
* 500: Server error during search

---

### **POST /documents/text-search**

Simple text embedding search that returns top chunk per unique document.

**Request**

Content-Type: application/json

```
{
  "query": "machine learning",
  "top_k": 5,
  "threshold": 0.4
}
```

**Request Fields**

| Field | Type | Required | Default | Description |
| :---- | :---- | :---- | :---- | :---- |
| query | String | Yes | \- | Search query text |
| top\_k | Integer | No | 10 | Number of unique documents to return |
| threshold | Float | No | 0.40 | Minimum similarity score threshold |

**Response**

```
{
  "query": "machine learning",
  "total_results": 5,
  "results": [
    {
      "source_id": "doc_123",
      "text": "Machine learning is a subset of...",
      "score": 0.89,
      "metadata": {
        "title": "ML Guide",
        "type": "pdf",
        "priority": "P1"
      }
    }
  ]
}
```

**Status Codes**

* 200: Search completed successfully  
* 400: Invalid request  
* 500: Server error during search

---

### **POST /documents/check-similarity**

Check if similar content already exists in the database.

**Request**

Content-Type: application/json

```
{
  "text": "Machine learning is a subset of artificial intelligence",
  "company_id": "company_1",
  "threshold": 0.85,
  "exclude_source_id": "doc_123"
}
```

**Request Fields**

| Field | Type | Required | Default | Description |
| :---- | :---- | :---- | :---- | :---- |
| text | String | Yes | \- | Text to check for similarity |
| company\_id | String | Yes | \- | Company ID to filter by |
| threshold | Float | No | 0.85 | Similarity threshold (0-1) |
| exclude\_source\_id | String | No | null | Source ID to exclude from check |

**Response**

```
{
  "has_similar": true,
  "similar_documents": [
    {
      "source_id": "doc_456",
      "text": "Machine learning, a subset of AI...",
      "score": 0.92,
      "metadata": {
        "title": "AI Basics",
        "type": "pdf"
      }
    }
  ]
}
```

**Status Codes**

* 200: Check completed successfully  
* 400: Invalid request  
* 500: Server error during check

---

## **Query Operations**

### **POST /query/**

Query documents with multilingual support and automatic translation.

**Request**

Content-Type: application/json

```
{
  "query": "What is machine learning?",
  "search_limit": 5,
  "priority_filter": "P1"
}
```

**Request Fields**

| Field | Type | Required | Default | Description |
| :---- | :---- | :---- | :---- | :---- |
| query | String | Yes | \- | Query text (English or Hindi) |
| search\_limit | Integer | No | 1 | Number of results to return |
| priority\_filter | String | No | null | Filter by priority (P1, P2, P3) |

**Response**

```
{
  "relevant_texts": [
    {
      "qdrant_recommendation_text": "Machine learning is...",
      "translated_text": null,
      "relevance_score": 0.89,
      "metadata": {
        "source_id": "doc_123",
        "type": "pdf",
        "priority": "P1"
      },
      "priority": "P1",
      "chunk_id": "abc123"
    }
  ],
  "original_query": "What is machine learning?",
  "translated_query": null,
  "language": "en"
}
```

**Hindi Query Example**

Request:

```
{
  "query": "मशीन लर्निंग क्या है?",
  "search_limit": 3
}
```

Response:

```
{
  "relevant_texts": [...],
  "original_query": "मशीन लर्निंग क्या है?",
  "translated_query": "What is machine learning?",
  "language": "hi"
}
```

**Status Codes**

* 200: Query completed successfully  
* 400: Invalid request  
* 500: Server error during query processing

---

## **Cache Management**

### **DELETE /cache/clear**

Clear all cached query results from Redis.

**Request**

No request body required.

**Example Request**

```
curl -X DELETE "http://localhost:8000/api/cache/clear"
```

**Response**

```
{
  "message": "Cache cleared successfully"
}
```

**Status Codes**

* 200: Cache cleared successfully  
* 500: Server error during cache clear

---

## **Request/Response Models**

### **DocumentMetadata**

```
{
  "source": "string",
  "page": 1,
  "row": 5
}
```

### **SearchResultItem**

```
{
  "id": "string",
  "text": "string",
  "title": "string",
  "summary": "string",
  "tags": ["string"],
  "metadata": {},
  "source_id": "string",
  "score": 0.89,
  "field_scores": {
    "title": 0.92,
    "text": 0.87
  }
}
```

### **PrioritizedSearchRequest**

```
{
  "query": "string",
  "top_k": 10,
  "categories": ["string"],
  "organizations": ["string"],
  "resource_type": ["string"],
  "file_type": ["string"]
}
```

### **PrioritizedSearchResponse**

```
{
  "query": "string",
  "total_results": 10,
  "top_k": 10,
  "results": [SearchResultItem],
  "search_config": {}
}
```

---

## **Error Handling**

### **Error Response Format**

```
{
  "detail": "Error message describing what went wrong"
}
```

### **Common Error Codes**

| Status Code | Description |
| :---- | :---- |
| 400 | Bad Request \- Invalid input data |
| 404 | Not Found \- Resource doesn't exist |
| 422 | Unprocessable Entity \- Validation error |
| 500 | Internal Server Error \- Server-side error |
| 503 | Service Unavailable \- Dependency failure |

### **Example Error Responses**

**400 Bad Request**

```
{
  "detail": "Invalid metadata JSON: Expecting property name enclosed in double quotes"
}
```

**404 Not Found**

```
{
  "detail": "No documents found with source_id: doc_123"
}
```

**500 Internal Server Error**

```
{
  "detail": "Failed to generate embeddings: Connection timeout"
}
```

**503 Service Unavailable**

```
{
  "detail": "Redis connection failed"
}
```

---

## **Rate Limiting**

Currently, there is no rate limiting implemented. For production deployments, consider implementing rate limiting at the API gateway or application level.

## **API Versioning**

The API uses URL path versioning:

* Current version: /api/v1/  
* Future versions: /api/v2/, /api/v3/, etc.

---

## **Best Practices**

### **1\. Document Upload**

* Use descriptive source\_id values  
* Include relevant metadata for better search results  
* Add tags for categorization  
* Provide title and summary when available

### **2\. Search Operations**

* Start with top\_k=10 and adjust based on results  
* Use filters to narrow down results  
* Combine multiple search strategies for best results  
* Cache frequently used queries

### **3\. Metadata Management**

* Use consistent metadata schema across documents  
* Include company\_id for multi-tenant scenarios  
* Update metadata separately when content doesn't change

### **4\. Error Handling**

* Always check response status codes  
* Implement retry logic for 500 errors  
* Validate input data before sending requests  
* Handle partial failures in batch operations

---

## **Examples**

### **Complete Upload and Search Workflow**

```
# 1. Upload a document
curl -X POST "http://localhost:8000/api/documents" \
  -F "file=@ml_guide.pdf" \
  -F "source_id=ml_guide_001" \
  -F "title=Machine Learning Guide" \
  -F 'tags=["AI", "ML", "Tutorial"]'

# 2. Search for the document
curl -X POST "http://localhost:8000/api/documents/search" \
  -H "Content-Type: application/json" \
  -d '{
    "query": "neural networks",
    "top_k": 5,
    "categories": ["AI"]
  }'

# 3. Update metadata
curl -X PATCH "http://localhost:8000/api/documents/ml_guide_001/metadata" \
  -F 'metadata_updates={"version": "2.0", "reviewed": true}'

# 4. Delete the document
curl -X DELETE "http://localhost:8000/api/documents/ml_guide_001"
```
