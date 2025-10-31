#!/bin/sh

# Check to see if a data directory is provided. If not, use the current directory.
if [ "$1" != "" ]; then
    DATA_FILE_DIR=$1
else
    DATA_FILE_DIR=$PWD
fi

TOKENS_FILE_PATH=""
if [ "$2" != "" ]; then
    TOKENS_FILE_PATH=$2
fi

max_jsonl_file_bytes="${MAX_JSONL_FILE_SIZE:-"52428800"}"

echo "Saving JSON data files to: ${DATA_FILE_DIR}"

docker build -t json-collector-service:latest .

set -- docker run -d -it
set -- "$@" --name json-collector-service
set -- "$@" --restart unless-stopped
set -- "$@" --mount "type=bind,src=${DATA_FILE_DIR},dst=/run/collector"
set -- "$@" -p 8000:8000
set -- "$@" --env "MAX_JSONL_FILE_SIZE=${max_jsonl_file_bytes}"

if [ "${TOKENS_FILE_PATH}" != "" ]; then
    echo "Binding authorized tokens file from: ${TOKENS_FILE_PATH}"
    set -- "$@" --mount "type=bind,src=${TOKENS_FILE_PATH},dst=/run/collector/authorized_tokens.json,readonly"
    set -- "$@" --env "AUTHORIZED_TOKENS_FILE=/run/collector/authorized_tokens.json"
fi

if [ "${JSON_COLLECTOR_TOKEN_HEADER}" != "" ]; then
    set -- "$@" --env "JSON_COLLECTOR_TOKEN_HEADER=${JSON_COLLECTOR_TOKEN_HEADER}"
fi

set -- "$@" json-collector-service:latest

"$@"
