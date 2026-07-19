# Using the Published Container Image

The collector is published through GitHub Container Registry (GHCR) as:

- `ghcr.io/michaelkamprath/simple-json-collector-service:latest`
- `ghcr.io/michaelkamprath/simple-json-collector-service:<full-commit-sha>`

`latest` follows the most recent successful `main` build. A commit SHA tag identifies an exact build and is preferable for repeatable production deployments.

## Pull the Image

The image is public, so no registry login is required:

```sh
docker pull ghcr.io/michaelkamprath/simple-json-collector-service:latest
docker image inspect ghcr.io/michaelkamprath/simple-json-collector-service:latest
```

See the repository README for runtime configuration and direct `docker run` instructions.
