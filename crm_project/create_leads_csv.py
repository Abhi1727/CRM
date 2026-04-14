import csv
import random
from datetime import datetime, timedelta
import os

# Sample data for generating leads
first_names = [
    "James", "John", "Robert", "Michael", "William", "David", "Richard", "Charles", "Joseph", "Thomas",
    "Christopher", "Daniel", "Paul", "Mark", "Donald", "Steven", "Andrew", "Joshua", "Kevin", "Brian",
    "George", "Edward", "Ronald", "Timothy", "Jason", "Jeffrey", "Ryan", "Jacob", "Gary", "Nicholas",
    "Eric", "Jonathan", "Stephen", "Larry", "Justin", "Scott", "Brandon", "Benjamin", "Samuel", "Gregory",
    "Frank", "Alexander", "Raymond", "Patrick", "Jack", "Dennis", "Jerry", "Tyler", "Aaron", "Jose",
    "Adam", "Henry", "Nathan", "Douglas", "Zachary", "Peter", "Kyle", "Walter", "Ethan", "Jeremy",
    "Harold", "Christian", "Sean", "Larry", "Joe", "Juan", "Wayne", "Billy", "Louis", "Russell",
    "Randy", "Vincent", "Bobby", "Eugene", "Sidney", "Marty", "Clarence", "Owen", "Oliver", "Luke"
]

last_names = [
    "Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis", "Rodriguez", "Martinez",
    "Hernandez", "Lopez", "Gonzalez", "Wilson", "Anderson", "Thomas", "Taylor", "Moore", "Jackson", "Martin",
    "Lee", "Perez", "Thompson", "White", "Harris", "Sanchez", "Clark", "Ramirez", "Lewis", "Robinson",
    "Walker", "Young", "Allen", "King", "Wright", "Scott", "Torres", "Nguyen", "Hill", "Flores",
    "Green", "Adams", "Baker", "Gonzalez", "Nelson", "Carter", "Mitchell", "Perez", "Roberts", "Turner",
    "Phillips", "Campbell", "Parker", "Evans", "Edwards", "Collins", "Stewart", "Sanchez", "Morris", "Morris",
    "Rogers", "Reed", "Cook", "Morgan", "Bell", "Murphy", "Bailey", "Rivera", "Cooper", "Richardson",
    "Cox", "Howard", "Ward", "Torres", "Peterson", "Gray", "Ramirez", "James", "Watson", "Brooks"
]

companies = [
    "Tech Solutions Inc", "Digital Dynamics", "Innovation Labs", "Global Systems", "Future Tech",
    "Smart Solutions", "Data Analytics Pro", "Cloud Computing Co", "Cyber Security Ltd", "AI Innovations",
    "Mobile First Tech", "Web Development Pro", "Software Solutions", "IT Consulting Group", "Tech Support Inc",
    "Digital Marketing Pro", "E-commerce Solutions", "App Development Co", "Cloud Services Ltd", "Data Science Pro",
    "Machine Learning Inc", "Blockchain Solutions", "IoT Technologies", "Robotics Systems", "Automation Pro",
    "Business Solutions", "Enterprise Systems", "Startup Tech Co", "Growth hacking Inc", "Digital Transformation",
    "Software Engineering Pro", "IT Infrastructure Co", "Network Solutions", "Database Management Inc", "Security Systems",
    "Web Hosting Pro", "Domain Registration Co", "Email Marketing Inc", "Social Media Pro", "Content Management",
    "Customer Relationship Inc", "Sales Automation Co", "Marketing Automation Pro", "Lead Generation Inc", "Conversion Optimization",
    "Analytics Solutions", "Business Intelligence Co", "Data Visualization Pro", "Reporting Systems Inc", "Dashboard Solutions",
    "Project Management Pro", "Task Automation Co", "Workflow Solutions Inc", "Process Automation Pro", "Efficiency Systems"
]

