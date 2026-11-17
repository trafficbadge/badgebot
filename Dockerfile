# badgebot on Railway: web server for the email links + the WSDOT watcher, in one process.
# Microsoft's Playwright image already has Chromium and every library it needs, so the build
# never runs the browser installer (that step broke on Nov 17 with exit code 127).
# Keep the image tag and the playwright version in requirements.txt the same.
FROM mcr.microsoft.com/playwright/python:v1.63.0-noble
ENV PYTHONUNBUFFERED=1 BADGEBOT_DATA=/data
WORKDIR /app
COPY requirements.txt .
RUN python3 -m pip install --no-cache-dir -r requirements.txt
COPY . .
CMD ["python3", "-m", "badgebot", "serve", "--with-watch"]
