import os
import sys
import django
import argparse
import requests
import json
from pathlib import Path
from datetime import datetime
from typing import List, Dict, Any

# Setup Django environment
# sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))
# os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'shikshalokam_mohini.settings')
django.setup()

from chatbot.models import Media

"""
Vector DB Source Verifier - Check which media documents exist in vector database

COMMAND LINE:
    python verify_vector_db_sources.py [--api-url URL] [--company-id ID] [--batch-size N] [--output FILE]

    Examples:
        python verify_vector_db_sources.py
        python verify_vector_db_sources.py --company-id acme --batch-size 50

SHELL_PLUS:
    verifier = VectorDBSourceVerifier(api_base_url=None, company_id=None, batch_size=100)
    verifier.run()

ENVIRONMENT:
    VECTOR_DB_BASE_URL - API base URL (required if not passed via --api-url)

OUTPUT:
    JSON file with found/not_found source IDs and summary statistics
"""


class VectorDBSourceVerifier:
    """Verify which media documents exist in the vector database"""
    
    def __init__(
        self,
        api_base_url: str = None,
        output_file: str = None,
        batch_size: int = 100,
        company_id: str = None
    ):
        """
        Initialize the verifier
        
        Args:
            api_base_url: Base URL of the API (default: from VECTOR_DB_BASE_URL env var)
            output_file: Path to output JSON file (default: verify_results_TIMESTAMP.json)
            batch_size: Number of IDs to send per request
            company_id: Optional company ID to filter media
        """
        # Get API URL from environment if not provided
        if api_base_url is None:
            api_base_url = os.getenv('VECTOR_DB_BASE_URL')
            if not api_base_url:
                raise ValueError(
                    "API URL not provided. Either pass --api-url argument or set VECTOR_DB_BASE_URL environment variable"
                )
            # Add http:// if not present
            if not api_base_url.startswith(('http://', 'https://')):
                api_base_url = f"http://{api_base_url}"
        
        self.api_base_url = api_base_url.rstrip('/')
        self.verify_endpoint = f"{self.api_base_url}/api/documents/verify-sources"
        self.batch_size = batch_size
        self.company_id = company_id
        
        # Set default output file if not provided
        if output_file is None:
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            output_file = f"verify_results_{timestamp}.json"
        
        self.output_file = Path(output_file)
        
        print(f"{'='*80}")
        print(f"Vector DB Source Verification")
        print(f"{'='*80}")
        print(f"API Base URL: {self.api_base_url}")
        print(f"Verify Endpoint: {self.verify_endpoint}")
        print(f"Output File: {self.output_file}")
        print(f"Batch Size: {self.batch_size}")
        if self.company_id:
            print(f"Company ID Filter: {self.company_id}")
        print(f"{'='*80}\n")
    
    def fetch_media_ids(self) -> List[str]:
        """
        Fetch all media IDs from the chatbot_media table
        
        Returns:
            List of media ID strings
        """
        print("Fetching media IDs from database...")
        
        # Build query
        queryset = Media.objects.all()
        
        # Filter by company if specified
        if self.company_id:
            queryset = queryset.filter(company_bot__company__slug=self.company_id)
        
        # Get IDs and convert to strings
        media_ids = list(queryset.values_list('id', flat=True))
        media_ids_str = [str(id) for id in media_ids]
        
        print(f"✅ Found {len(media_ids_str)} media records in database")
        
        return media_ids_str
    
    def verify_sources(self, source_ids: List[str]) -> Dict[str, Any]:
        """
        Call the verify-sources endpoint
        
        Args:
            source_ids: List of source IDs to verify
            
        Returns:
            API response as dictionary
        """
        payload = {
            "source_ids": source_ids
        }
        
        print(f"\nCalling verify-sources endpoint...")
        print(f"Request payload: {json.dumps(payload, indent=2)}")
        
        try:
            response = requests.post(
                self.verify_endpoint,
                json=payload,
                headers={'Content-Type': 'application/json'},
                timeout=60
            )
            
            if response.status_code == 200:
                result = response.json()
                print(f"✅ API call successful")
                return result
            else:
                print(f"❌ API call failed with status {response.status_code}")
                print(f"Response: {response.text}")
                return {
                    "error": True,
                    "status_code": response.status_code,
                    "message": response.text
                }
        
        except requests.exceptions.RequestException as e:
            print(f"❌ Network error: {str(e)}")
            return {
                "error": True,
                "message": str(e)
            }
    
    def process_in_batches(self, media_ids: List[str]) -> List[Dict[str, Any]]:
        """
        Process media IDs in batches
        
        Args:
            media_ids: List of all media IDs
            
        Returns:
            List of batch results
        """
        total_ids = len(media_ids)
        num_batches = (total_ids + self.batch_size - 1) // self.batch_size
        
        print(f"\nProcessing {total_ids} IDs in {num_batches} batch(es)...")
        
        batch_results = []
        
        for i in range(0, total_ids, self.batch_size):
            batch_num = (i // self.batch_size) + 1
            batch = media_ids[i:i + self.batch_size]
            
            print(f"\n{'='*80}")
            print(f"Batch {batch_num}/{num_batches} - Processing {len(batch)} IDs")
            print(f"{'='*80}")
            
            result = self.verify_sources(batch)
            result['batch_number'] = batch_num
            result['batch_size'] = len(batch)
            batch_results.append(result)
        
        return batch_results
    
    def aggregate_results(self, batch_results: List[Dict[str, Any]]) -> Dict[str, Any]:
        """
        Aggregate results from all batches
        
        Args:
            batch_results: List of batch results
            
        Returns:
            Aggregated results dictionary
        """
        aggregated = {
            "total_requested": 0,
            "found": [],
            "not_found": [],
            "found_count": 0,
            "not_found_count": 0,
            "batches": batch_results,
            "timestamp": datetime.now().isoformat(),
            "api_endpoint": self.verify_endpoint
        }
        
        for batch in batch_results:
            if not batch.get('error'):
                aggregated["total_requested"] += batch.get("total_requested", 0)
                aggregated["found"].extend(batch.get("found", []))
                aggregated["not_found"].extend(batch.get("not_found", []))
        
        aggregated["found_count"] = len(aggregated["found"])
        aggregated["not_found_count"] = len(aggregated["not_found"])
        
        return aggregated
    
    def save_results(self, results: Dict[str, Any]):
        """
        Save results to JSON file
        
        Args:
            results: Results dictionary to save
        """
        print(f"\nSaving results to {self.output_file}...")
        
        with open(self.output_file, 'w') as f:
            json.dump(results, f, indent=2)
        
        print(f"✅ Results saved successfully")
    
    def print_summary(self, results: Dict[str, Any]):
        """
        Print summary of results
        
        Args:
            results: Results dictionary
        """
        print(f"\n{'='*80}")
        print(f"VERIFICATION SUMMARY")
        print(f"{'='*80}")
        print(f"Total IDs Requested:    {results['total_requested']}")
        print(f"Found in Vector DB:     {results['found_count']} ({results['found_count']/results['total_requested']*100:.1f}%)")
        print(f"Not Found in Vector DB: {results['not_found_count']} ({results['not_found_count']/results['total_requested']*100:.1f}%)")
        print(f"Output File:            {self.output_file}")
        print(f"{'='*80}\n")
        
        if results['not_found_count'] > 0:
            print(f"⚠️  {results['not_found_count']} documents are missing from the vector database")
            print(f"   Check {self.output_file} for the list of missing IDs")
        else:
            print(f"✅ All documents are present in the vector database!")
    
    def run(self):
        """
        Run the verification process
        """
        try:
            # Step 1: Fetch media IDs from database
            media_ids = self.fetch_media_ids()
            
            if not media_ids:
                print("⚠️  No media records found in database")
                return
            
            # Step 2: Verify sources in batches
            batch_results = self.process_in_batches(media_ids)
            
            # Step 3: Aggregate results
            aggregated_results = self.aggregate_results(batch_results)
            
            # Step 4: Save results
            self.save_results(aggregated_results)
            
            # Step 5: Print summary
            self.print_summary(aggregated_results)
            
        except Exception as e:
            print(f"\n❌ ERROR: {str(e)}")
            import traceback
            traceback.print_exc()
            sys.exit(1)


def main():
    """Main entry point for command-line usage"""
    parser = argparse.ArgumentParser(
        description='Verify which media documents exist in the AI vector database',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  # Verify all documents (uses VECTOR_DB_BASE_URL from environment)
  python verify_vector_db_sources.py
  
  # Override with custom API URL
  python verify_vector_db_sources.py --api-url http://localhost:8000
  
  # Verify documents for a specific company
  python verify_vector_db_sources.py --company-id my-company
  
  # Specify custom output file
  python verify_vector_db_sources.py --output my_results.json
  
  # Process in smaller batches
  python verify_vector_db_sources.py --batch-size 50
        """
    )
    
    parser.add_argument(
        '--api-url',
        help='Base URL of the API (default: from VECTOR_DB_BASE_URL environment variable)'
    )
    parser.add_argument(
        '--output',
        help='Output JSON file path (default: verify_results_TIMESTAMP.json)'
    )
    parser.add_argument(
        '--batch-size',
        type=int,
        default=100,
        help='Number of IDs to process per batch (default: 100)'
    )
    parser.add_argument(
        '--company-id',
        help='Filter media by company slug/ID'
    )
    
    args = parser.parse_args()
    
    try:
        verifier = VectorDBSourceVerifier(
            api_base_url=args.api_url,
            output_file=args.output,
            batch_size=args.batch_size,
            company_id=args.company_id
        )
        
        verifier.run()
        
    except Exception as e:
        print(f"\n❌ FATAL ERROR: {str(e)}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