industries = [
    "Technology", "Healthcare", "Finance", "Education", "Retail", "Manufacturing", "Real Estate",
    "Consulting", "Marketing", "Legal", "Hospitality", "Transportation", "Construction", "Energy",
    "Agriculture", "Telecommunications", "Media", "Entertainment", "Non-Profit", "Government"
]

sources = [
    "Website", "LinkedIn", "Referral", "Cold Call", "Email Campaign", "Trade Show", "Webinar",
    "Social Media", "Google Ads", "Facebook Ads", "Content Download", "Partner", "Direct Mail",
    "Telemarketing", "Event", "Online Advertising", "SEO", "PPC", "Affiliate", "Other"
]

statuses = [
    "New", "Contacted", "Qualified", "Proposal", "Negotiation", "Closed Won", "Closed Lost"
]

priorities = ["High", "Medium", "Low"]

def generate_phone_number():
    """Generate a random US phone number"""
    area_codes = ["212", "646", "917", "718", "347", "929", "516", "631", "914", "845", "203", "475", "860", "862", "973", "201", "551", "908", "732", "848", "215", "267", "484", "610", "570", "717", "724", "412", "814", "610"]
    return f"{random.choice(area_codes)}-{random.randint(100, 999)}-{random.randint(1000, 9999)}"

def generate_email(first_name, last_name, company):
    """Generate email based on name and company"""
    domains = ["gmail.com", "yahoo.com", "outlook.com", "hotmail.com", "company.com", "business.com"]
    company_domain = company.lower().replace(" ", "").replace(".", "") + ".com"
    
    email_formats = [
        f"{first_name.lower()}.{last_name.lower()}@{company_domain}",
        f"{first_name[0].lower()}{last_name.lower()}@{company_domain}",
        f"{first_name.lower()}_{last_name.lower()}@{company_domain}",
        f"{first_name.lower()}{last_name.lower()}@{random.choice(domains)}"
    ]
    
    return random.choice(email_formats)

def generate_address():
    """Generate a random US address"""
    streets = [
        "Main St", "Oak Ave", "Elm St", "Maple Ave", "Cedar St", "Pine Ave", "Washington St",
        "Park Ave", "Broadway", "First St", "Second Ave", "Third St", "Fourth Ave", "Fifth St",
        "Market St", "Church St", "State St", "Union Ave", "Franklin St", "Madison Ave"
    ]
    
    cities = [
        "New York", "Los Angeles", "Chicago", "Houston", "Phoenix", "Philadelphia", "San Antonio",
        "San Diego", "Dallas", "San Jose", "Austin", "Jacksonville", "Fort Worth", "Columbus",
        "Charlotte", "San Francisco", "Indianapolis", "Seattle", "Denver", "Washington"
    ]
    
    states = ["NY", "CA", "IL", "TX", "AZ", "PA", "FL", "OH", "NC", "WA", "CO", "DC"]
    
    street_number = random.randint(100, 9999)
    street = random.choice(streets)
    city = random.choice(cities)
    state = random.choice(states)
    zip_code = f"{random.randint(10000, 99999)}"
    
    return f"{street_number} {street}, {city}, {state} {zip_code}"

def generate_random_date(start_date, end_date):
    """Generate a random date between start_date and end_date"""
    time_between_dates = end_date - start_date
    days_between_dates = time_between_dates.days
    random_number_of_days = random.randrange(days_between_dates)
    random_date = start_date + timedelta(days=random_number_of_days)
    return random_date.strftime("%Y-%m-%d")

