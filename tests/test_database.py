from sqlalchemy import text

from database import get_schema_metadata


def test_schema_metadata_includes_keys_and_relationships(sqlite_engine):
    with sqlite_engine.begin() as connection:
        connection.execute(
            text("CREATE TABLE departments (id INTEGER PRIMARY KEY, name TEXT)")
        )
        connection.execute(
            text(
                "CREATE TABLE employees ("
                "id INTEGER PRIMARY KEY, "
                "department_id INTEGER REFERENCES departments(id)"
                ")"
            )
        )

    schema = get_schema_metadata(sqlite_engine)
    employees = next(table for table in schema if table["name"] == "employees")
    columns = {column["name"]: column for column in employees["columns"]}

    assert employees["schema"] == ""
    assert columns["id"]["flags"] == ["PK"]
    assert columns["department_id"]["flags"] == ["FK"]
    assert employees["foreign_keys"][0]["referred_table"] == "departments"
