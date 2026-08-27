# Deployment Guide

## Render

1. Push the project to a Git repository.
2. Create a new Blueprint on Render and select this repository.
3. Render will read `render.yaml` and create:
   - A Python web service.
   - A PostgreSQL database.
4. Fill the secret variables Render asks for:
   - `DEFAULT_OWNER_PASSWORD`
   - `EMAIL_API_URL`
   - `EMAIL_API_KEY`
   - `EMAIL_FROM`
5. Update `CORS_ORIGINS` in `render.yaml` if the Render service name or custom domain is different from `https://alrwad.onrender.com`.

The service runs:

```bash
alembic upgrade head && python -m uvicorn main:app --host 0.0.0.0 --port $PORT
```

Health check:

```text
/health
```

Expected production health response after Email API is configured:

```json
{
  "database_status": "ok",
  "email_status": "ok",
  "storage_status": "ok",
  "scheduler_status": "ok",
  "server_status": "ok"
}
```

The default `render.yaml` uses Render's free web service plan, so uploads are stored under `/tmp/alrwad_uploads`. This is suitable for testing, but uploaded files are not persistent across restarts or redeploys.

For persistent uploads on Render, switch the web service to a paid plan, add a persistent disk, and set:

```yaml
disk:
  name: alrwad-uploads
  mountPath: /var/data/uploads
  sizeGB: 1
```

Then set `UPLOAD_ROOT=/var/data/uploads`.

## VPS

Install Python 3.11 and PostgreSQL, then set environment variables similar to:

```bash
export ENVIRONMENT=production
export DATABASE_URL=postgresql://USER:PASSWORD@HOST:5432/DB
export JWT_SECRET_KEY='long-random-secret'
export CORS_ORIGINS='https://your-domain.com'
export DEFAULT_OWNER_USERNAME=admin
export DEFAULT_OWNER_EMAIL=admin@your-domain.com
export DEFAULT_OWNER_PASSWORD='strong-owner-password'
export EMAIL_API_URL=https://api.resend.com/emails
export EMAIL_API_KEY='your-api-key'
export EMAIL_FROM='Acme <no-reply@your-domain.com>'
export UPLOAD_ROOT=/var/www/alrwad/uploads
export UPLOAD_URL_PREFIX=/uploads
```

Run:

```bash
python -m pip install -r requirements.txt
alembic upgrade head
python -m uvicorn main:app --host 0.0.0.0 --port 8000
```

For production VPS, run Uvicorn behind Nginx and use a process manager such as systemd or Supervisor.
