FROM postgis/postgis:14-master

RUN mkdir -p /tmp/buffers

# Create group and user

RUN adduser --system --group app

# Set user rights to allow the on-root-postgres-user
# to access the temp folder

RUN chown -R app:app /tmp/buffers
RUN chmod 770 /tmp/buffers

# Change to non-root privilege

USER app