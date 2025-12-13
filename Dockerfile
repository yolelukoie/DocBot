FROM python:3.12-slim

WORKDIR /app

COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Кладёшь сюда свой шаблон документа:
#   template.pdf  (можешь переименовать, но тогда поменяй TEMPLATE_PATH)
COPY main.py template.pdf . 

ENV PORT=8080

CMD ["python", "main.py"]

