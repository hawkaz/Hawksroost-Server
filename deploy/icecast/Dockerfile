FROM alpine:3.22
RUN apk add --no-cache icecast
USER icecast
# The app writes /config/icecast.xml (Settings → Radio → Apply).
CMD ["/bin/sh", "-c", "until [ -s /config/icecast.xml ]; do echo 'Waiting for icecast.xml'; sleep 15; done; exec icecast -c /config/icecast.xml"]
