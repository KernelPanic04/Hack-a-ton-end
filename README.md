# Hack-a-ton

Repository for the Hackathon project.

## Requirements

Install the Python dependencies:

```bash
pip install -r requirements.txt
```

## Run the Backend Locally

### 1. Start the Docker services

```bash
docker compose -f docker/docker-compose.yml up -d
```

### 2. Start the FastAPI backend

```bash
uvicorn main:app --reload
```

The backend will be available at:

```text
http://localhost:8000
```

### 3. Test the Backend

You can access the following endpoint:

```text
http://localhost:8000/users_test
```

## Stop the Backend

First, stop the FastAPI server with:

```text
Ctrl + C
```

Then stop and remove the Docker services:

```bash
docker compose -f docker/docker-compose.yml down -v