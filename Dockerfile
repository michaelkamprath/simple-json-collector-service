FROM python:3-alpine
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
#   This docker is listening on port 8000. Be sure to map that port.
#

EXPOSE 8000
RUN apk --no-cache add curl
RUN pip install bottle
RUN mkdir -p /run/collector
COPY json-collector-service.py /json-collector-service.py

HEALTHCHECK CMD curl --fail http://localhost:8000/json-collector/health-check || exit 1
CMD ["python", "/json-collector-service.py"]