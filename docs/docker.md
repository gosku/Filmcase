# Running Filmcase in Docker

Runs the **full** stack: PostgreSQL, RabbitMQ, the web server and a Celery worker. Full
mode rather than lite, because compose supplies the two services that make a manual full
install awkward, so the parallel import path costs nothing extra to set up here.

The web server is served over **HTTPS** with a self-signed certificate generated on first
run. That is not decoration: browsers only expose USB, and several other capabilities, to a
secure context, and plain HTTP to a LAN address never qualifies. See
[HTTPS and the certificate warning](#https-and-the-certificate-warning).

---

## Quick start

```bash
./setup.sh docker
```

It checks that Docker and Compose v2 are present, asks a handful of questions with sensible
defaults detected from the machine, writes `.env` and `docker-compose.override.yml`, and
offers to build and start. Then open `https://<FILMCASE_HOST>:8443/` and accept the
certificate warning once.

Unlike the other two modes the script installs nothing on the host, so it runs anywhere
with bash and Docker, not only on macOS and Ubuntu.

Re-running it is safe and is the intended way to change an answer: existing values become
the prompt defaults, configured photo directories are kept, and the generated signing key
and database password are preserved rather than regenerated. Regenerating the database
password would lock the app out of an existing PostgreSQL volume.

Both files are gitignored. `.env.example` and `docker-compose.override.yml.example` are
tracked as a reference if you would rather write them by hand.

---

## Configuration

Compose reads `.env` from the same directory. `.env.example` is the template.

| Variable                      | Default              | Purpose                                                                                                                                 |
| ----------------------------- | -------------------- | --------------------------------------------------------------------------------------------------------------------------------------- |
| `FILMCASE_HOST`               | `localhost`          | Address you type in the browser. Goes into the certificate SAN and the trusted CSRF origin.                                             |
| `FILMCASE_HTTPS_PORT`         | `8443`               | Published port.                                                                                                                         |
| `PUID` / `PGID`               | `1000` / `1000`      | Account that owns the volumes and runs the app.                                                                                         |
| `FILMCASE_WEB_WORKERS`        | `2`                  | gunicorn processes.                                                                                                                     |
| `FILMCASE_WEB_THREADS`        | `4`                  | Threads per gunicorn process. Simultaneous requests is workers times threads.                                                           |
| `FILMCASE_WORKER_CONCURRENCY` | `8`                  | Photos processed at once. This is Celery's `--concurrency`, the pool inside one worker, not a count of workers. Each process loads Django and Pillow, so keep it near the core count on a server running other things. |
| `FILMCASE_SECRET_KEY`         | insecure dev default | Django signing key. Generate one before exposing the app.                                                                               |
| `FILMCASE_DB_PASSWORD`        | `fujifilm_recipes`   | PostgreSQL password, reachable only inside the compose network. Changing it after first start locks the app out of the existing volume. |

`FILMCASE_HOST` must match what you actually type. It is written into the certificate as a
`subjectAltName` and reused to derive `CSRF_TRUSTED_ORIGINS`, so reaching the app on any
other address gives a certificate mismatch and fails every POST. Set
`CSRF_TRUSTED_ORIGINS` explicitly if the install needs to answer on several names.

---

## Mounting your photo directories

Photo directories live in `docker-compose.override.yml`, which compose reads automatically
and which is gitignored so your paths stay out of the repository. Copy the tracked
`.example` file and edit it:

```yaml
services:
  web:
    volumes:
      - /srv/photos:/srv/photos:ro
  celery_worker:
    volumes:
      - /srv/photos:/srv/photos:ro
```

Mount each directory at **the same path it has on the host**. Filmcase stores the absolute
path of each library folder in the database, so mounting at the identical path means the
value you type on the Library page is the path the container sees, stored paths stay valid,
and moving between a Docker and a native install does not strand your library. Read-only is
deliberate: Filmcase never writes to the originals.

Both services need the same mounts. The worker does the importing, so a directory the web
service can see but the worker cannot would fail at sync time rather than when you add it.

Named volumes do not need repeating in the override: compose merges volumes by target path
rather than replacing the list. That merge is also why `docker-compose.yml` lists no photo
directory of its own, since an override can add a mount but never remove one.

---

## HTTPS and the certificate warning

On first start the entrypoint generates a self-signed certificate for `FILMCASE_HOST` and
hands it to gunicorn. Your browser will show a full-page warning the first time, along the
lines of "Your connection is not private". Accept it once per browser and the app works
normally afterwards.

**Why not plain HTTP?** Browsers gate powerful APIs behind a _secure context_, and the
check is on the origin's scheme, not on whether the certificate chains to a trusted
authority. So:

| Origin                                                     | Secure context                   | Powerful APIs |
| ---------------------------------------------------------- | -------------------------------- | ------------- |
| `http://localhost:8443`                                    | yes                              | available     |
| `https://192.168.1.10:8443` with a self-signed certificate | yes, after accepting the warning | available     |
| `http://192.168.1.10:8443`                                 | no                               | unavailable   |

A self-signed certificate is therefore enough. Private IP addresses are never treated as
trustworthy on their own, and that has not changed despite a
[long-standing proposal](https://github.com/w3c/webappsec-secure-contexts/issues/60) to make
it so.

**To get rid of the warning entirely** you need a certificate that chains to something the
browser already trusts, which means a real hostname:

- Put a reverse proxy in front of the container and give it a certificate for a real
  hostname. Most NAS platforms include a reverse proxy and a free dynamic-DNS hostname with
  a managed certificate, which needs nothing installed on any client.
- Or serve it through a mesh VPN that issues real certificates for its own hostnames.

Both are optional. The self-signed default works without owning a domain or installing
anything on the machines you browse from.

**Regenerating the certificate**, after changing `FILMCASE_HOST`:

```bash
docker compose down
docker volume rm filmcase_certs
docker compose up -d
```

---

## Camera access

Pushing a recipe to a camera reads the camera over USB from **the machine running the
server**. In a container that has consequences worth being explicit about:

- **On a remote server: pushing recipes does not work yet.** The camera is on your desk and
  the server is elsewhere, and no amount of configuration bridges that. Moving the transport
  into the browser over WebUSB would remove the restriction entirely, since the browser runs
  on the machine the camera is plugged into. That work is under way.
- **On a desktop: it can work**, if you pass the USB bus through to the container. Add to
  the `web` service:

  ```yaml
  devices:
    - /dev/bus/usb:/dev/bus/usb
  ```

  and see [camera_usb_access.md](camera_usb_access.md) for the udev rules the host still
  needs.

The image ships `libusb` for that second case. It is unused on a remote server.

### Checking what your browser can do

`https://<FILMCASE_HOST>:8443/camera/diagnostics/` reports whether the page is a secure
context, whether the browser exposes WebUSB, and whether it can select, open and claim the
camera. Useful for confirming the certificate is doing its job, and for testing whether a
browser-side transport is viable on your setup.

WebUSB is Chromium-only. Firefox and Safari do not implement it.

---

## Security

**Filmcase has no authentication.** Every page, including the Library page that browses the
filesystem, is available to anyone who can reach the port. TLS encrypts the connection, it
does not restrict who connects.

That is fine on a laptop bound to localhost. Publishing it on a network where you do not
trust everyone is a different proposition, and you should put it behind your NAS's reverse
proxy with authentication, or on a private network such as a VPN, rather than exposing
the port directly. Never forward this port from the internet.

---

## Running on a NAS or headless server

- `PUID` / `PGID` must be the account that owns your photo directories, not necessarily
  `1000`. Appliance operating systems often assign different ids to the first user account.
  Run `id <your-user>` on the host to find them; `./setup.sh docker` fills in the id of
  whoever runs it.
- If the machine already runs a reverse proxy, point it at the container and let it present
  a trusted certificate, keeping the self-signed one for the hop between them.
- Pick a `FILMCASE_HTTPS_PORT` that nothing else is using. `./setup.sh docker` warns if the
  port it is about to publish is already listening.
- Keep the process counts modest. A server that is already running other services will not
  enjoy a Celery worker per core, and each worker process loads Django and Pillow.

---

## Updating

```bash
make docker-update
```

That pulls, rebuilds and restarts. `make update` is for the other two install modes and
will refuse to run here: it drives a virtualenv that a Docker install does not have.

The equivalent by hand is two commands:

```bash
git pull origin main
docker compose up -d --build
```

Neither step needs anything installed on the host. The rebuild picks up new dependencies
from `requirements.txt`, and the entrypoint applies migrations as the web container starts.

**What happens to the running app.** The image is built first, while the current containers
keep serving. Only once the build succeeds does compose replace them, so a failed build
costs nothing and leaves the running stack exactly as it was. Downtime is the few seconds of
recreating the containers, plus however long any new migration takes.

Only `web` and `celery_worker` are replaced, since they are the two built from this
repository. `db` and `rabbitmq` are untouched, and no data volume is affected by an update.

**Do not update while a library sync is running.** Celery acknowledges a task when the
worker receives it rather than when it finishes, so replacing the worker mid-import drops
whatever it was holding, which can be several hundred images once prefetching is taken into
account. Nothing is corrupted or deleted: those files simply were never imported, so the
next sync finds them missing from the catalog and picks them up. Run one afterwards if you
are unsure. The Library page shows whether a sync is active.

---

## Operating it

```bash
docker compose logs -f web          # follow the web server
docker compose exec web python manage.py sync_library
docker compose down                 # stop, keeping all volumes
docker compose up -d --build        # rebuild after pulling changes
```

Migrations run automatically on every start of the `web` service.
