FROM python:3.11-slim
WORKDIR /app

# התקנת תלויות
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# העתקת הקוד
COPY app.py .

EXPOSE 8090
# ברירת מחדל להרצה
CMD ["python", "app.py"]
