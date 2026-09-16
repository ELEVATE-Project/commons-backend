import requests
import os
from chatbot.models import Media, CompanyBot


class DuplicateDetector:
    """Comprehensive duplicate detection using trigram and vector similarity"""

    @staticmethod
    def check_for_duplicates(
            extracted_text,
            company_slug,
            exclude_media_id=None,
            trigram_threshold=0.85,
            semantic_threshold=0.85,
            trigram_exact_threshold=0.95,
            semantic_exact_threshold=0.90,
    ):
        """
        Check for duplicates using both trigram and semantic similarity
        """
        if not extracted_text or len(extracted_text.strip()) < 50:
            return

        # 1. First check trigram similarity (fast, local)
        trigram_similar = Media.find_trigram_similar(
            extracted_text=extracted_text,
            company_slug=company_slug,
            similarity_threshold=trigram_threshold,
            exclude_id=exclude_media_id
        )
        print("trigram_similar: ", trigram_similar)

        if trigram_similar and any(m['similarity'] >= trigram_exact_threshold for m in trigram_similar):
            # Exact duplicate found
            match = next(m for m in trigram_similar if m['similarity'] >= trigram_exact_threshold)
            raise ValueError(
                f"❌ EXACT DUPLICATE FOUND ({match['similarity'] * 100:.1f}% match):\n"
                f"   • '{match['name']}'\n\n"
                f"This file appears to be an exact duplicate. Upload cancelled."
            )

        # 2. Check semantic similarity via vector service (if no exact match)
        if not trigram_similar or all(m['similarity'] < trigram_exact_threshold for m in trigram_similar):
            semantic_similar = DuplicateDetector.check_semantic_similarity(
                text=extracted_text,
                company_slug=company_slug,
                threshold=semantic_threshold,
                exclude_source_id=str(exclude_media_id) if exclude_media_id else None
            )
            print("semantic_similar: ", semantic_similar)
            # Only raise error if semantic similarity >= semantic_exact_threshold
            if semantic_similar:
                exact_semantic_matches = [
                    doc for doc in semantic_similar
                    if doc['similarity_score'] >= semantic_exact_threshold
                ]
                if exact_semantic_matches:
                    error_parts = ["❌ DUPLICATE CONTENT DETECTED:"]
                    for doc in exact_semantic_matches[:3]:
                        error_parts.append(
                            f"({doc['similarity_score'] * 100:.1f}% similar)"
                        )
                    error_parts.append("\nThis content appears to be a duplicate. Upload cancelled.")
                    raise ValueError("\n".join(error_parts))

        # 3. Show near-duplicates as warning (but don't block)
        # if trigram_similar and any(trigram_threshold <= m['similarity'] < trigram_exact_threshold for m in trigram_similar):
        #     print("⚠️  Warning: Near-duplicates found:")
        #     for match in [m for m in trigram_similar if trigram_threshold <= m['similarity'] < trigram_exact_threshold][:3]:
        #         print(f"   • '{match['name']}' ({match['similarity'] * 100:.0f}% similar)")

    @staticmethod
    def check_semantic_similarity(text, company_slug, threshold=0.85, exclude_source_id=None):
        """Check semantic similarity via vector service API"""
        try:
            base_url = os.getenv('VECTOR_DB_BASE_URL')
            url = f"{base_url}/api/documents/check-similarity"

            payload = {
                "text": text,
                "company_id": company_slug,
                "threshold": threshold,
                "exclude_source_id": exclude_source_id
            }

            headers = {
                'Content-Type': 'application/json',
                'accept': 'application/json',
            }

            response = requests.post(url, json=payload, headers=headers)
            print("response: ", response)
            if response.status_code == 200:
                result = response.json()
                print("response result: ", result)
                if result.get('has_similar'):
                    return result.get('similar_documents', [])
            else:
                print(f"Vector service similarity check failed: {response.text}")

            return []

        except Exception as e:
            print(f"Error checking semantic similarity: {str(e)}")
            # Don't fail the upload if vector service is down
            return []
