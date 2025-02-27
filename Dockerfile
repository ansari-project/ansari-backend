FROM python:3.13

WORKDIR /app/

COPY requirements.txt /app/

RUN pip install --no-cache-dir -r requirements.txt

COPY /src /app/src

ENV PYTHONPATH=/app/src

CMD ["gunicorn", "-w", "4", "-k", "uvicorn.workers.UvicornWorker", "ansari.app.main_api:app"]
