### Base stage
FROM python:3.9-slim AS base-stage

ENV FLASK_APP=app.py

RUN adduser --disabled-password --home /app --shell /bin/bash app
USER app
WORKDIR /app

COPY docker/entrypoint*.sh /
COPY requirements.txt ./

RUN echo "export PATH=${PATH}:/app/.local/bin" >> .bashrc

ENTRYPOINT ["/entrypoint.sh"]

### Development stage
FROM base-stage AS development-stage

ARG APP_ENV

ENV APP_ENV=${APP_ENV}
ARG PIPENV_USERNAME
ARG PIPENV_PASSWORD
COPY docker/pip.conf /etc

RUN pip install -r requirements.txt

### Build stage
FROM base-stage AS build-stage

COPY . ./

ARG PIPENV_USERNAME
ARG PIPENV_PASSWORD
COPY docker/pip.conf /etc

RUN pip install -r requirements.txt

### Production stage
FROM build-stage AS production-stage

ENV GUNICORN_CMD_ARGS="--workers=3"

USER app
