FROM nginxproxy/nginx-proxy:1.8.0
# HTTP/2 is off until nginx-proxy ships nginx >= 1.31.9 (nginx2root: CVE-2026-123007, CVE-2026-123633).
# The 1.8.0 template still forces `http2 on;` on its fallback server, which serves h2c on port 80
# without any Host: the sed below removes that line, and the grep fails the build if the template changes.
ENV ENABLE_HTTP2=false
COPY vhost.d/default /etc/nginx/vhost.d/default
# nginx-proxy adds this file to every proxied route.
COPY vhost.d/web_location_additions /etc/nginx/vhost.d/default_location
COPY custom.conf /etc/nginx/conf.d/custom.conf
# Stop sending traffic to an unhealthy web container while another one is healthy (zero-downtime deploys).
# The grep fails the build if an nginx-proxy upgrade breaks this patch.
RUN sed -i '/# Container: {{ $container.Name }}/a {{- if and (eq $container.State.Health.Status "unhealthy") (where $containers "State.Health.Status" "healthy") }}{{- continue }}{{- end }}' /app/nginx.tmpl \
    && grep -c 'eq $container.State.Health.Status "unhealthy"' /app/nginx.tmpl | grep -qx 1 \
    && sed -i '/server_name _; # This is just an invalid value/,/http2 on;/{/^    http2 on;$/d}' /app/nginx.tmpl \
    && grep -c 'http2 on;' /app/nginx.tmpl | grep -qx 1
