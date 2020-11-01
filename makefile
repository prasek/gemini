.PHONY: default
default: clean deps run

.PHONY: deps
deps: venv
	venv/bin/pip3 install -r requirements.txt

.PHONY: run
run:
	source venv/bin/activate && \
	python3 main.py

.PHONY: clean
clean:
	rm -rf venv

.PHONY: venv
venv:
	virtualenv venv
	venv/bin/python -m pip install --upgrade pip

.PHONY: docker-build
docker-build:
	docker build -t gemini .

.PHONY: docker-push
docker-push:
	docker tag gemini prasek/gemini:latest
	docker push prasek/gemini:latest

.PHONY: docker-run
docker-run:
	docker run -it gemini

.PHONY: docker-debug
docker-debug:
	docker run -it gemini /bin/sh

.PHONY: docker-rmi
docker-rmi:
	docker rmi gemini -f

.PHONY: docker-rmi-all
docker-rmi-all:
	docker rmi -f $$(docker images -a -q)

.PHONY: docker-kill-all
docker-kill-all:
	docker kill $$(docker ps -q)

.PHONY: docker-rm-all
docker-rm-all:
	docker rm $$(docker ps -a -q)
