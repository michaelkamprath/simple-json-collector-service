import json
import time
from bottle import Bottle, route, get, post, run, request, static_file, response

try:
    from cheroot.wsgi import Server as WSGIServer
except ImportError:
    from cherrypy.wsgiserver import CherryPyWSGIServer as WSGIServer

DATA_FILE_DIR = '/run/collector'
DATE_FILE_EXTENSION = 'jsonl'
LOG_TIME_FORMAT = '%Y-%m-%d %H:%M:%S'

app = Bottle()

def clean_project_name(project):
    # since project is used a a file name, remove any symbols 
    return "".join(filter(str.isalnum, project))

def logRequestEvent(time_str, json_data):
    print('{0} [{1}] {2} {3} {4} {5}'.format(
            request.environ.get('HTTP_X_FORWARDED_FOR') or request.environ.get('REMOTE_ADDR'),
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
        'client_ip': request.environ.get('HTTP_X_FORWARDED_FOR') or request.environ.get('REMOTE_ADDR'),
        'request_headers':{}, 
        'request_url': request.url,
        'posted_data': json_data
    }
    for k in request.headers.keys():
        data_dict['request_headers'][k] = request.get_header(k, '')
    
    filename = '{0}/{1}.{2}'.format(DATA_FILE_DIR, cleaned_project, DATE_FILE_EXTENSION)
    with open(filename, 'a') as f:
        f.write(json.dumps(data_dict)+'\n')
        
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

if __name__ == "__main__":
    server = WSGIServer(
        ('0.0.0.0', 8000),
        app,
        server_name='simple-json-collector',
        numthreads=8,
        timeout=90,
    )

    try:
        print("Simple JSON Collector Service starting:\thttp://0.0.0.0:8000/")
        server.start()
    except KeyboardInterrupt:
        print("Halting Simple JSON Collector Service")
        server.stop()
