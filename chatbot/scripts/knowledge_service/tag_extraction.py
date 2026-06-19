import requests
import openai
import json
import re
from typing import List, Dict, Any

def extract_tags_from_google_doc(doc_url: str, openai_api_key: str, max_tags: int = 15) -> List[str]:
    """
    Extract tags from a Google Docs URL
    
    Args:
        doc_url: Google Docs URL (https://docs.google.com/document/d/...)
        openai_api_key: Your OpenAI API key
        max_tags: Maximum number of tags to extract
    
    Returns:
        List of extracted tags
    """
    
    def convert_to_export_url(google_docs_url: str) -> str:
        """Convert Google Docs URL to plain text export URL"""
        # Extract document ID from URL
        doc_id_match = re.search(r'/document/d/([a-zA-Z0-9-_]+)', google_docs_url)
        if not doc_id_match:
            raise ValueError("Invalid Google Docs URL format")
        
        doc_id = doc_id_match.group(1)
        # Convert to plain text export URL
        export_url = f"https://docs.google.com/document/d/{doc_id}/export?format=txt"
        return export_url
    
    def fetch_document_text(export_url: str) -> str:
        """Fetch document content as plain text"""
        try:
            headers = {
                'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/91.0.4472.124 Safari/537.36'
            }
            
            response = requests.get(export_url, headers=headers, timeout=30)
            response.raise_for_status()
            
            # Google Docs export returns text content
            text = response.text.strip()
            
            if not text or len(text) < 10:
                raise ValueError("Document appears to be empty or inaccessible")
            
            return text
            
        except requests.exceptions.RequestException as e:
            raise Exception(f"Failed to fetch document: {str(e)}")
    
    def extract_tags_with_llm(text: str, api_key: str, max_tags: int) -> Dict[str, Any]:
        """Extract tags using OpenAI LLM"""
        
        # Initialize OpenAI client
        client = openai.OpenAI(api_key=api_key)
        
        # Truncate text if too long
        if len(text) > 4000:
            text = text[:4000] + "..."
        
        prompt = f"""
Analyze this document and extract relevant tags and classification information.

Document Content:
{text}

Extract the following and return as JSON:
1. "tags": A list of {max_tags} relevant tags (2-3 words each) that describe content, purpose, domain
2. "classification": A single phrase describing what type of document this is
3. "main_topics": A list of 3-5 main topics covered
4. "entities": A list of important organizations, people, or places mentioned

Focus on:
- Educational and academic content
- Government and policy terms
- Monitoring & Evaluation concepts
- Field work and assessment
- Administrative content

Return ONLY valid JSON:
{{
  "tags": ["tag1", "tag2", "tag3"],
  "classification": "Document Type",
  "main_topics": ["topic1", "topic2"],
  "entities": ["entity1", "entity2"]
}}
"""
        
        try:
            response = client.chat.completions.create(
                model="gpt-3.5-turbo",
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert document analyzer. Extract tags and classification information in JSON format."
                    },
                    {"role": "user", "content": prompt}
                ],
                max_tokens=600,
                temperature=0.3
            )
            
            result_text = response.choices[0].message.content.strip()
            
            # Parse JSON response
            try:
                result = json.loads(result_text)
                return result
            except json.JSONDecodeError:
                # Fallback: extract tags using regex
                tags = re.findall(r'"([^"]*)"', result_text)
                return {
                    "tags": tags[:max_tags] if tags else ["Document", "Content"],
                    "classification": "Document",
                    "main_topics": [],
                    "entities": []
                }
                
        except Exception as e:
            raise Exception(f"LLM processing failed: {str(e)}")
    
    # Main execution
    try:
        print(f"Processing Google Doc: {doc_url}")
        
        # Convert URL to export format
        export_url = convert_to_export_url(doc_url)
        print(f"Export URL: {export_url}")
        
        # Fetch document text
        document_text = fetch_document_text(export_url)
        print(f"Extracted {len(document_text)} characters")
        
        # Extract tags using LLM
        extraction_result = extract_tags_with_llm(document_text, openai_api_key, max_tags)
        
        # Return just the tags as requested
        tags = extraction_result.get("tags", [])
        print(f"Extracted {len(tags)} tags: {tags}")
        
        return tags
        
    except Exception as e:
        print(f"Error: {str(e)}")
        return []

