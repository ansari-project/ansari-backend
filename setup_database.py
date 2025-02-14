import os

import psycopg2

from ansari.ansari_logger import get_logger
from ansari.config import get_settings

# NOTE: This file could only be used (by you, locally) to create missing tables
# in your local database (check `get_settings().DATABASE_URL` for the address)

logger = get_logger()


def import_sql_files(directory, db_url):
    try:
        # Connect to the PostgreSQL database
        conn = psycopg2.connect(db_url)
        # Create a cursor object using the cursor() method
        cursor = conn.cursor()
        # List files in the directory
        files = os.listdir(directory)

        # Sort files by name
        sorted_files = sorted(files)

        # Iterate over each file in the directory
        for filename in sorted_files:
            if filename.endswith(".sql"):
                file_path = os.path.join(directory, filename)
                logger.info(f"Importing: {file_path}")

                # Read the SQL file
                with open(file_path) as f:
                    sql_query = f.read()
                try:
                    # Execute the SQL query
                    cursor.execute(sql_query)
                except psycopg2.Error as error:
                    logger.error(f"Error executing {filename}: {error}")
                    conn.rollback()  # Rollback the transaction in case of error

        # Commit changes to the database
        conn.commit()

        # Close communication with the PostgreSQL database
        cursor.close()

    except (Exception, psycopg2.DatabaseError) as error:
        logger.error(f"Error: {error}")
    finally:
        if conn is not None:
            conn.close()


# Import all sql files under sql directory
sql_directory = "sql"
db_url = str(get_settings().DATABASE_URL)

import_sql_files(sql_directory, db_url)
