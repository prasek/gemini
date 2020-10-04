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
