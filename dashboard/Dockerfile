FROM python:3.12-slim
ENV PYTHONUNBUFFERED=1
WORKDIR /srv
COPY requirements-dashboard.txt .
RUN pip install --no-cache-dir -r requirements-dashboard.txt
COPY dashboard/app.py .
COPY dashboard/.streamlit .streamlit
COPY data/muestras muestras
RUN useradd --uid 1000 docuvali
USER docuvali
EXPOSE 8501
CMD ["streamlit", "run", "app.py", "--server.port=8501", "--server.address=0.0.0.0", "--server.baseUrlPath=/dashboard", "--browser.gatherUsageStats=false"]
