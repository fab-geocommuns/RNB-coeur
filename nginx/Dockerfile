FROM nginxproxy/nginx-proxy:1.8.0
COPY vhost.d/default /etc/nginx/vhost.d/default
# nginx-proxy adds this file to every proxied route.
COPY vhost.d/web_location_additions /etc/nginx/vhost.d/default_location
COPY custom.conf /etc/nginx/conf.d/custom.conf
# Stop sending traffic to an unhealthy web container while another one is healthy (zero-downtime deploys).
# The grep fails the build if an nginx-proxy upgrade breaks this patch.
RUN sed -i '/# Container: {{ $container.Name }}/a {{- if and (eq $container.State.Health.Status "unhealthy") (where $containers "State.Health.Status" "healthy") }}{{- continue }}{{- end }}' /app/nginx.tmpl \
    && grep -c 'eq $container.State.Health.Status "unhealthy"' /app/nginx.tmpl | grep -qx 1
