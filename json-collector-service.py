import asyncio
import json
import os
import shutil
import time

import tornado.httpserver
import tornado.wsgi
from flask import Flask, abort, request, send_from_directory
from werkzeug.exceptions import BadRequest, NotFound

DATA_FILE_DIR = "/run/collector"
DATE_FILE_EXTENSION = "jsonl"
LOG_TIME_FORMAT = "%Y-%m-%d %H:%M:%S"

app = Flask(__name__)


def clean_project_name(project: str) -> str:
    # since project is used a as file name, remove any symbols
    return "".join(filter(str.isalnum, project))


def log_request_event(time_str: str, status_code: int, payload):
    payload_str = "-"
    if payload not in (None, "", {}):
        payload_str = payload if isinstance(payload, str) else json.dumps(payload)
    remote_addr = request.remote_addr or "-"
    print(
        "{0} [{1}] {2} {3} {4} {5}".format(
            remote_addr,
            time_str,
            request.method,
            request.url,
            status_code,
            payload_str,
        )
    )


@app.route("/json-collector/<project>", methods=["GET"])
def return_json_data(project: str):
    cleaned_project = clean_project_name(project)
    event_time_str = time.strftime(LOG_TIME_FORMAT, time.gmtime())
    try:
        response = send_from_directory(
            DATA_FILE_DIR,
            "{0}.{1}".format(cleaned_project, DATE_FILE_EXTENSION),
            as_attachment=False,
        )
    except NotFound:
        abort(404, description="Unknown URL")

    log_request_event(event_time_str, response.status_code, None)
    return response


@app.route("/json-collector/<project>", methods=["POST"])
def ingest_json_data(project: str):
    event_time = time.time()
    event_time_str = time.strftime(LOG_TIME_FORMAT, time.gmtime(event_time))
    cleaned_project = clean_project_name(project)

    try:
        json_data = request.get_json(force=False, silent=False)
    except BadRequest:
        raw_body = (
            request.get_data(as_text=True).replace("\n", "").replace("\t", " ")
        )
        log_request_event(event_time_str, 400, raw_body)
        return "ERROR - improperly formatted JSON data", 400

    if json_data is None:
        json_data = ""

    data_dict = {
        "timestamp": event_time,
        "client_ip": request.remote_addr,
        "request_headers": {},
        "request_url": request.url,
        "posted_data": json_data,
    }
    for key, value in request.headers.items():
        data_dict["request_headers"][key] = value

    max_size_env = os.environ.get("MAX_JSONL_FILE_SIZE")
    max_size = int(max_size_env) if max_size_env else 52428800

    filename = "{0}/{1}.{2}".format(
        DATA_FILE_DIR, cleaned_project, DATE_FILE_EXTENSION
    )
    rotate_file_if_needed(filename, max_size=max_size)

    with open(filename, "a", encoding="utf-8") as file_handle:
        file_handle.write(json.dumps(data_dict) + "\n")

    log_request_event(event_time_str, 200, json_data)
    return "JSON data accepted for {0}".format(project)


@app.route("/json-collector/health-check", methods=["GET"])
def return_health_check():
    log_request_event(time.strftime(LOG_TIME_FORMAT, time.gmtime()), 200, None)
    return "Everything is ay oh kay"


@app.errorhandler(404)
def error404(error):
    log_request_event(time.strftime(LOG_TIME_FORMAT, time.gmtime()), 404, None)
    return "Unknown URL", 404


def rotate_file_if_needed(filename: str, max_size: int):
    if os.path.exists(filename) and os.path.getsize(filename) >= max_size:
        backup_number = 1
        file_base, ext = os.path.splitext(filename)
        while os.path.exists(f"{file_base}.{backup_number}{ext}"):
            backup_number += 1

        shutil.move(filename, f"{file_base}.{backup_number}{ext}")


async def main():
    event = asyncio.Event()
    container = tornado.wsgi.WSGIContainer(app)
    server = tornado.httpserver.HTTPServer(container)
    server.listen(port=8000)
    print("Started Simple JSON Collector Service listening on port 8000")
    await event.wait()


if __name__ == "__main__":
    asyncio.run(main())
