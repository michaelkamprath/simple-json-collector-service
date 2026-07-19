# TrueNAS SCALE Deployment

This example deploys the collector as a TrueNAS Custom App behind Caddy. The collector remains private on the Compose network; only the chosen HTTPS port is published.

The collector is pulled from `ghcr.io/michaelkamprath/simple-json-collector-service:latest`; no registry login is required.

## Publish a DNS-Enabled Caddy Image

TrueNAS Custom Apps cannot build images. Build Caddy elsewhere with the module for your DNS provider, then publish it to a public registry. Replace the module, provider suffix, username, and platform as needed:

```sh
docker login ghcr.io -u YOUR_GITHUB_USER
docker buildx build --platform linux/amd64 \
  -f docker/Dockerfile.caddy \
  --build-arg CADDY_DNS_MODULE=github.com/caddy-dns/YOUR_PROVIDER \
  -t ghcr.io/YOUR_GITHUB_USER/simple-json-collector-caddy-YOUR_PROVIDER:latest \
  --push docker
```

Use the provider's documented module path; not every provider is under `github.com/caddy-dns`. If it requires multiple or named credentials, update `docker/Caddyfile` and `caddy.env` accordingly. Replace the proxy image in `docs/docker-compose.truenas.yml` with the resulting pullable image.

## Prepare Storage and Secrets

Replace `YOUR_POOL` with an existing TrueNAS pool name, then create the host paths and set ownership for the containers' non-root UID:

```sh
mkdir -p /mnt/YOUR_POOL/apps/json-collector/{data,caddy/data,caddy/config,secrets}
chown -R 10001:10001 /mnt/YOUR_POOL/apps/json-collector/data /mnt/YOUR_POOL/apps/json-collector/caddy
```

Create `secrets/authorized_tokens.json` under that directory:

```json
{
  "example-device": "replace-with-a-long-random-token"
}
```

```sh
chown root:10001 /mnt/YOUR_POOL/apps/json-collector/secrets/authorized_tokens.json
chmod 640 /mnt/YOUR_POOL/apps/json-collector/secrets/authorized_tokens.json
```

Create `secrets/caddy.env` with the environment variables required by the selected DNS provider. The supplied Caddyfile expects:

```dotenv
ACME_EMAIL=admin@example.com
DNS_API_TOKEN=replace-with-dns-api-token
```

Set `caddy.env` to mode `600`. Do not commit either secrets file.

## Customize and Install

Edit `docs/docker-compose.truenas.yml` before pasting it into TrueNAS:

1. Replace `YOUR_POOL`, `YOUR_GITHUB_USER`, and `YOUR_PROVIDER`.
2. Replace `collector.example.com` with the public collector hostname.
3. Set `DNS_PROVIDER` to the Caddy provider name.
4. Choose the TLS port. The example uses `8443`; update the environment value, port mapping, and proxy healthcheck together if changing it.

In TrueNAS, open **Apps → Discover Apps → Custom App → Install via YAML**. Set a name, paste the customized YAML, and select **Save**. TrueNAS performs only basic YAML validation, so inspect both container logs and confirm both health checks pass.

## DNS, Port Forwarding, and Firewall

Create a public DNS `A` record pointing the hostname to the router's public IPv4 address. If serving over IPv6, also create an `AAAA` record pointing to the TrueNAS host's public IPv6 address.

For IPv4, forward the chosen external TCP port on the router to the same published port at the TrueNAS host's LAN address. Permit that TCP port through any router and TrueNAS firewalls. For IPv6, port forwarding is normally unnecessary; permit inbound TCP directly to the host instead. Do not publish or forward the collector's internal HTTP port.

DNS-01 certificate issuance does not require inbound ports `80` or `443`. Clients must include the port in the URL unless the published port is `443`. If an `AAAA` record exists but IPv6 traffic is blocked, clients may fail even when IPv4 works. Carrier-grade NAT may prevent inbound IPv4 forwarding entirely.

Test from outside the local network:

```sh
curl https://collector.example.com:8443/json-collector/health-check
curl -H 'X-JSON-Collector-Token: YOUR_DEVICE_TOKEN' \
  -H 'Content-Type: application/json' -d '{"temperature":21}' \
  https://collector.example.com:8443/json-collector/example
curl -H 'X-JSON-Collector-Token: YOUR_DEVICE_TOKEN' \
  https://collector.example.com:8443/json-collector/example
```

For certificate failures, inspect the proxy logs, confirm the DNS credential can edit the zone, and check public `_acme-challenge` TXT propagation. For connection failures, test IPv4 and IPv6 separately and verify the public port reaches the TrueNAS host.
