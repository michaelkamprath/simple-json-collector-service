#!/bin/sh

# Check to see if a data directory is provided. If not, use the current directory.
if [ "$1" != "" ]; then
    DATA_FILE_DIR=$1
else
    DATA_FILE_DIR=$PWD
fi

max_jsonl_file_bytes="${MAX_JSONL_FILE_SIZE:-"52428800"}"

echo "Saving JSON data files to: ${DATA_FILE_DIR}"

docker build -t json-collector-service:latest .

docker run -d -it \
    --name json-collector-service \
    --restart unless-stopped \
    --mount type=bind,src=$DATA_FILE_DIR,dst=/run/collector \
    -p 8000:8000 \
    --env MAX_JSONL_FILE_SIZE=${max_jsonl_file_bytes} \
    json-collector-service:latest
