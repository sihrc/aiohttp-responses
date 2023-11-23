FROM python:3.10.6 as builder

ENV PATH="/root/.local/bin:${PATH}"

RUN curl -sSL https://install.python-poetry.org | python3 - && \
    poetry self update --preview && \
    poetry config virtualenvs.in-project true


COPY pyproject.toml poetry.lock /venv/

WORKDIR /venv/

RUN poetry install

FROM python:3.10.6

LABEL version="0.1.0"
LABEL author="Chris Lee"
LABEL email="chris@indico.io"
LABEL description="Mocking AIOHTTP Requests"

ENV PYTHONPATH=/aiohttp_responses PATH=/venv/.venv/bin:/aiohttp_responses/bin:/aiohttp_responses/scripts:${PATH}
COPY --from=builder /venv /venv

RUN apt update

WORKDIR /aiohttp_responses
COPY . /aiohttp_responses


ENTRYPOINT [ "bash" ]
