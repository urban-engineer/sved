FROM python:3.9

ENV PYTHONUNBUFFERED=1

WORKDIR /code

COPY requirements.txt /code

RUN python3 -m pip install -r requirements.txt

COPY . /code/

RUN rm -f /code/.idea /code/venv /code/testing /code/.gitignore /code/sved-worker.py /code/*.dockerfile /code/db.sqlite3

RUN pwd && cd /code && python3 manage.py migrate

ENTRYPOINT ["python3", "manage.py", "runserver", "0:8080"]
