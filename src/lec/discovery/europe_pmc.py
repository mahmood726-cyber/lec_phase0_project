"""Europe PMC Open Access Index.

Search and retrieve Open Access PDFs from Europe PMC.
"""

import requests
import time
from pathlib import Path
from typing import Optional, List, Dict

from lec.core import write_json, utc_now_iso, get_logger

logger = get_logger("discovery.epmc")


class EuropePMCIndex:
    """Europe PMC Open Access Discovery."""

    SEARCH_URL = "https://www.ebi.ac.uk/europepmc/webservices/rest/search"
    PDF_BASE_URL = "https://europepmc.org/backend/ptpmcrender.fcgi"

    def __init__(self, output_dir: Path, demo_mode: bool = False):
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)
        self.pdf_dir = self.output_dir / "pdfs"
        self.pdf_dir.mkdir(parents=True, exist_ok=True)
        self.demo_mode = demo_mode

    def search(self, query: str, limit: int = 100) -> List[Dict]:
        """Search Europe PMC for OA articles."""
        if self.demo_mode:
            logger.info("Running in DEMO MODE (no API calls)")
            return [
                {
                    "pmcid": "PMC123456",
                    "title": f"Demo Article regarding {query}",
                    "doi": "10.1038/demo.123",
                    "journalTitle": "Journal of Demo Evidence",
                    "pubYear": "2025"
                },
                {
                    "pmcid": "PMC789012",
                    "title": "Another Great Study",
                    "doi": "10.1056/demo.456",
                    "journalTitle": "NEJM Demo",
                    "pubYear": "2024"
                }
            ]

        # Ensure we only get OA articles with full text
        full_query = f'{query} AND OPEN_ACCESS:Y AND SRC:PMC'
        
        params = {
            "query": full_query,
            "format": "json",
            "pageSize": min(limit, 1000),
            "resultType": "core"
        }

        try:
            response = requests.get(self.SEARCH_URL, params=params, timeout=60)
            response.raise_for_status()
            data = response.json()
            
            articles = data.get('resultList', {}).get('result', [])
            return articles
        except Exception as e:
            logger.error(f"Error searching Europe PMC: {e}")
            return []

    def download_pdf(self, pmcid: str, max_retries: int = 3) -> Optional[Path]:
        """Download PDF for a specific PMCID with retries."""
        if not pmcid.startswith("PMC"):
            pmcid = f"PMC{pmcid}"
            
        output_path = self.pdf_dir / f"{pmcid}.pdf"
        
        # Return if exists
        if output_path.exists():
            return output_path
            
        if self.demo_mode:
            with open(output_path, "wb") as f:
                f.write(b"%PDF-1.4 Demo PDF content")
            return output_path

        pdf_url = f"{self.PDF_BASE_URL}?accid={pmcid}&blobtype=pdf"
        
        for attempt in range(max_retries):
            try:
                response = requests.get(pdf_url, timeout=120, stream=True)
                
                # Validation
                if response.status_code != 200:
                    if attempt < max_retries - 1:
                        time.sleep(2 ** attempt)  # Exponential backoff
                        continue
                    return None
                
                content_type = response.headers.get('content-type', '').lower()
                if 'pdf' not in content_type and 'application/octet-stream' not in content_type:
                    # Some servers might not return proper PDF content type but still be PDFs
                    pass
                    
                # Use streaming write
                with open(output_path, 'wb') as f:
                    for chunk in response.iter_content(chunk_size=8192):
                        if chunk:
                            f.write(chunk)
                
                # Post-download validation: check size and header
                if output_path.stat().st_size < 5000:
                    output_path.unlink()
                    if attempt < max_retries - 1:
                        time.sleep(2 ** attempt)
                        continue
                    return None
                    
                with open(output_path, "rb") as f:
                    header = f.read(5)
                    if header != b"%PDF-":
                        output_path.unlink()
                        if attempt < max_retries - 1:
                            time.sleep(2 ** attempt)
                            continue
                        return None
                    
                return output_path
                
            except Exception as e:
                logger.error(f"Error downloading {pmcid} (attempt {attempt+1}): {e}")
                if output_path.exists():
                    output_path.unlink()
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
                else:
                    return None
        return None

    def run(self, topic: str, query: str, limit: int = 50) -> Path:
        """Run discovery and download PDFs for a topic."""
        articles = self.search(query, limit)
        
        results = []
        downloaded = 0
        
        for article in articles:
            pmcid = article.get('pmcid')
            result = {
                "pmcid": pmcid,
                "title": article.get('title'),
                "doi": article.get('doi'),
                "journal": article.get('journalTitle'),
                "year": article.get('pubYear'),
                "pdf_path": None
            }
            
            if pmcid:
                pdf_path = self.download_pdf(pmcid)
                if pdf_path:
                    result["pdf_path"] = str(pdf_path)
                    downloaded += 1
                time.sleep(0.5)  # Rate limit
            
            results.append(result)

        output_data = {
            "topic": topic,
            "created_at_utc": utc_now_iso(),
            "source": "europe_pmc",
            "query": query,
            "total_found": len(articles),
            "downloaded": downloaded,
            "articles": results
        }
        
        output_path = self.output_dir / f"epmc_discovery_{topic}.json"
        write_json(output_path, output_data)
        
        return output_path
