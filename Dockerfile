FROM python:3.10-slim

WORKDIR /app

COPY . .

RUN pip install -e .

EXPOSE 8765

CMD ["python", "-m", "zhiku", "serve", "--host", "0.0.0.0"]
