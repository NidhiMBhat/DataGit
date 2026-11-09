from dagit.db.connection import get_db_cursor

if __name__ == "__main__":
    with get_db_cursor() as cursor:
        cursor.execute("SELECT version();")
        print("Database Version:", cursor.fetchone())