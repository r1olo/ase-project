FROM nginx:1.25-alpine

COPY src/api_gateway/nginx.conf /etc/nginx/nginx.conf.template

COPY cards/images /var/www/images

CMD ["/bin/sh", "-c", "\
  : \"${AUTH_URL:=https://auth:5000}\"; \
  : \"${PLAYERS_URL:=https://players:5000}\"; \
  : \"${MATCHMAKING_URL:=https://matchmaking:5000}\"; \
  : \"${CATALOGUE_URL:=https://catalogue:5000}\"; \
  : \"${GAME_ENGINE_URL:=https://game-engine:5000}\"; \
  envsubst '${AUTH_URL} ${PLAYERS_URL} ${MATCHMAKING_URL} ${CATALOGUE_URL} ${GAME_ENGINE_URL}' < /etc/nginx/nginx.conf.template > /etc/nginx/nginx.conf && \
  exec nginx -g 'daemon off;'"]
