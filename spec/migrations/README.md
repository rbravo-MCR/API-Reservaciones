# Run this script against your MySQL database before enabling USE_IN_MEMORY=false

mysql -u<user> -p<pass> -h<host> -P<port> <dbname> < spec/migrations/20260115_outbox_events.sql
