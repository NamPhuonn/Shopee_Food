import csv
import psycopg2
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]
DATA_DIR = PROJECT_ROOT / 'data'
csv_file_path = DATA_DIR / 'menu_data.csv'

def split_csv_file(input_file_path, num_splits=5):
    input_file_path = Path(input_file_path)
    split_files = []
    try:
        with open(input_file_path, 'r') as file:
            reader = csv.reader(file)
            header = next(reader)  # Read the header row.

            rows = list(reader)
            total_rows = len(rows)
            rows_per_file = total_rows // num_splits + (total_rows % num_splits > 0)
            
            for i in range(num_splits):
                split_file_path = input_file_path.with_name(f"{input_file_path.stem}_part_{i+1}{input_file_path.suffix}")
                with open(split_file_path, 'w', newline='') as split_file:
                    writer = csv.writer(split_file)
                    writer.writerow(header)  # Write the header to each split file.
                    writer.writerows(rows[i * rows_per_file: (i + 1) * rows_per_file])
                
                split_files.append(split_file_path)
        
        print("CSV file split successfully:", split_files)
    except (FileNotFoundError, csv.Error, OSError) as e:
        print("Unable to split the CSV file:")
        print(e)
    return split_files

def connect_to_azure_postgres(host, database, user, password, port=5432):
    try:
        conn = psycopg2.connect(
            host=host,
            database=database,
            user=user,
            password=password,
            port=port
        )
        print("Successfully connected to Azure PostgreSQL!")
        return conn
    except psycopg2.Error as e:
        print("Unable to connect to Azure PostgreSQL:")
        print(e)
        return None

def load_data_to_postgres(csv_files):
    try:
        # Connect to PostgreSQL.
        host = "shopee.postgres.database.azure.com"
        database = "delivery_info"
        user = "Numpy"
        password = "********"
        conn = connect_to_azure_postgres(host, database, user, password)

        for csv_file_path in csv_files:
            with conn.cursor() as cursor:
                # Create a temporary table to hold the CSV data.
                cursor.execute("""
                    CREATE TEMP TABLE temp_menu (
                        restaurant_id INT,
                        menu TEXT
                    );
                """)

                # Use COPY to load the CSV into the temporary table.
                with open(csv_file_path, 'r') as file:
                    next(file)  # Skip the header row.
                    cursor.copy_expert("COPY temp_menu FROM STDIN WITH CSV", file)
                print(f"Data from {csv_file_path} has been loaded into the temporary table.")

                # Update and insert data from the temporary table into the target table.
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

                # Insert new or changed rows from the temporary table into the target table.
                cursor.execute("""
                    INSERT INTO menu (restaurant_id, menu, start_date, is_current)
                    SELECT restaurant_id, menu, CURRENT_TIMESTAMP, TRUE
                    FROM temp_menu
                    WHERE restaurant_id NOT IN (
                        SELECT restaurant_id FROM menu WHERE is_current = TRUE
                    );
                """)
                conn.commit()
                print(f"New data from {csv_file_path} has been inserted into the target table.")

                # Drop the temporary table after processing.
                cursor.execute("DROP TABLE IF EXISTS temp_menu;")

    except (psycopg2.Error, OSError) as e:
            print("Unable to insert data into Azure PostgreSQL:")
        print(e)
    finally:
        if conn:
            conn.close()

# Split the CSV into parts and load each part.
split_files = split_csv_file(csv_file_path, num_splits=10)
load_data_to_postgres(split_files)
