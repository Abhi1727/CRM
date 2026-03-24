# CRM Project

A Django-based CRM application for managing users, leads, assignments, and follow-up workflows.

## Features
- User authentication and role-based access
- Lead creation, assignment, and status tracking
- Team/dashboard views for operations
- Internal reminders and notification workflows

## Tech Stack
- Python
- Django
- SQLite (default local database)
- Whitenoise (static files in production)
- Gunicorn (app server for Linux deployment)

## Project Structure
- `crm_project/` - main Django project source
- `crm_project/manage.py` - Django management entry point
- `.env.example` - sample environment variables

## Local Setup (Windows PowerShell)
```powershell
cd "C:\Users\parih\OneDrive\Desktop\Projects\CRM"
python -m venv .venv
.\.venv\Scripts\Activate.ps1
cd crm_project
pip install -r requirements.txt
python manage.py migrate
python manage.py runserver 127.0.0.1:8000
```

Open: `http://127.0.0.1:8000/`

## Environment Variables
Copy values from `.env.example` and configure:
- `DJANGO_SECRET_KEY`
- `DJANGO_DEBUG`
- `DJANGO_ALLOWED_HOSTS`
- `DJANGO_CSRF_TRUSTED_ORIGINS`
- `DJANGO_SECURE_SSL_REDIRECT`

## Production Basics
- Set `DJANGO_DEBUG=False`
- Configure your real domain in allowed hosts and CSRF trusted origins
- Run:
  - `python manage.py migrate`
  - `python manage.py collectstatic --noinput`
- Serve with Gunicorn behind Nginx/Apache
