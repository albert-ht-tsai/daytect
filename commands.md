# Docker + alembic
docker compose exec app bash
alembic init alembic
alembic revision --autogenerate -m "init"
alembic upgrade head
alembic stamp head
