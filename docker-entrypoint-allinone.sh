#!/bin/bash
set -e

echo "=== ChambeApp All-in-One Starting ==="

PG_VERSION=$(ls /usr/lib/postgresql/ | head -1)
POSTGRES_DATA_DIR="/var/lib/postgresql/$PG_VERSION/main"
POSTGRES_USER="chambeapp"
POSTGRES_PASSWORD="chambeapp_dev"
POSTGRES_DB="chambeapp"

echo "PostgreSQL version: $PG_VERSION"
echo "Data directory: $POSTGRES_DATA_DIR"

# Remove any existing cluster and reinitialize
if [ -d "$POSTGRES_DATA_DIR" ]; then
    echo "Removing existing PostgreSQL data directory..."
    rm -rf "$POSTGRES_DATA_DIR"
fi

echo "Initializing PostgreSQL database..."
su -s /bin/bash postgres -c "/usr/lib/postgresql/$PG_VERSION/bin/initdb -D $POSTGRES_DATA_DIR --auth-local=trust --auth-host=md5"

echo "Configuring PostgreSQL..."
sed -i "s/#listen_addresses = 'localhost'/listen_addresses = '*'/" "$POSTGRES_DATA_DIR/postgresql.conf"
sed -i "s/#port = 5432/port = 5432/" "$POSTGRES_DATA_DIR/postgresql.conf"
echo "host all all 0.0.0.0/0 md5" >> "$POSTGRES_DATA_DIR/pg_hba.conf"

# Create log directory with proper permissions
mkdir -p /var/log/postgresql
chown postgres:postgres /var/log/postgresql

echo "Starting PostgreSQL temporarily for setup..."
su -s /bin/bash postgres -c "/usr/lib/postgresql/$PG_VERSION/bin/pg_ctl -D $POSTGRES_DATA_DIR -l /var/log/postgresql/postgresql.log start"

sleep 3

echo "Creating database and user..."
su -s /bin/bash postgres -c "psql -c \"CREATE USER $POSTGRES_USER WITH PASSWORD '$POSTGRES_PASSWORD';\" || true"
su -s /bin/bash postgres -c "psql -c \"CREATE DATABASE $POSTGRES_DB OWNER $POSTGRES_USER;\" || true"
su -s /bin/bash postgres -c "psql -c \"GRANT ALL PRIVILEGES ON DATABASE $POSTGRES_DB TO $POSTGRES_USER;\" || true"
su -s /bin/bash postgres -c "psql -d $POSTGRES_DB -c \"CREATE EXTENSION IF NOT EXISTS postgis;\" || true"

su -s /bin/bash postgres -c "/usr/lib/postgresql/$PG_VERSION/bin/pg_ctl -D $POSTGRES_DATA_DIR stop -m fast"
sleep 2

echo "=== Starting services via supervisord ==="
exec "$@"