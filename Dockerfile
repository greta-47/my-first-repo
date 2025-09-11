FROM python:3.12-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

COPY . .
ENV PYTHONUNBUFFERED=1

# Render will inject $PORT; we set the command in the dashboard
# (or you could uncomment the next line to bake it in)
# CMD ["uvicorn", "api.main:app", "--host", "0.0.0.0", "--port", "8000"]
