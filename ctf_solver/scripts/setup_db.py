#!/usr/bin/env python3
"""
Database setup script for flaggy
"""
import os
import sys
import click
from pathlib import Path

from ctf_solver.database.db import get_db_connection


@click.command()
@click.option('--drop', is_flag=True, help='Drop existing tables first')
@click.option('--seed', is_flag=True, help='Add sample data')
def main(drop: bool, seed: bool):
    """Setup the flaggy database schema"""
    try:
        # Find schema file
        schema_path = Path(__file__).parent.parent / 'database' / 'schema.sql'
        if not schema_path.exists():
            click.echo(f"Schema file not found: {schema_path}", err=True)
            sys.exit(1)
            
        # Read schema
        schema_sql = schema_path.read_text()
        
        # Connect to database
        conn = get_db_connection()
        conn.autocommit = True
        cursor = conn.cursor()
        
        if drop:
            click.echo("Dropping existing tables...")
            drop_sql = """
                DROP TABLE IF EXISTS steps CASCADE;
                DROP TABLE IF EXISTS attempts CASCADE;
                DROP TABLE IF EXISTS challenges CASCADE;
            """
            cursor.execute(drop_sql)
            click.echo("Tables dropped.")
        
        click.echo("Creating database schema...")
        cursor.execute(schema_sql)
        click.echo("Database schema created successfully.")
        
        if seed:
            click.echo("Skipping seed data - use 'flaggy sync-challenges' to add actual challenges from filesystem")
            click.echo("This ensures only challenges that actually exist get added to the database.")
        
        cursor.close()
        conn.close()
        click.echo("Database setup complete!")
        
    except Exception as e:
        click.echo(f"Error setting up database: {e}", err=True)
        sys.exit(1)


if __name__ == '__main__':
    main()


