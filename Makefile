SHELL := powershell.exe

.PHONY: install install-node install-python dev-api dev-gateway dev-desktop test build

install:
	npm.cmd install
	py -3.11 -m pip install -r services/local-api/requirements.txt
	py -3.11 -m pip install -r services/demo-gateway/requirements.txt

install-node:
	npm.cmd install

install-python:
	py -3.11 -m pip install -r services/local-api/requirements.txt
	py -3.11 -m pip install -r services/demo-gateway/requirements.txt

dev-api:
	py -3.11 -m uvicorn app.main:app --app-dir services/local-api --reload --host 127.0.0.1 --port 8765

dev-gateway:
	py -3.11 -m uvicorn app.main:app --app-dir services/demo-gateway --reload --host 127.0.0.1 --port 8788

dev-desktop:
	npm.cmd run dev --workspace @genie/desktop

test:
	npm.cmd test

build:
	npm.cmd run build
