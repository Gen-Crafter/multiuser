FROM nginx:1.25-alpine
RUN apk add --no-cache openssl
RUN rm /etc/nginx/conf.d/default.conf
COPY nginx.conf /etc/nginx/templates/default.conf.template
COPY docker-entrypoint.d/10-generate-self-signed-cert.sh /docker-entrypoint.d/10-generate-self-signed-cert.sh
RUN chmod +x /docker-entrypoint.d/10-generate-self-signed-cert.sh
EXPOSE 80
CMD ["nginx", "-g", "daemon off;"]
