FROM python:3.13-alpine
LABEL org.label-schema.schema-version="1.0"
LABEL org.label-schema.name="Simple JSON Data Collector Service"
LABEL org.label-schema.description="A simple web service for gathering JSON-formatted data. Allows data to be grouped into projects."
LABEL org.label-schema.usage="https://github.com/michaelkamprath/simple-json-collector-service/blob/main/README.md"
LABEL org.label-schema.vcs-url="https://github.com/michaelkamprath/simple-json-collector-service/"
LABEL maintainer="Michael Kamprath <https://github.com/michaelkamprath>"

#
#   To run this docker, the following bind is expected
#       dst=/run/collector - This directory will contain the JSON data files
#
#   This docker listens on JSON_COLLECTOR_PORT (8000 by default).
#

COPY requires.txt /requires.txt
RUN pip install --no-cache-dir -r /requires.txt
RUN addgroup -S -g 10001 collector && adduser -S -D -H -u 10001 -G collector collector \
    && mkdir -p /run/collector \
    && chown collector:collector /run/collector
COPY json-collector-service.py /json-collector-service.py
COPY token_auth.py /token_auth.py

USER collector
HEALTHCHECK CMD python -c "import os, urllib.request; urllib.request.urlopen('http://127.0.0.1:' + (os.environ.get('JSON_COLLECTOR_PORT') or '8000') + '/json-collector/health-check')"
CMD ["python", "/json-collector-service.py"]
