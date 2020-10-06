import json
import time
from bottle import route, get, post, run, request, static_file

DATA_FILE_DIR = '/run/collector'
DATE_FILE_EXTENSION = 'jsonl'

def clean_project_name(project):
    # since project is used a a file name, remove any symbols 
    return "".join(filter(str.isalnum, project))
         
@get('/json-collector/<project>')
def return_json_data(project):
    cleaned_project = clean_project_name(project)
    print('Downloading JSON data file for \'{0}\''.format(cleaned_project))
    return static_file('{0}.{1}'.format(cleaned_project, DATE_FILE_EXTENSION), root=DATA_FILE_DIR)
        

@post('/json-collector/<project>')
def ingest_json_data(project):
    cleaned_project = clean_project_name(project)
    json_data = request.json
    if json_data is None:
        json_data = ''
    data_dict = {
        'timestamp': time.time(),
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
    print('Received JSON data for \'{0}\': {1}'.format(cleaned_project, data_dict))
    return 'JSON data accepted for {0}\n'.format(cleaned_project)


run(host='0.0.0.0', port=8000, debug=True)