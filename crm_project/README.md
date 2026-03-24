## CRM Django Project

Production-ready cleanup has been applied for safer deployment.

### Tech Stack
- Django
- SQLite (local development)
- Whitenoise for static files in production
- Gunicorn for Linux hosting

### Local Setup
1. Create and activate virtual environment from project root:
   - Windows:
     - `python -m venv .venv`
     - `.venv\Scripts\Activate.ps1`
2. Install dependencies:
   - `pip install -r requirements.txt`
3. Run migrations:
   - `python manage.py migrate`
4. Start server:
   - `python manage.py runserver 127.0.0.1:8000`

### Environment Variables
Create `.env` (do not commit) using values from root `.env.example`:
- `DJANGO_SECRET_KEY`
- `DJANGO_DEBUG`
- `DJANGO_ALLOWED_HOSTS`
- `DJANGO_CSRF_TRUSTED_ORIGINS`
- `DJANGO_SECURE_SSL_REDIRECT`

### Production Notes
- Set `DJANGO_DEBUG=False`.
- Set real domain values in `DJANGO_ALLOWED_HOSTS`.
- Set HTTPS origins in `DJANGO_CSRF_TRUSTED_ORIGINS`.
- Run `python manage.py collectstatic --noinput`.
- Use Gunicorn behind Nginx/Apache on Linux hosting.

### GitHub Push (first time)
From repository root:
- `git init`
- `git add .`
- `git commit -m "Prepare CRM project for production deployment"`
- `git branch -M main`
- `git remote add origin <your-github-repo-url>`
- `git push -u origin main`
