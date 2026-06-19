# Excel to Markdown Conversion Integration

## Overview
Integrated a new `MarkdownExtractor` class that converts Excel and CSV files to clean Markdown format using the `tabulate` library. This improves LLM processing of spreadsheet data by providing structured, readable Markdown tables instead of raw CSV or pandas string output.

## Changes Made

### 1. New File: `markdown_extractor.py`
**Location:** `chatbot/utils/knowledge_service/extractor/markdown_extractor.py`

**Class:** `MarkdownExtractor`

**Key Features:**
- Converts Excel (.xlsx, .xls) and CSV files to Markdown format
- Uses `tabulate` library with 'pipe' format for clean Markdown tables
- Sanitizes cell content by converting line breaks to HTML `<br>` tags
- Post-processes Markdown to clean up formatting issues
- Extracts hyperlinks from Excel files using `openpyxl`
- Supports both limited and comprehensive content extraction

**Main Methods:**
- `spreadsheet_to_markdown(content_bytes, filename)` - Core conversion logic
- `extract_limited_content(content_bytes, max_chars, filename)` - For LLM processing with character limits
- `extract_comprehensive_content_for_urls(content_bytes, filename)` - Full extraction with URL extraction
- `sanitize_cell_content(df)` - Cleans cell content before conversion
- `post_process_markdown(markdown_text)` - Cleans up generated Markdown

### 2. Updated: `document_extractor.py`
**Location:** `chatbot/utils/knowledge_service/extractor/document_extractor.py`

**Changes:**
1. **Import Added:** `from .markdown_extractor import MarkdownExtractor`
2. **Initialization:** Added `self.markdown_extractor = MarkdownExtractor(subdoc_max_chars)` in `__init__`
3. **Excel Processing:** Updated Excel file extraction to use `MarkdownExtractor` instead of `ExcelExtractor`
4. **CSV Processing:** Updated CSV file extraction to use `MarkdownExtractor` for consistency

**Before (Excel):**
```python
text = self.excel_extractor.extract_limited_content(content_bytes, max_chars)
```

**After (Excel):**
```python
filename = f"spreadsheet.{file_extension}"
text = self.markdown_extractor.extract_limited_content(content_bytes, max_chars, filename)
```

**Before (CSV):**
```python
df = pd.read_csv(io.BytesIO(content_bytes), nrows=self.excel_max_rows)
text = df.to_string(max_rows=self.excel_max_rows, max_cols=self.excel_max_cols)
```

**After (CSV):**
```python
filename = "spreadsheet.csv"
text = self.markdown_extractor.extract_limited_content(content_bytes, max_chars, filename)
```

## Benefits

### 1. Better LLM Understanding
- Markdown tables are more structured and easier for LLMs to parse
- Clear column headers and row separators
- Preserves table structure better than CSV or pandas string output

### 2. Cleaner Output
- Removes repetitive hyphens and excessive whitespace
- Standardizes table separators
- Handles multi-line cell content with `<br>` tags

### 3. Consistent Processing
- Both Excel and CSV files now use the same conversion pipeline
- Uniform output format regardless of input file type

### 4. URL Extraction
- Maintains hyperlink extraction from Excel files using `openpyxl`
- Returns both Markdown content and extracted URLs

## Example Output

### Input (Excel/CSV):
```
Name, Age, City
John, 30, New York
Jane, 25, Los Angeles
```

### Output (Markdown):
```markdown
# spreadsheet.xlsx

## Sheet1

| 0    | 1   | 2           |
|:-----|:----|:------------|
| Name | Age | City        |
| John | 30  | New York    |
| Jane | 25  | Los Angeles |

---
```

## Dependencies
- `pandas` - For reading Excel/CSV files
- `tabulate` - For converting DataFrames to Markdown tables
- `openpyxl` (optional) - For extracting hyperlinks from Excel files

## Backward Compatibility
- `ExcelExtractor` class remains unchanged for any legacy code that might use it directly
- All existing functionality is preserved
- The integration is transparent to calling code

## Testing Recommendations
1. Test with various Excel files (single/multiple sheets)
2. Test with CSV files
3. Test with files containing special characters
4. Test with files containing hyperlinks
5. Verify character limit truncation works correctly
6. Check that empty sheets are handled properly

## Notes
- The `ExcelExtractor` class is still available and functional
- The `CSVExtractor` is no longer used for text extraction but may still be referenced elsewhere
- All logging statements are preserved for debugging
- Character limits are respected for LLM processing
