"""
Enterprise-grade streaming file parser for large lead imports
Handles CSV and Excel files with memory-efficient chunked processing
"""

import csv
import pandas as pd
from io import TextIOWrapper
import logging
from typing import Iterator, Dict, Any, List, Optional
from datetime import datetime

logger = logging.getLogger(__name__)


class StreamingLeadParser:
    """
    Memory-efficient streaming parser for large lead import files.
    Processes files in configurable chunks to prevent memory exhaustion.
    """
    
    def __init__(self, file_handler, chunk_size: int = 2000, encoding: str = 'utf-8'):
        """
        Initialize the streaming parser.
        
        Args:
            file_handler: File object (Django UploadedFile or file-like object)
            chunk_size: Number of records per chunk (default: 2000)
            encoding: File encoding (default: utf-8)
        """
        self.file_handler = file_handler
        self.chunk_size = chunk_size
        self.encoding = encoding
        self.total_rows = 0
        self.file_size = getattr(file_handler, 'size', 0)
        
    def get_file_info(self) -> Dict[str, Any]:
        """Get basic file information for progress estimation"""
        return {
            'file_size': self.file_size,
            'file_size_mb': round(self.file_size / (1024 * 1024), 2) if self.file_size else 0,
            'estimated_rows': self._estimate_row_count()
        }
    
    def _estimate_row_count(self) -> int:
        """Estimate total row count for progress tracking"""
        if not self.file_size:
            return 0
        
        # Rough estimation: ~100 bytes per row average
        estimated_rows = self.file_size // 100
        # Cap at reasonable limits
        return min(max(estimated_rows, 1000), 1000000)
    
    def parse_chunks(self) -> Iterator[List[Dict[str, Any]]]:
        """
        Parse file and yield chunks of lead data.
        
        Yields:
            List of dictionaries containing lead data for each chunk
        """
        file_name = getattr(self.file_handler, 'name', '').lower()
        
        if file_name.endswith('.csv'):
            yield from self._parse_csv_chunks()
        elif file_name.endswith(('.xlsx', '.xls')):
            yield from self._parse_excel_chunks()
        else:
            raise ValueError(f"Unsupported file format: {file_name}")
    
    def _parse_csv_chunks(self) -> Iterator[List[Dict[str, Any]]]:
        """Parse CSV file in chunks with encoding detection"""
        reader = None
        encodings = ['utf-8', 'utf-8-sig', 'latin-1', 'cp1252']
        
        # Try different encodings
        for encoding in encodings:
            try:
                self.file_handler.seek(0)
                if hasattr(self.file_handler, 'read'):
                    # Handle Django uploaded file
                    text_file = TextIOWrapper(self.file_handler, encoding=encoding)
                    reader = csv.DictReader(text_file)
                else:
                    reader = csv.DictReader(self.file_handler)
                break
            except UnicodeDecodeError:
                continue
        
        if not reader:
            raise ValueError("Unable to read CSV file with any supported encoding")
        
        # Validate and normalize column names
        if not reader.fieldnames:
            raise ValueError("CSV file has no headers")
        
        column_names = [str(col).strip().lower() for col in reader.fieldnames]
        
        # Validate required columns
        required_columns = ['name', 'mobile']
        missing_columns = [col for col in required_columns if col not in column_names]
        
        if missing_columns:
            raise ValueError(f"Missing required columns: {', '.join(missing_columns)}")
        
        # Process rows in streaming mode
        current_chunk = []
        for row_num, row in enumerate(reader):
            try:
                lead_data = self._normalize_row(row, row_num + 1)
                
                # Skip invalid records
                if not lead_data or not lead_data.get('name') or not lead_data.get('mobile'):
                    continue
                
                current_chunk.append(lead_data)
                
                # Yield chunk when it reaches the configured size
                if len(current_chunk) >= self.chunk_size:
                    yield current_chunk
                    current_chunk = []
                    
            except Exception as e:
                logger.warning(f"Error processing row {row_num + 1}: {e}")
                continue
        
        # Yield remaining records
        if current_chunk:
            yield current_chunk
    
    def _parse_excel_chunks(self) -> Iterator[List[Dict[str, Any]]]:
        """Parse Excel file in chunks using pandas with memory optimization"""
        try:
            # Read Excel file with memory optimization
            df = pd.read_excel(
                self.file_handler,
                dtype=str,  # Read all as strings to avoid type inference issues
                na_values=['', 'NULL', 'null', 'None', 'none'],
                keep_default_na=False
            )
            
            # Normalize column names
            df.columns = df.columns.str.strip().str.lower()
            
            # Validate required columns
            required_columns = ['name', 'mobile']
            missing_columns = [col for col in required_columns if col not in df.columns]
            
            if missing_columns:
                raise ValueError(f"Missing required columns: {', '.join(missing_columns)}")
            
            # Process DataFrame in chunks
            total_rows = len(df)
            for start_idx in range(0, total_rows, self.chunk_size):
                end_idx = min(start_idx + self.chunk_size, total_rows)
                chunk_df = df.iloc[start_idx:end_idx]
                
                current_chunk = []
                for idx, row in chunk_df.iterrows():
                    try:
                        lead_data = self._normalize_row(row.to_dict(), idx + 1)
                        
                        # Skip invalid records
                        if not lead_data or not lead_data.get('name') or not lead_data.get('mobile'):
                            continue
                        
                        current_chunk.append(lead_data)
                        
                    except Exception as e:
                        logger.warning(f"Error processing Excel row {idx + 1}: {e}")
                        continue
                
                if current_chunk:
                    yield current_chunk
                    
        except Exception as e:
            logger.error(f"Error parsing Excel file: {e}")
            raise ValueError(f"Failed to parse Excel file: {str(e)}")
    
    def _normalize_row(self, row: Dict[str, Any], row_num: int) -> Optional[Dict[str, Any]]:
        """
        Normalize a single row of data into lead format.
        
        Args:
            row: Raw row data from CSV/Excel
            row_num: Row number for error reporting
            
        Returns:
            Normalized lead data dictionary or None if invalid
        """
        try:
            lead_data = {
                'name': str(row.get('name', '')).strip(),
                'mobile': str(row.get('mobile', '')).strip(),
                'email': str(row.get('email', '')).strip(),
                'alt_mobile': str(row.get('alt_mobile', '')).strip(),
                'whatsapp_no': str(row.get('whatsapp_no', '')).strip(),
                'alt_email': str(row.get('alt_email', '')).strip(),
                'address': str(row.get('address', '')).strip(),
                'city': str(row.get('city', '')).strip(),
                'state': str(row.get('state', '')).strip(),
                'postalcode': str(row.get('postalcode', '')).strip(),
                'country': str(row.get('country', '')).strip(),
                'status': str(row.get('status', 'lead')).strip() or 'lead',
                'status_description': str(row.get('status_description', '')).strip(),
                'lead_source': str(row.get('lead_source', '')).strip(),
                'lead_source_description': str(row.get('lead_source_description', '')).strip(),
                'refered_by': str(row.get('refered_by', '')).strip(),
                'campaign_id': str(row.get('campaign_id', '')).strip(),
                'course_name': str(row.get('course_name', '')).strip(),
                'course_amount': str(row.get('course_amount', '')).strip(),
                'exp_revenue': str(row.get('exp_revenue', '')).strip(),
                'description': str(row.get('description', '')).strip(),
                'company': str(row.get('company', '')).strip(),  # For related lead detection
                'row_number': row_num  # Track original row number for error reporting
            }
            
            # Handle date fields with validation
            date_fields = {
                'exp_close_date': '%Y-%m-%d',
                'followup_datetime': '%Y-%m-%d %H:%M:%S',
                'birthdate': '%Y-%m-%d'
            }
            
            for field, date_format in date_fields.items():
                date_value = str(row.get(field, '')).strip()
                if date_value:
                    try:
                        if field == 'followup_datetime':
                            lead_data[field] = datetime.strptime(date_value, date_format)
                        else:
                            lead_data[field] = datetime.strptime(date_value, date_format).date()
                    except ValueError:
                        # Skip invalid dates but keep other data
                        logger.debug(f"Invalid {field} format in row {row_num}: {date_value}")
                        continue
            
            # Clean and validate mobile number
            mobile = lead_data['mobile']
            if mobile:
                # Remove common formatting characters
                mobile = ''.join(c for c in mobile if c.isdigit() or c in '+-')
                lead_data['mobile'] = mobile
            
            # Clean email
            email = lead_data['email']
            if email and '@' not in email:
                lead_data['email'] = ''  # Clear invalid emails
            
            return lead_data
            
        except Exception as e:
            logger.warning(f"Error normalizing row {row_num}: {e}")
            return None


