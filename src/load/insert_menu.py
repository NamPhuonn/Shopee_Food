import csv
from pathlib import Path
import sys

import psycopg2

PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / "data"
sys.path.insert(0, str(PROJECT_ROOT))

from utils.postgres import get_postgres_connection

csv_file_path = DATA_DIR / "menu_data.csv"


def split_csv_file(input_file_path, num_splits=5):
    input_file_path = Path(input_file_path)
    split_files = []

    try:
        with open(input_file_path, "r", encoding="utf-8") as file:
            reader = csv.reader(file)
            header = next(reader)

            rows = list(reader)
            total_rows = len(rows)
            rows_per_file = total_rows // num_splits + (total_rows % num_splits > 0)

            for i in range(num_splits):
                split_file_path = input_file_path.with_name(
                    f"{input_file_path.stem}_part_{i+1}{input_file_path.suffix}"
                )
                with open(
                    split_file_path, "w", newline="", encoding="utf-8"
                ) as split_file:
                    writer = csv.writer(split_file)
                    writer.writerow(header)
                    writer.writerows(rows[i * rows_per_file : (i + 1) * rows_per_file])

                split_files.append(split_file_path)

        print("CSV file split successfully:", split_files)
    except (FileNotFoundError, csv.Error, OSError) as exc:
        print("Unable to split the CSV file:")
        print(exc)

    return split_files


def load_data_to_postgres(csv_files):
    conn = None
    try:
        conn = get_postgres_connection()
        if conn is None:
            return

        for csv_file_path in csv_files:
            with conn.cursor() as cursor:
                cursor.execute("""
                    CREATE TEMP TABLE temp_menu (
                        restaurant_id INT,
                        menu TEXT
                    );
                    """)

                with open(csv_file_path, "r", encoding="utf-8") as file:
                    next(file)
                    cursor.copy_expert("COPY temp_menu FROM STDIN WITH CSV", file)
                print(
                    f"Data from {csv_file_path} has been loaded into the temporary table."
                )

                cursor.execute("""
                    UPDATE menu
                    SET end_date = CURRENT_TIMESTAMP, is_current = FALSE
                    WHERE is_current = TRUE
                    AND EXISTS (
                        SELECT 1
                        FROM temp_menu
                        WHERE temp_menu.restaurant_id = menu.restaurant_id
                        AND temp_menu.menu IS NOT NULL
                        AND temp_menu.menu <> menu.menu
                    );
                    """)
                print("Existing rows have been updated.")

                cursor.execute("""
                    INSERT INTO menu (restaurant_id, menu, start_date, is_current)
                    SELECT restaurant_id, menu, CURRENT_TIMESTAMP, TRUE
                    FROM temp_menu
                    WHERE restaurant_id NOT IN (
                        SELECT restaurant_id FROM menu WHERE is_current = TRUE
                    );
                    """)
                conn.commit()
                print(
                    f"New data from {csv_file_path} has been inserted into the target table."
                )

                cursor.execute("DROP TABLE IF EXISTS temp_menu;")

    except (psycopg2.Error, OSError) as exc:
        print("Unable to insert data into Azure PostgreSQL:")
        print(exc)
    finally:
        if conn:
            conn.close()


split_files = split_csv_file(csv_file_path, num_splits=10)
load_data_to_postgres(split_files)
