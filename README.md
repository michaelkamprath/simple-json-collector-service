# Simple JSON Collector Service
This is a dead simple web service to be used with a IOT or similar such devices that send telemetry data formatted as JSON, but can be used with anything that POSTs JSON payloads. This service was original designed to work with [The Things Network (TTN)](https://www.thethingsnetwork.org) to recieve telemetry from TTN applications via a [HTTP integration](https://www.thethingsnetwork.org/docs/applications/http/). This service has been packaged as a Docker container, making it easy to build and deploy anywhere.

## Launching Web Service
To launch the webservice, use the included shell script:
```
./json-collector-service-docker.sh /path/to/data/directory
```
Replacing `/path/to/data/directory` with the path to the directory where you want data to be stored. If no data directory is provided, the launch script will use the current `PWD`. This script will build the Docker image and then launch the container. Note that port 8000 will be used by this service, and that the container is launched in detached, interactive mode.

Alternatively, you can manually build the Docker file, then launch the container with something like:
```
docker run -d  \
     --mount type=bind,src=$DATA_FILE_DIR,dst=/run/collector \
    -p $SERVICE_PORT:8000 \
    json-collector-service:latest
```
Where `DATA_FILE_DIR` is the directory in which to save data and `SERVICE_PORT` is the port the web service should listen on.

## TTN Integration
Set up in TTN by adding a [HTTP Integration](https://www.thethingsnetwork.org/docs/applications/http/) to your application. The URL should be:
```
http://your_ip_address:8000/json-collector/dataset_name
```
Where  `your_ip_address` is the IP address where your docker container is running, and `dataset_name` is a unique name you want to give to the data from this application. The HTTP Method should be `POST`.

## Getting Saved Data
The data is saved in the JSON Lines format (one JSON payload per line) with the file name of `dataset_name.jsonl`, where `dataset_name` is the data set name you used in the POST URL. As a result, you can use the `dataset_name` to organize the data you post to this service. The data can be found in the data directory you configured, or you can fetch it from the service using a HTTP GET request at the same URL you posted telemetry data to for the data set.

# Issues and TODOs
* Currently this service has no security.
* Add log rotation so individual log files do not grow "too large".