class ImportProgressTracker:
    """
    Track import progress for real-time updates and monitoring.
    """
    
    def __init__(self, session_id: str, estimated_total: int = 0):
        self.session_id = session_id
        self.estimated_total = estimated_total
        self.processed_count = 0
        self.error_count = 0
        self.start_time = None
        self.current_stage = 'initializing'
        
    def start(self):
        """Start tracking"""
        self.start_time = datetime.now()
        self.current_stage = 'processing'
        
    def update_progress(self, processed: int, errors: int = 0, stage: str = None):
        """Update progress metrics"""
        self.processed_count = processed
        self.error_count = errors
        if stage:
            self.current_stage = stage
            
    def get_progress_data(self) -> Dict[str, Any]:
        """Get current progress data for frontend"""
        elapsed_time = 0
        processing_rate = 0
        eta_seconds = 0
        
        if self.start_time:
            elapsed_time = (datetime.now() - self.start_time).total_seconds()
            if elapsed_time > 0:
                processing_rate = self.processed_count / elapsed_time
                
                if processing_rate > 0 and self.estimated_total > self.processed_count:
                    eta_seconds = (self.estimated_total - self.processed_count) / processing_rate
        
        percentage = 0
        if self.estimated_total > 0:
            percentage = min(100, (self.processed_count / self.estimated_total) * 100)
        
        return {
            'session_id': self.session_id,
            'current_stage': self.current_stage,
            'processed': self.processed_count,
            'total': self.estimated_total,
            'percentage': round(percentage, 2),
            'processing_rate': round(processing_rate, 2),
            'eta_seconds': int(eta_seconds),
            'error_count': self.error_count,
            'elapsed_time': int(elapsed_time)
        }
