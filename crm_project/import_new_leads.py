import os
import sys
import django
import pandas as pd

# Set up Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'crm.settings')
sys.path.append(os.path.dirname(os.path.abspath(__file__)))
django.setup()

from dashboard.models import Lead
from services.duplicate_detector import DuplicateDetector

def import_new_leads():
    """Import leads from new_leads.csv"""
    csv_file = 'unique_new_leads.csv'
    
    try:
        # Read the CSV file
        df = pd.read_csv(csv_file)
        print(f"Found {len(df)} leads in {csv_file}")
        
        # Initialize duplicate detector with company_id=1 (default company)
        detector = DuplicateDetector(company_id=1)
        imported_count = 0
        skipped_count = 0
        
        for index, row in df.iterrows():
            # Check for duplicates
            lead_data = {
                'name': row['name'],
                'mobile': str(row['mobile']),
                'email': row.get('email', '')
            }
            duplicate_result = detector.detect_duplicates_for_lead(lead_data)
            
            if duplicate_result['status'] != 'new':
                print(f"Skipping duplicate lead: {row['name']} - {row['mobile']}")
                skipped_count += 1
                continue
            
            # Create new lead
            lead = Lead.objects.create(
                name=row['name'],
                mobile=str(row['mobile']),
                email=row.get('email', ''),
                city=row.get('city', ''),
                status=row.get('status', 'lead'),
                lead_source=row.get('lead_source', ''),
                assigned_user=None  # Unassigned by default
            )
            
            imported_count += 1
            print(f"Imported lead: {lead.name} - {lead.mobile}")
        
        print(f"\nImport Summary:")
        print(f"Total leads processed: {len(df)}")
        print(f"Successfully imported: {imported_count}")
        print(f"Skipped (duplicates): {skipped_count}")
        
    except FileNotFoundError:
        print(f"Error: {csv_file} not found!")
    except Exception as e:
        print(f"Error importing leads: {str(e)}")

if __name__ == "__main__":
    import_new_leads()
