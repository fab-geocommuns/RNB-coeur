
# Create required .env.*.dev files from .env.*.example files if missing"
env-local:
	test -f .env.app.dev || cp .env.app.example .env.app.dev
	test -f .env.db_auth.dev || cp .env.db_auth.example .env.db_auth.dev
	test -f .env.nginx-encrypt.dev || cp .env.nginx-encrypt.example .env.nginx-encrypt.dev
	test -f .env.rnb.dev || cp .env.rnb.example .env.rnb.dev
	test -f .env.s3_backup.dev || cp .env.s3_backup.example .env.s3_backup.dev
	test -f .env.sentry.dev || cp .env.sentry.example .env.sentry.dev
	test -f .env.worker.dev || cp .env.worker.example .env.worker.dev
	test -f .env.metabase.dev || cp .env.metabase.example .env.metabase.dev
	test -f .env.rabbitmq.dev || cp .env.rabbitmq.example .env.rabbitmq.dev
