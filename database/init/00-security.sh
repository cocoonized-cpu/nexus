#!/bin/bash
# Security configuration script for PostgreSQL
# This runs as part of the Docker entrypoint initialization

# This script modifies pg_hba.conf to restrict connections to only the nexus user
# This must run AFTER PostgreSQL data is initialized

# Only run if pg_hba.conf exists (means database is initialized)
if [ -f "/var/lib/postgresql/data/pg_hba.conf" ]; then
    echo "Securing pg_hba.conf..."

    # Backup original
    cp /var/lib/postgresql/data/pg_hba.conf /var/lib/postgresql/data/pg_hba.conf.bak

    # Create restricted pg_hba.conf
    cat > /var/lib/postgresql/data/pg_hba.conf << 'PGHBA'
# PostgreSQL Client Authentication Configuration
# Secured for NEXUS - only allows nexus user

# Local connections (Unix sockets)
local   all             nexus                                   trust

# IPv4 local loopback
host    all             nexus           127.0.0.1/32            scram-sha-256

# Docker network (172.16.0.0/12 covers 172.16-31.x.x)
host    all             nexus           172.16.0.0/12           scram-sha-256

# Reject everything else
host    all             all             0.0.0.0/0               reject
hostssl all             all             0.0.0.0/0               reject
PGHBA

    echo "pg_hba.conf secured successfully"
fi