# Simple usage function
def get_tags_from_google_doc(doc_url: str, api_key: str) -> List[str]:
    """
    Simplified function - just pass URL and get tags back
    
    Args:
        doc_url: Google Docs URL
        api_key: OpenAI API key
    
    Returns:
        List of tags
    """
    return extract_tags_from_google_doc(doc_url, api_key)

# Example usage
if __name__ == "__main__":
    # Example Google Docs URL (replace with your actual document)
    google_doc_url = "https://docs.google.com/document/d/1xZbZpByp-TeysQR7M8PzqidtoaJIWxcy/edit?tab=t.0"
    
    # Your OpenAI API key (replace with actual key)
    openai_key = "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"
    
    # Extract tags
    tags = get_tags_from_google_doc(google_doc_url, openai_key)
    
    # Print results
    print("Extracted Tags:")
    for i, tag in enumerate(tags, 1):
        print(f"{i}. {tag}")
    
    # Or as a simple list
    print(f"\nTags as list: {tags}")

# Alternative: Get full extraction results
def get_full_analysis_from_google_doc(doc_url: str, api_key: str) -> Dict[str, Any]:
    """
    Get complete analysis including tags, classification, topics, entities
    
    Args:
        doc_url: Google Docs URL  
        api_key: OpenAI API key
    
    Returns:
        Dictionary with tags, classification, topics, entities
    """
    
    def convert_to_export_url(google_docs_url: str) -> str:
        doc_id_match = re.search(r'/document/d/([a-zA-Z0-9-_]+)', google_docs_url)
        if not doc_id_match:
            raise ValueError("Invalid Google Docs URL format")
        doc_id = doc_id_match.group(1)
        return f"https://docs.google.com/document/d/{doc_id}/export?format=txt"
    
    def fetch_and_analyze(export_url: str, api_key: str) -> Dict[str, Any]:
        # Fetch text
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'}
        response = requests.get(export_url, headers=headers, timeout=30)
        response.raise_for_status()
        text = response.text.strip()
        
        if len(text) > 4000:
            text = text[:4000] + "..."
        
        # Analyze with LLM
        client = openai.OpenAI(api_key=api_key)
        
        prompt = f"""
Analyze this document and return JSON with tags and classification:

{text}

Return:
{{
  "tags": ["tag1", "tag2", "tag3"],
  "classification": "Document Type", 
  "main_topics": ["topic1", "topic2"],
  "entities": ["entity1", "entity2"]
}}
"""
        
        response = client.chat.completions.create(
            model="gpt-3.5-turbo",
            messages=[{"role": "user", "content": prompt}],
            max_tokens=500,
            temperature=0.3
        )
        
        try:
            return json.loads(response.choices[0].message.content.strip())
        except:
            return {"tags": ["Document"], "classification": "Unknown", "main_topics": [], "entities": []}
    
    try:
        export_url = convert_to_export_url(doc_url)
        return fetch_and_analyze(export_url, api_key)
    except Exception as e:
        return {"error": str(e), "tags": [], "classification": "Error", "main_topics": [], "entities": []}

# Quick test function
def quick_test():
    """Quick test with a public Google Doc"""
    
    # Public Google Doc example (Google Sheets tutorial)
    test_url = "https://docs.google.com/document/d/1BxiMVs0XRA5nFMdKvBdBZjgmUUqptlbs74OgvE2upms/edit"
    api_key = "your-openai-api-key-here"  # Replace with your key
    
    print("Testing Google Docs tag extraction...")
    
    # Test simple tag extraction
    tags = get_tags_from_google_doc(test_url, api_key)
    print(f"Simple tags: {tags}")
    
    # Test full analysis
    full_analysis = get_full_analysis_from_google_doc(test_url, api_key)
    print(f"Full analysis: {full_analysis}")

# Uncomment to test
# quick_test()