FROM alpine:3.22
RUN apk add --no-cache icecast mailcap
COPY run-icecast.sh /run-icecast.sh
USER icecast
# The app writes /config/icecast.xml (Admin → Radio → Apply); the wrapper restarts
# Icecast when that file changes.
CMD ["/bin/sh", "/run-icecast.sh"]
