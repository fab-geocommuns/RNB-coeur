FROM nginxproxy/nginx-proxy:1.8.0
COPY vhost.d/default /etc/nginx/vhost.d/default
COPY custom.conf /etc/nginx/conf.d/custom.conf
# Deploys drain the old web by making it unhealthy: drop an unhealthy container from its upstream
# as long as another container of that upstream is healthy (an unhealthy container keeps serving otherwise).
# The grep fails the build if a new nginx-proxy version moves the anchor line.
RUN sed -i '/# Container: {{ $container.Name }}/a {{- if and (eq $container.State.Health.Status "unhealthy") (where $containers "State.Health.Status" "healthy") }}{{- continue }}{{- end }}' /app/nginx.tmpl \
    && grep -c 'eq $container.State.Health.Status "unhealthy"' /app/nginx.tmpl | grep -qx 1
