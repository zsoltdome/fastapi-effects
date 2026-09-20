# Taskiq worker composition

Create the host's production broker, async relay-session maker, and frozen FastAPI Effects
handler executor, then call `register_worker(...)` from `factory.py`. Export the
broker from that module and start it with Taskiq's standard worker CLI. The same
bridge registration must run in sender and worker processes.

The example deliberately does not select Redis, NATS, RabbitMQ, Kafka, or another
broker plugin for the application. That deployment choice belongs to the host and
does not change FastAPI Effects's PostgreSQL handoff and retry authority.
