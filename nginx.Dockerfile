FROM nginx:1.25-alpine

COPY nginx.conf /etc/nginx/nginx.conf.template

COPY cards/images /var/www/images

CMD ["/bin/sh", "-c", "\
  : \"${AUTH_URL:=http://auth:5000}\"; \
  : \"${PLAYERS_URL:=http://players:5000}\"; \
  : \"${MATCHMAKING_URL:=http://matchmaking:5000}\"; \
  : \"${CATALOGUE_URL:=http://catalogue:5000}\"; \
  : \"${GAME_ENGINE_URL:=http://game-engine:5000}\"; \
  envsubst '${AUTH_URL} ${PLAYERS_URL} ${MATCHMAKING_URL} ${CATALOGUE_URL} ${GAME_ENGINE_URL}' < /etc/nginx/nginx.conf.template > /etc/nginx/nginx.conf && \
  exec nginx -g 'daemon off;'"]
