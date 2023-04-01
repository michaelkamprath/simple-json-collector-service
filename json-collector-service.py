import json
import os
import shutil
from logging.handlers import RotatingFileHandler
import time
import asyncio
from bottle import Bottle, route, get, post, run, request, static_file, response

import tornado.wsgi
import tornado.httpserver
import tornado.ioloop

DATA_FILE_DIR = '/run/collector'
DATE_FILE_EXTENSION = 'jsonl'
LOG_TIME_FORMAT = '%Y-%m-%d %H:%M:%S'

app = Bottle()

def clean_project_name(project):
    # since project is used a a file name, remove any symbols
    return "".join(filter(str.isalnum, project))

def logRequestEvent(time_str, json_data):
    print('{0} [{1}] {2} {3} {4} {5}'.format(
            request.remote_addr,
            time_str,
            request.method,
            request.url,
            response.status,
            '-' if json_data is None else json_data
        ))

@app.get('/json-collector/<project>')
def return_json_data(project):
    cleaned_project = clean_project_name(project)
    logRequestEvent(time.strftime(LOG_TIME_FORMAT), None)
    return static_file('{0}.{1}'.format(cleaned_project, DATE_FILE_EXTENSION), root=DATA_FILE_DIR)

@app.post('/json-collector/<project>')
def ingest_json_data(project):
    event_time = time.time()
    event_time_str = time.strftime(LOG_TIME_FORMAT, time.gmtime(event_time))
    cleaned_project = clean_project_name(project)
    try:
        json_data = request.json
    except json.decoder.JSONDecodeError:
        response.status = 400
        logRequestEvent(
            event_time_str,
            request.body.getvalue().decode("utf-8").replace('\n','').replace('\t',' ')
        )
        return "ERROR - improperly formatted JSON data"
    if json_data is None:
        json_data = ''
    data_dict = {
        'timestamp': event_time,
        'client_ip': request.remote_addr,
        'request_headers':{},
        'request_url': request.url,
        'posted_data': json_data
    }
    for k in request.headers.keys():
        data_dict['request_headers'][k] = request.get_header(k, '')

    max_size_env = os.environ.get('MAX_JSONL_FILE_SIZE')
    max_size = int(max_size_env) if max_size_env else 52428800  # Set a default value if the environment variable is not set

    filename = '{0}/{1}.{2}'.format(DATA_FILE_DIR, cleaned_project, DATE_FILE_EXTENSION)
    rotate_file_if_needed(filename, max_size=max_size)

    with open(filename, 'a') as f:
        f.write(json.dumps(data_dict) + '\n')

    logRequestEvent(event_time_str, json_data)
    return 'JSON data accepted for {0}'.format(project)

@app.get('/json-collector/health-check')
def return_health_check():
    logRequestEvent(time.strftime(LOG_TIME_FORMAT), None)
    return 'Everything is ay oh kay'

@app.error(404)
def error404(error):
    logRequestEvent(time.strftime(LOG_TIME_FORMAT), None)
    return 'Unknown URL'

def rotate_file_if_needed(filename, max_size):
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
    print('Started Simple JSON Collector Service listening on port 8000')
    await event.wait()

if __name__ == "__main__":
    asyncio.run(main())
