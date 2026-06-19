"""
Quick test script for MarkdownExtractor
Run this to verify the Excel to Markdown conversion works correctly
"""

import io
import pandas as pd
from chatbot.utils.knowledge_service.extractor.markdown_extractor import MarkdownExtractor

def test_markdown_extractor():
    """Test the MarkdownExtractor with sample data"""
    
    # Create sample Excel data
    data = {
        'Name': ['John Doe', 'Jane Smith', 'Bob Johnson'],
        'Age': [30, 25, 35],
        'City': ['New York', 'Los Angeles', 'Chicago'],
        'Email': ['john@example.com', 'jane@example.com', 'bob@example.com']
    }
    
    df = pd.DataFrame(data)
    
    # Save to bytes
    excel_buffer = io.BytesIO()
    df.to_excel(excel_buffer, index=False, sheet_name='TestSheet')
    excel_bytes = excel_buffer.getvalue()
    
    # Initialize extractor
    extractor = MarkdownExtractor(subdoc_max_chars=5000)
    
    print("=" * 80)
    print("Testing MarkdownExtractor")
    print("=" * 80)
    
    # Test 1: Basic conversion
    print("\n1. Testing spreadsheet_to_markdown():")
    print("-" * 80)
    markdown_output = extractor.spreadsheet_to_markdown(excel_bytes, "test_file.xlsx")
    print(markdown_output)
    
    # Test 2: Limited content extraction
    print("\n2. Testing extract_limited_content():")
    print("-" * 80)
    limited_output = extractor.extract_limited_content(excel_bytes, max_chars=500, filename="test_file.xlsx")
    print(limited_output)
    print(f"\nLength: {len(limited_output)} characters")
    
    # Test 3: Comprehensive extraction with URLs
    print("\n3. Testing extract_comprehensive_content_for_urls():")
    print("-" * 80)
    comprehensive_output, urls = extractor.extract_comprehensive_content_for_urls(excel_bytes, "test_file.xlsx")
    print(f"Content length: {len(comprehensive_output)} characters")
    print(f"URLs extracted: {len(urls)}")
    print(f"Sample content:\n{comprehensive_output[:500]}...")
    
    # Test 4: CSV conversion
    print("\n4. Testing CSV conversion:")
    print("-" * 80)
    csv_buffer = io.BytesIO()
    df.to_csv(csv_buffer, index=False)
    csv_bytes = csv_buffer.getvalue()
    
    csv_markdown = extractor.spreadsheet_to_markdown(csv_bytes, "test_file.csv")
    print(csv_markdown)
    
    print("\n" + "=" * 80)
    print("All tests completed successfully!")
    print("=" * 80)

if __name__ == "__main__":
    test_markdown_extractor()
