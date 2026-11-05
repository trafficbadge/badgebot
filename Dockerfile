# badgebot on Railway: web server for the email links + the WSDOT watcher, in one process.
FROM python:3.13-slim
ENV PYTHONUNBUFFERED=1 BADGEBOT_DATA=/data
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt \
 && python -m playwright install --with-deps chromium
COPY . .
CMD ["python", "-m", "badgebot", "serve", "--with-watch"]
