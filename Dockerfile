FROM python:3.12-slim
WORKDIR /app
COPY requirements.txt .
COPY ./src/app .
RUN pip install -r requirements.txt
EXPOSE 5000
CMD ["python", "app/run.py"]