def create_leads_csv(filename="leads_30000.csv", num_leads=30000):
    """Create a CSV file with sample leads"""
    
    # Define CSV headers
    headers = [
        'first_name', 'last_name', 'email', 'phone', 'mobile', 'company', 'job_title',
        'industry', 'website', 'address', 'city', 'state', 'zip_code', 'country',
        'lead_source', 'lead_status', 'lead_priority', 'annual_revenue', 'employee_count',
        'description', 'notes', 'created_date', 'last_contact_date', 'next_follow_up_date'
    ]
    
    # Date range for created dates
    start_date = datetime(2023, 1, 1)
    end_date = datetime(2024, 12, 31)
    
    with open(filename, 'w', newline='', encoding='utf-8') as csvfile:
        writer = csv.DictWriter(csvfile, fieldnames=headers)
        writer.writeheader()
        
        for i in range(num_leads):
            first_name = random.choice(first_names)
            last_name = random.choice(last_names)
            company = random.choice(companies)
            email = generate_email(first_name, last_name, company)
            phone = generate_phone_number()
            mobile = generate_phone_number()
            
            # Generate address components
            full_address = generate_address()
            address_parts = full_address.split(', ')
            street_address = address_parts[0]
            
            # Parse city, state, zip more safely
            if len(address_parts) >= 2:
                city_state_zip = address_parts[1].split(' ')
                if len(city_state_zip) >= 3:
                    city = ' '.join(city_state_zip[:-2])
                    state = city_state_zip[-2]
                    zip_code = city_state_zip[-1]
                else:
                    # Fallback if parsing fails
                    city = address_parts[1] if len(address_parts) > 1 else "New York"
                    state = random.choice(["NY", "CA", "TX", "FL"])
                    zip_code = f"{random.randint(10000, 99999)}"
            else:
                # Fallback if parsing fails
                city = "New York"
                state = "NY"
                zip_code = f"{random.randint(10000, 99999)}"
            
            # Generate job titles
            job_titles = [
                "CEO", "CTO", "CFO", "COO", "President", "Vice President", "Director", "Manager",
                "Supervisor", "Team Lead", "Senior Developer", "Project Manager", "Business Analyst",
                "Sales Manager", "Marketing Director", "Operations Manager", "HR Manager",
                "Software Engineer", "Product Manager", "Consultant", "Account Executive", "Sales Representative"
            ]
            
            # Generate dates
            created_date = generate_random_date(start_date, end_date)
            last_contact_date = generate_random_date(
                datetime.strptime(created_date, "%Y-%m-%d"),
                end_date
            ) if random.random() > 0.3 else ""
            
            next_follow_up_date = generate_random_date(
                datetime.strptime(last_contact_date, "%Y-%m-%d") if last_contact_date else datetime.strptime(created_date, "%Y-%m-%d"),
                end_date
            ) if random.random() > 0.4 else ""
            
            # Create lead record
            lead = {
                'first_name': first_name,
                'last_name': last_name,
                'email': email,
                'phone': phone,
                'mobile': mobile,
                'company': company,
                'job_title': random.choice(job_titles),
                'industry': random.choice(industries),
                'website': f"https://www.{company.lower().replace(' ', '').replace('.', '')}.com",
                'address': street_address,
                'city': city,
                'state': state,
                'zip_code': zip_code,
                'country': 'USA',
                'lead_source': random.choice(sources),
                'lead_status': random.choice(statuses),
                'lead_priority': random.choice(priorities),
                'annual_revenue': f"${random.randint(100000, 10000000):,}",
                'employee_count': random.choice(['1-10', '11-50', '51-200', '201-500', '501-1000', '1000+']),
                'description': f"Lead interested in {random.choice(['software solutions', 'consulting services', 'product demos', 'partnership opportunities', 'training programs', 'technical support'])}",
                'notes': f"Initial contact made via {random.choice(['phone', 'email', 'website', 'referral'])}. {random.choice(['Interested in our services.', 'Requested more information.', 'Scheduled follow-up call.', 'Sent proposal.', 'Awaiting response.'])}",
                'created_date': created_date,
                'last_contact_date': last_contact_date,
                'next_follow_up_date': next_follow_up_date
            }
            
            writer.writerow(lead)
            
            # Progress indicator
            if (i + 1) % 5000 == 0:
                print(f"Generated {i + 1} leads...")
    
    print(f"Successfully created {num_leads} leads in {filename}")

if __name__ == "__main__":
    create_leads_csv()
