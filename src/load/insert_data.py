from pathlib import Path
import sys

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
sys.path.insert(0, str(PROJECT_ROOT))

import psycopg2

from utils.postgres import get_postgres_connection


def insert_data_to_postgres():
    conn = None
    try:
        conn = get_postgres_connection()
        if conn is None:
            return

        with conn.cursor() as cursor:
            cursor.execute("""
                CREATE TEMP TABLE temp_restaurant_data (
                    restaurant_id INT,
                    avg_price NUMERIC
                );
                """)

            with open(DATA_DIR / "temp_clean.csv", "r", encoding="utf-8") as file:
                cursor.copy_expert(
                    """
                    COPY temp_restaurant_data (restaurant_id, avg_price)
                    FROM STDIN
                    WITH CSV HEADER
                    """,
                    file,
                )
            print("Data has been loaded into the temporary table.")

            cursor.execute("""
                UPDATE restaurant
                SET avg_price = temp.avg_price
                FROM temp_restaurant_data temp
                WHERE restaurant.restaurant_id = temp.restaurant_id;
                """)
            print("Existing rows have been updated.")

            conn.commit()
            cursor.execute("DROP TABLE IF EXISTS temp_restaurant_data;")
            print("Data has been inserted successfully.")

    except (psycopg2.Error, OSError, KeyError) as exc:
        print("Unable to insert data into Azure PostgreSQL:")
        print(exc)
    finally:
        if conn:
            conn.close()


if __name__ == "__main__":
    insert_data_to_postgres()
