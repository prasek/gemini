FROM python:3.8.5-slim

RUN apt-get update && \
    apt-get install -y locales && \
    sed -i -e 's/# en_US.UTF-8 UTF-8/en_US.UTF-8 UTF-8/' /etc/locale.gen && \
    dpkg-reconfigure --frontend=noninteractive locales

ENV LANG en_US.UTF-8
ENV LC_ALL en_US.UTF-8

COPY *.py /
COPY requirements.txt /
RUN pip install -r requirements.txt

CMD [ "python", "./main.py" ]
