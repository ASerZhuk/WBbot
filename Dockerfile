FROM python:3.11-slim
WORKDIR /app

# Копируем файл учетных данных (обратите внимание на имя файла)
COPY ./app/paymentbotwb-firebase-adminsdk-fbsvc-db087d202d.json /app/paymentbotwb-firebase-adminsdk.json

# Устанавливаем зависимости
COPY ./app/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Копируем код
COPY ./app/ .

# Запускаем приложение
CMD ["python", "bot.py", "--mode", "polling"]
