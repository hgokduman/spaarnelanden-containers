FROM python:3.11-slim

RUN mkdir /app
COPY . /app
WORKDIR /app
EXPOSE 5000

RUN pip install -r requirements.txt

CMD [ "python3", "app.py" ]
