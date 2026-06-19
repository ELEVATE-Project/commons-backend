#!/usr/bin/env python3
"""
Qdrant Sanity Check Script
Validates collection structure, vector dimensions, and metadata completeness
"""

from qdrant_client import QdrantClient
from qdrant_client.models import Distance, VectorParams
from collections import defaultdict
import json

# Configuration
QDRANT_HOST = "localhost"
QDRANT_PORT = 6333
COLLECTION_NAME = "documents"  # Only check this collection
EXPECTED_VECTORS = ["title", "text", "metadata", "tags", "summary"]
EXPECTED_DIMENSION = 384

def connect_to_qdrant():
    """Connect to local Qdrant instance"""
    try:
        client = QdrantClient(host=QDRANT_HOST, port=QDRANT_PORT)
        print(f"✓ Connected to Qdrant at {QDRANT_HOST}:{QDRANT_PORT}")
        return client
    except Exception as e:
        print(f"✗ Failed to connect to Qdrant: {e}")
        return None

def get_collections_info(client):
    """Get all collections and their basic info"""
    try:
        collections = client.get_collections().collections
        print(f"\n📊 Found {len(collections)} collection(s)")
        return collections
    except Exception as e:
        print(f"✗ Error fetching collections: {e}")
        return []

def check_collection(client, collection_name):
    """Perform detailed checks on a collection"""
    print(f"\n{'='*80}")
    print(f"🔍 Checking Collection: {collection_name}")
    print(f"{'='*80}")
    
    # Get collection info
    try:
        collection_info = client.get_collection(collection_name)
        print(f"\n📈 Collection Stats:")
        print(f"   Points count: {collection_info.points_count}")
        print(f"   Vectors count: {collection_info.vectors_count}")
        
        # Check vector configuration
        print(f"\n🔧 Vector Configuration:")
        vectors_config = collection_info.config.params.vectors
        
        if isinstance(vectors_config, dict):
            for vector_name, config in vectors_config.items():
                print(f"   • {vector_name}: {config.size} dimensions, {config.distance}")
        else:
            print(f"   Single vector: {vectors_config.size} dimensions")
            
    except Exception as e:
        print(f"✗ Error getting collection info: {e}")
        return
    
    # Fetch all points
    print(f"\n📥 Fetching all points...")
    try:
        points = client.scroll(
            collection_name=collection_name,
            limit=10000,  # Adjust based on your data size
            with_payload=True,
            with_vectors=True
        )[0]
        
        print(f"   Retrieved {len(points)} points")
        
    except Exception as e:
        print(f"✗ Error fetching points: {e}")
        return
    
    # Initialize counters
    issues = {
        "missing_vectors": defaultdict(list),
        "wrong_dimensions": defaultdict(list),
        "missing_metadata": defaultdict(list),
        "null_tags": []
    }
    
    valid_points = 0
    
    # Check each point
    print(f"\n🔎 Validating points...")
    for idx, point in enumerate(points):
        point_id = point.id
        has_issues = False
        
        # Check vectors
        if hasattr(point, 'vector') and point.vector:
            vectors = point.vector if isinstance(point.vector, dict) else {"default": point.vector}
            
            # Check for missing vectors
            for expected_vector in EXPECTED_VECTORS:
                if expected_vector not in vectors:
                    issues["missing_vectors"][expected_vector].append(point_id)
                    has_issues = True
                else:
                    # Check dimensions
                    vector_data = vectors[expected_vector]
                    if len(vector_data) != EXPECTED_DIMENSION:
                        issues["wrong_dimensions"][expected_vector].append(
                            (point_id, len(vector_data))
                        )
                        has_issues = True
        else:
            for expected_vector in EXPECTED_VECTORS:
                issues["missing_vectors"][expected_vector].append(point_id)
            has_issues = True
        
        # Check payload/metadata
        if hasattr(point, 'payload') and point.payload:
            payload = point.payload
            
            # Check for null or empty tags
            if "tags" in payload:
                tags = payload.get("tags")
                if tags is None or tags == "" or (isinstance(tags, list) and len(tags) == 0):
                    issues["null_tags"].append(point_id)
                    has_issues = True
            else:
                issues["missing_metadata"]["tags"].append(point_id)
                has_issues = True
            
            # Check for other important metadata fields
            important_fields = ["title", "text", "metadata", "summary"]
            for field in important_fields:
                if field not in payload or payload[field] is None or payload[field] == "":
                    issues["missing_metadata"][field].append(point_id)
                    has_issues = True
        else:
            issues["missing_metadata"]["payload"].append(point_id)
            has_issues = True
        
        if not has_issues:
            valid_points += 1
        
        # Progress indicator
        if (idx + 1) % 100 == 0:
            print(f"   Processed {idx + 1}/{len(points)} points...", end="\r")
    
    print(f"   Processed {len(points)}/{len(points)} points...   ")
    
    # Print summary
    print(f"\n{'='*80}")
    print(f"📋 VALIDATION SUMMARY")
    print(f"{'='*80}")
    print(f"\n✓ Valid points: {valid_points}/{len(points)} ({valid_points/len(points)*100:.2f}%)")
    print(f"✗ Points with issues: {len(points) - valid_points}/{len(points)} ({(len(points) - valid_points)/len(points)*100:.2f}%)")
    
    # Detailed issues report
    if any(issues.values()):
        print(f"\n🚨 ISSUES FOUND:")
        
        # Missing vectors
        if issues["missing_vectors"]:
            print(f"\n  Missing Vectors:")
            for vector_name, point_ids in issues["missing_vectors"].items():
                print(f"    • {vector_name}: {len(point_ids)} points")
                if len(point_ids) <= 5:
                    print(f"      Point IDs: {point_ids}")
                else:
                    print(f"      Point IDs (first 5): {point_ids[:5]}")
        
        # Wrong dimensions
        if issues["wrong_dimensions"]:
            print(f"\n  Wrong Vector Dimensions (expected {EXPECTED_DIMENSION}):")
            for vector_name, errors in issues["wrong_dimensions"].items():
                print(f"    • {vector_name}: {len(errors)} points")
                if len(errors) <= 3:
                    for point_id, dim in errors:
                        print(f"      Point {point_id}: {dim} dimensions")
                else:
                    for point_id, dim in errors[:3]:
                        print(f"      Point {point_id}: {dim} dimensions")
                    print(f"      ... and {len(errors) - 3} more")
        
        # Missing metadata
        if issues["missing_metadata"]:
            print(f"\n  Missing/Empty Metadata:")
            for field_name, point_ids in issues["missing_metadata"].items():
                print(f"    • {field_name}: {len(point_ids)} points")
                if len(point_ids) <= 5:
                    print(f"      Point IDs: {point_ids}")
                else:
                    print(f"      Point IDs (first 5): {point_ids[:5]}")
        
        # Null tags
        if issues["null_tags"]:
            print(f"\n  Null/Empty Tags:")
            print(f"    • {len(issues['null_tags'])} points with null/empty tags")
            if len(issues["null_tags"]) <= 5:
                print(f"      Point IDs: {issues['null_tags']}")
            else:
                print(f"      Point IDs (first 5): {issues['null_tags'][:5]}")
    else:
        print(f"\n✓ No issues found! All points are valid.")
    
    # Save detailed report to file
    report_file = f"qdrant_report_{collection_name}.json"
    report = {
        "collection_name": collection_name,
        "total_points": len(points),
        "valid_points": valid_points,
        "invalid_points": len(points) - valid_points,
        "issues": {
            "missing_vectors": {k: len(v) for k, v in issues["missing_vectors"].items()},
            "wrong_dimensions": {k: len(v) for k, v in issues["wrong_dimensions"].items()},
            "missing_metadata": {k: len(v) for k, v in issues["missing_metadata"].items()},
            "null_tags_count": len(issues["null_tags"])
        },
        "detailed_issues": {
            "missing_vectors": {k: v for k, v in issues["missing_vectors"].items()},
            "wrong_dimensions": {k: [(str(pid), dim) for pid, dim in v] for k, v in issues["wrong_dimensions"].items()},
            "missing_metadata": {k: v for k, v in issues["missing_metadata"].items()},
            "null_tags": issues["null_tags"]
        }
    }
    
    with open(report_file, 'w') as f:
        json.dump(report, f, indent=2)
    print(f"\n💾 Detailed report saved to: {report_file}")

def main():
    """Main execution function"""
    print("🚀 Starting Qdrant Sanity Check")
    print(f"{'='*80}\n")
    
    # Connect to Qdrant
    client = connect_to_qdrant()
    if not client:
        return
    
    # Check if documents collection exists
    try:
        collections = client.get_collections().collections
        collection_names = [c.name for c in collections]
        
        if COLLECTION_NAME not in collection_names:
            print(f"\n⚠️  Collection '{COLLECTION_NAME}' not found!")
            print(f"Available collections: {', '.join(collection_names)}")
            return
        
        print(f"\n✓ Found collection: {COLLECTION_NAME}")
        
    except Exception as e:
        print(f"✗ Error checking collections: {e}")
        return
    
    # Check the documents collection
    check_collection(client, COLLECTION_NAME)
    
    print(f"\n{'='*80}")
    print("✅ Sanity check completed!")
    print(f"{'='*80}\n")

if __name__ == "__main__":
    main()