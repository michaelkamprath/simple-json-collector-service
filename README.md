# Simple JSON Collector Service
This is a dead simple web service to be used with a IOT or similar such devices that send telemetry data formatted as JSON, but can be used with anything that POSTs JSON payloads. This service was original designed to work with [The Things Network (TTN)](https://www.thethingsnetwork.org) to recieve telemetry from TTN applications via a [HTTP integration](https://www.thethingsnetwork.org/docs/applications/http/). This service has been packaged as a Docker container, making it easy to build and deploy anywhere.

## Launching Web Service
To launch the webservice, use the included shell script:
```
./json-collector-service-docker.sh /path/to/data/directory [/path/to/tokens.json]
```
Replacing `/path/to/data/directory` with the path to the directory where you want data to be stored. If no data directory is provided, the launch script will use the current `PWD`. Provide the optional second argument to bind an authorized tokens file into the container and enable token authentication. This script will build the Docker image and then launch the container. Note that port 8000 will be used by this service, and that the container is launched in detached, interactive mode.

Alternatively, you can manually build the Docker file, then launch the container with something like:
```
docker run -d  \
     --mount type=bind,src=$DATA_FILE_DIR,dst=/run/collector \
    -p $SERVICE_PORT:8000 \
    json-collector-service:latest
```
Where `DATA_FILE_DIR` is the directory in which to save data and `SERVICE_PORT` is the port the web service should listen on.

The environment variable `MAX_JSONL_FILE_SIZE` (integer value in bytes) can be used to set the max data file size used when determining when to rotate the data file. It defaults to 50 MB. 

## Securing Ingestion
By default the collector accepts POST requests from any client. Provide a bearer-token manifest to restrict ingestion to trusted devices.

1. Create a JSON file that maps usernames to shared tokens, for example:
    ```json
    {
      "weather-station-a": "token-abc123",
      "warehouse-pi": "token-def456"
    }
    ```
2. Bind-mount that file into the container at `/run/collector/authorized_tokens.json` or set the `AUTHORIZED_TOKENS_FILE` environment variable to an alternate path and mount accordingly.
3. Instruct clients to send the header `X-JSON-Collector-Token: <their token>` on every POST and project data `GET`. Override the header name by setting `JSON_COLLECTOR_TOKEN_HEADER` before launching the container.

When token authentication is enabled, the service rejects missing headers with a `401` that names the required header, rejects unknown tokens with `403`, logs the associated username as `authenticated_user` in the JSONL output, and redacts the token header from stored request headers and stdout logs.

> While the default bind target lives alongside collected data under `/run/collector`, the HTTP GET endpoint only serves files matching `<project>.jsonl`. The credentials manifest remains inaccessible over HTTP, though operators should still treat the bound file as sensitive on the host filesystem.

> Dataset downloads require the same header when authentication is enabled; the `/json-collector/health-check` endpoint remains publicly accessible for monitoring.

The health check returns `500` with diagnostic text when the collector cannot access its data directory, making it easier to spot setup mistakes during deployment.

## TTN Integration
Set up in TTN by adding a [HTTP Integration](https://www.thethingsnetwork.org/docs/applications/http/) to your application. The URL should be:
```
http://your_ip_address:8000/json-collector/dataset_name
```
Where  `your_ip_address` is the IP address where your docker container is running, and `dataset_name` is a unique name you want to give to the data from this application. The HTTP Method should be `POST`.

## Getting Saved Data
The data is saved in the JSON Lines format (one JSON payload per line) with the file name of `dataset_name.jsonl`, where `dataset_name` is the data set name you used in the POST URL. As a result, you can use the `dataset_name` to organize the data you post to this service. The data can be found in the data directory you configured, or you can fetch it from the service using a HTTP GET request at the same URL you posted telemetry data to for the data set.
