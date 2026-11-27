# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## What this is

Pynab drives Nabaztag (v1) and Nabaztag:tag (v2) rabbits fitted with a TagTagTag card on a Raspberry Pi Zero W (ARMv6, one core, 512 MB) or Zero 2 W. This fork (Wulfaz/pynab) runs it on DietPi / Debian 12 Bookworm with the system Python 3.11, Django 4.2 and PostgreSQL. README.md (French) and CONTRIBUTING.md (English) are the user and contributor docs; `index.md` is a symlink to README.md for GitHub Pages.

## Branches and releases

- `bookworm`: development branch. A push runs the Python 3.11 tests and builds an image (no release).
- `releng`: release branch, fast-forwarded from `bookworm`. A push builds the image and creates a **draft prerelease** tagged `latest`.
- `release`: what published images and community rabbits follow (the web upgrade page warns when a rabbit does not track `origin/release`). Fast-forward it from `bookworm`, then push a tag: `git push fork bookworm:release`, then `git tag vX.Y.Z+wzA.B.C && git push fork <tag>`. A tag builds the image and a full release (NabBlockly from `master` on Erlang/OTP 24+).
- Versions: `v<upstream base>+wz<fork version>`. The upstream base stays `1.0.2` until upstream releases again. `wz1.x.y` = Bookworm fixes and features, `wz2.0.0` = Trixie, `wz3.0.0` = Forky.
- `fl`: f-laurens' branch (Bullseye, Python 3.9), the base of this fork. `nabaztag2018/pynab` is the original upstream.
- Release gotcha: `marvinpinto/action-automatic-releases` cannot find an existing *draft*, so every `releng` push creates a new draft holding only the commits since the previous build. After each build, copy the previous draft's notes (the "Before you start" section and the full changelog) into the new one, delete the old draft only with the maintainer's OK, then set `tag_name=latest` on the new one (`gh api -X PATCH repos/Wulfaz/pynab/releases/<id>`).

## Commands

Lint (CI runs it on `releng`). Use the pinned black from requirements.txt: newer black versions rewrite unrelated lines (e.g. lowercase hex escapes).

```sh
black -l 79 nab*            # black==24.10.0
isort -l 79 --profile black nab*
flake8 nab*                 # .flake8: max 79, ignores E203/E501
mypy nab*                   # django-stubs plugin, see pyproject.toml
```

Full test suite: it needs PostgreSQL (role `pynab` with CREATEDB), the Kaldi libraries and models, and trained snips NLU engines. `.github/workflows/tests-py311.yml` is the reference setup; running it in CI is usually simpler than locally.

```sh
PGPASSWORD=pynab PGHOST=localhost PGPORT=5432 pytest
PGPASSWORD=pynab PGHOST=localhost pytest nabweatherd/tests/nabweatherd_test.py::TestNabWeatherd::test_aliases
```

Tests that do not touch Django or nabd's port (e.g. `nabd/tests/rfid_test.py`) also run with plain `python3 -m unittest nabd.tests.rfid_test`.

**Never run pytest on a rabbit whose services are running.** The test suite's mock nabd listens on nabd's real port (10543). With the real nabd up, `nabd_test.test_shutdown_api_method` sends it a real reboot and most tests fail. On a rabbit, stop everything first (`sudo ./venv/bin/python manage.py stop_all`, then `start_all` afterwards), or test in CI.

On a rabbit, `/opt/pynab` belongs to `dietpi`: run git and upgrades as that user (`cd /opt/pynab && sudo -u dietpi bash upgrade.sh`). Running them as root leaves root-owned files that break the next pull or upgrade.

## Architecture

- **`nabd`** is the only process that touches the hardware: ears, LEDs, sound, button, RFID, microphone. `nabio_hw.py` is used on a Pi Zero and `nabio_virtual.py` everywhere else, so nabd runs on a laptop. It serves a JSON-lines protocol over TCP port 10543, documented (in French) in `PROTOCOL.md`: services send `info`, `message`, `command`, `mode` packets and receive events (`button_event`, `ear_event`, `rfid_event`, `asr_event`, ...).
- **Services** (`nab8balld`, `nabclockd`, `nabweatherd`, `nabradio`, ...) are both a Django app and a daemon:
  - `<name>.py` subclasses `NabService`, `NabRecurrentService` or `NabRandomService` from `nabcommon/nabservice.py`, connects to nabd and implements `process_nabd_packet`.
  - `models.py` holds the configuration as a singleton model, edited from `nabweb`. On save, the web view signals the daemon (SIGUSR1) and the daemon re-reads it (`reload_config`).
  - `<name>.service` is the systemd unit. `install.sh` starts every `*/*.service`.
  - `nlu/intent_{fr,en}.yaml` are the voice intents. At install they are merged into one snips NLU engine per language (`nabd/nlu/`).
  - Other folders: `sounds/`, `locale/` (gettext), `templates/`, and `rfid_data.py` for the data stored on a tag.
  - A new service must also be added to `INSTALLED_APPS` in `nabweb/settings.py`, and to `TAG_APPLICATIONS` in `nabd/rfid.py` if it handles tags.
- **`nabweb`** is the Django configuration site (gunicorn behind nginx). Its views talk to nabd over the same protocol, e.g. RFID tag reading and writing in `nabweb/views.py`.
- **Speech:** Kaldi ASR with grammar-adapted FR/EN models (`asr/`, `nabd/asr.py`), then snips NLU (`nabd/nlu.py`). Both depend on wheels rebuilt for Python 3.11 and armv6l (py-kaldi-asr, snips-nlu-parsers/utils forks on GitHub releases). `requirements.txt` selects them with platform and Python-version markers.
- **Kernel drivers** are built on the rabbit against the running kernel: `wm8960` (sound), `tagtagtag-ears`, `cr14` (v2 RFID reader, from the Wulfaz fork, branch `kernel-6.12`) and `st25r391x` (2022 NFC card). `install.sh` clones, builds and installs them. `upgrade.sh` reboots the rabbit when a driver was rebuilt.

## Install and image scripts

- `install.sh` installs or upgrades pynab on a rabbit: venv, pip, migrations, gettext, NLU training, nginx, drivers, systemd. Its modes are `--upgrade`, `--makerfaire2018`, `ci-chroot` and `ci-chroot-test`.
- `upgrade.sh` runs `git pull`, then `install.sh --upgrade`; the web interface's update button uses it. pip re-downloads the GitHub-hosted wheels on every run, so a bad Wi-Fi link makes it fail half-way with all services stopped. Re-run it, or start the services the way the end of `install.sh` does.
- `setup` builds the release image inside `pguyot/arm-runner-action` (QEMU arm1176, DietPi Bookworm base); see `.github/workflows/arm-runner.yml`.
- The Pi Zero W has a single core: anything timing-sensitive (RFID polling, sound start, ASR) can be delayed by other work in nabd's event loop.
