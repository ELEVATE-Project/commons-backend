"""Simple text extraction functionality for CSV and TXT files"""

import io
import logging
from typing import List, Tuple
import pandas as pd

logger = logging.getLogger('django')


class CSVExtractor:
    """Handles CSV content extraction"""

    def __init__(self, excel_max_rows: int = 50, excel_max_cols: int = 20):
        self.excel_max_rows = excel_max_rows
        self.excel_max_cols = excel_max_cols

    def extract_comprehensive_content_for_urls(self, content_bytes: bytes) -> Tuple[str, List[str]]:
        """
        Extract comprehensive CSV content (CSV files don't have hyperlinks, but we maintain consistency)
        """
        try:
            logger.info("=" * 80)
            logger.info("EXTRACTING COMPREHENSIVE CSV CONTENT FOR URL EXTRACTION")
            logger.info("=" * 80)

            # For CSV, there are no embedded hyperlinks, so just extract all text
            df_full = pd.read_csv(io.BytesIO(content_bytes))
            comprehensive_text = df_full.to_csv(index=False)

            logger.info(f"CSV extraction complete:")
            logger.info(f"  - Text content: {len(comprehensive_text)} characters")
            logger.info(f"  - Rows: {len(df_full)}, Columns: {len(df_full.columns)}")
            logger.info("  - No hyperlinks (CSV format doesn't support embedded links)")

            return comprehensive_text, []

        except Exception as e:
            logger.error(f"Error extracting comprehensive CSV content: {e}")
            return "", []

    def extract_text(self, file_path) -> str:
        """
        Extract text from CSV (file path) with limits
        """
        df = pd.read_csv(file_path, nrows=self.excel_max_rows)
        if len(df.columns) > self.excel_max_cols:
            df = df.iloc[:, :self.excel_max_cols]
        return df.to_string(max_rows=self.excel_max_rows, max_cols=self.excel_max_cols)

    def extract_text_from_object(self, file) -> str:
        """
        Extract text from CSV (file object) with limits
        """
        df = pd.read_csv(file, nrows=self.excel_max_rows)
        if len(df.columns) > self.excel_max_cols:
            df = df.iloc[:, :self.excel_max_cols]
        return df.to_string(max_rows=self.excel_max_rows, max_cols=self.excel_max_cols)


class TXTExtractor:
    """Handles TXT content extraction"""

    def extract_comprehensive_content_for_urls(self, content_bytes: bytes) -> Tuple[str, List[str]]:
        """
        Extract comprehensive TXT content (TXT files don't have hyperlinks, but we maintain consistency)
        """
        try:
            logger.info("=" * 80)
            logger.info("EXTRACTING COMPREHENSIVE TXT CONTENT FOR URL EXTRACTION")
            logger.info("=" * 80)

            # For TXT, there are no embedded hyperlinks, so just extract all text
            try:
                comprehensive_text = content_bytes.decode('utf-8', errors='ignore')
            except:
                comprehensive_text = str(content_bytes, errors='ignore')

            logger.info(f"TXT extraction complete:")
            logger.info(f"  - Text content: {len(comprehensive_text)} characters")
            logger.info("  - No hyperlinks (TXT format doesn't support embedded links)")

            return comprehensive_text, []

        except Exception as e:
            logger.error(f"Error extracting comprehensive TXT content: {e}")
            return "", []

    def extract_text(self, file_path) -> str:
        """
        Extract text from plain text file (file path)
        """
        with open(file_path, 'r', encoding='utf-8', errors='ignore') as f:
            return f.read()

    def extract_text_from_object(self, file) -> str:
        """
        Extract text from plain text file (file object)
        """
        content = file.read()
        if isinstance(content, bytes):
            content = content.decode('utf-8', errors='ignore')
        return content