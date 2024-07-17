# Deployment: docker run -it -d -e "HOSTNAME=$(cat /etc/hostname)" --name=sved_worker sved_worker:latest

FROM python:3.9-alpine

# Define working directory.
WORKDIR /tmp

# Install ffmpeg, mkvtoolnix, and mediainfo
RUN wget -O /tmp/ffmpeg-release-amd64-static.tar.xz "https://johnvansickle.com/ffmpeg/releases/ffmpeg-release-amd64-static.tar.xz" && \
    tar xvf /tmp/ffmpeg-release-amd64-static.tar.xz && \
    mv /tmp/ffmpeg-*-amd64-static/ff* /usr/local/bin/ && \
    rm /tmp/ffmpeg-release-amd64-static.tar.xz && \
    apk add mkvtoolnix mediainfo && \
    mv /usr/bin/mediainfo /usr/bin/mediainfocli

# Installing Python dependencies & copying over worker files
# I debated reworking this to combine the two RUN ops, but I figured this was better.
# Logically, we don't need to recompile Handbrake very often, so we leave at as a base level thing while the below
# operations may change frequently.  Saves time and space.
WORKDIR /code
COPY requirements.txt /code
RUN python3 -m pip install --upgrade pip && python3 -m pip install -r requirements.txt
COPY config/ /code/config/
COPY utils/ /code/utils/
COPY sved-worker.py /code/
ENV PYTHONUNBUFFERED=1

ENTRYPOINT ["python3", "sved-worker.py"]
