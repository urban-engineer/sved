# Deployment: docker run -it -d -e "HOSTNAME=$(cat /etc/hostname)" --name=sved_worker sved_worker:latest

FROM python:3.9

RUN apt-get update

# Installing Handbrake

# I'm stealing most of this from jlesage's Handbrake image.  Gods bless them for their knowledge.
# https://github.com/jlesage/docker-handbrake

ARG HANDBRAKE_VERSION=1.4.2
ARG X264_VERSION="r3060-5db6aa6"
# Removed a lot of the hardware acceleration from this, for now.
# I'm not interested in hardware acceleration for anything but on-the-fly transcoding.
# But someone will probably come along and request support, at which point I'll look into it
#  (and steal more from jlesage)

ARG HANDBRAKE_URL=https://github.com/HandBrake/HandBrake/releases/download/${HANDBRAKE_VERSION}/HandBrake-${HANDBRAKE_VERSION}-source.tar.bz2
ARG X264_URL=https://artifacts.videolan.org/x264/release-debian-amd64/x264-${X264_VERSION}

# Define working directory.
WORKDIR /tmp

# Dependencies for Handbrake building found at
# https://handbrake.fr/docs/en/latest/developer/install-dependencies-ubuntu.html
RUN apt-get install -y \
        curl \
        autoconf \
        automake \
        autopoint \
        appstream \
        build-essential \
        cmake \
        git \
        libass-dev \
        libbz2-dev \
        libfontconfig1-dev \
        libfreetype6-dev \
        libfribidi-dev \
        libharfbuzz-dev \
        libjansson-dev \
        liblzma-dev \
        libmp3lame-dev \
        libnuma-dev \
        libogg-dev \
        libopus-dev \
        libsamplerate-dev \
        libspeex-dev \
        libtheora-dev \
        libtool \
        libtool-bin \
        libturbojpeg0-dev \
        libvorbis-dev \
        libx264-dev \
        libxml2-dev \
        libvpx-dev \
        m4 \
        make \
        meson \
        nasm \
        ninja-build \
        patch \
        pkg-config \
        python2 \
        tar \
        zlib1g-dev \
        gstreamer1.0-libav \
        intltool \
        libdbus-glib-1-dev \
        libglib2.0-dev \
        libgstreamer1.0-dev \
        libgstreamer-plugins-base1.0-dev \
        libgtk-3-dev \
        libgudev-1.0-dev \
        libnotify-dev \
        libwebkit2gtk-4.0-dev && \
    mkdir HandBrake && \
    curl -# -L ${HANDBRAKE_URL} | tar xj --strip 1 -C HandBrake && cd HandBrake && \
    ./configure --launch-jobs=$(nproc) --launch && \
    make --directory=build install && \
    rm -rf /tmp/* /tmp/.[!.]*

# Installing Python dependencies & copying over worker files
# I debated reworking this to combine the two RUN ops, but I figured this was better.
# Logically, we don't need to recompile Handbrake very often, so we leave at as a base level thing while the below
# operations may change frequently.  Saves time and space.
WORKDIR /code
COPY requirements.txt /code
RUN python3 -m pip install -r requirements.txt
COPY config/ /code/config/
COPY utils/ /code/utils/
COPY sved-worker.py /code/
ENV PYTHONUNBUFFERED=1

ENTRYPOINT ["python3", "sved-worker.py"]
