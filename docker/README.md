# Docker Compose HTTPS Deployment

This stack keeps the collector private and publishes only Caddy's TLS port. Caddy obtains a Let's Encrypt certificate with DNS-01, so the published port need not be `443`.

## Prerequisites

- Docker with Compose support
- A public DNS name pointing to the host
- A DNS provider API credential allowed to edit that name's zone

## Configure

From `docker/`, copy `.env.example` to `.env` and `authorized_tokens.example.json` to `authorized_tokens.json`. Replace every example value. Both destination files are ignored by Git.

`JSON_COLLECTOR_PORT` selects the collector's internal HTTP port (default `8000`); `TLS_PORT` selects Caddy's published HTTPS port (default `8443`). `DOMAIN` and `ACME_EMAIL` configure the certificate. `CADDY_DNS_MODULE` is the Go module compiled into Caddy, `DNS_PROVIDER` is its Caddy name, and `DNS_API_TOKEN` is its credential. `JSON_COLLECTOR_TOKEN_HEADER` sets the client token header, while `MAX_JSONL_FILE_SIZE` controls rotation in bytes. Mounting `authorized_tokens.json` enables authentication by default.

The default provider is Cloudflare. To swap providers, set both module and provider, then rebuild. For example:

```dotenv
CADDY_DNS_MODULE=github.com/caddy-dns/linode
DNS_PROVIDER=linode
```

Most providers accept an API token as the first `dns` argument. If yours uses multiple or named credentials, adjust only the `tls` block in `Caddyfile` according to that provider's documentation.

The Compose service grants Caddy `NET_BIND_SERVICE`, allowing a non-root process to use TLS ports below `1024`. When running the custom Caddy image directly on a low port, include `--cap-add NET_BIND_SERVICE`; it is unnecessary for ports `1024` and above.

## Run and Test

```sh
docker compose up -d --build
docker compose ps
curl "https://${DOMAIN}:${TLS_PORT}/json-collector/health-check"
curl -H "${JSON_COLLECTOR_TOKEN_HEADER}: YOUR_DEVICE_TOKEN" \
  -H 'Content-Type: application/json' -d '{"temperature":21}' \
  "https://${DOMAIN}:${TLS_PORT}/json-collector/example"
curl -H "${JSON_COLLECTOR_TOKEN_HEADER}: YOUR_DEVICE_TOKEN" \
  "https://${DOMAIN}:${TLS_PORT}/json-collector/example"
```

Collector output and Caddy state use named volumes. To use bind mounts, replace the named-volume sources in `docker-compose.yml` with host paths.

## Certificate Troubleshooting

Check `docker compose logs proxy` for ACME errors. Confirm the domain's authoritative DNS provider matches the compiled module, the API token can edit DNS records, and `_acme-challenge` TXT records can propagate publicly. DNS-01 does not require inbound port 80 or 443, but clients must be able to reach `TLS_PORT`.
