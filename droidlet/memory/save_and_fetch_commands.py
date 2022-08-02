"""
Copyright (c) Facebook, Inc. and its affiliates.
"""
import sqlite3
import json


def create_connection(db_file):
    """create a database connection to the SQLite database
        specified by the db_file
    :param db_file: database file
    :return: Connection object or None
    """
    return sqlite3.connect(db_file, check_same_thread=False)


def create_table(conn, create_table_sql):
    """create a table from the create_table_sql statement
    :param conn: Connection object
    :param create_table_sql: a CREATE TABLE statement
    :return:
    """
    c = conn.cursor()
    c.execute(create_table_sql)


def create_all_tables(conn):
    if conn is not None:
        create_table_commands = """CREATE TABLE IF NOT EXISTS commands (
        cmd_id INTEGER PRIMARY KEY,
        action_dict TEXT,
        chat_message TEXT,
        block_assembly TEXT,
        username TEXT
        );"""

        # create commands table
        create_table(conn, create_table_commands)

        create_table_tags = """CREATE TABLE IF NOT EXISTS tags (
        tag_id INTEGER PRIMARY KEY,
        tag TEXT
        );"""

        # create tags table
        create_table(conn, create_table_tags)

        create_table_bridge = """CREATE TABLE IF NOT EXISTS command_tag_bridge (
        tag_id INTEGER,
        cmd_id INTEGER,
        FOREIGN KEY(tag_id) REFERENCES tags(tag_id),
        FOREIGN KEY(cmd_id) REFERENCES commands(cmd_id)
        );"""

        # create bridge table
        create_table(conn, create_table_bridge)

        create_table_errors = """CREATE TABLE IF NOT EXISTS error_annotation_info (
        error_type TEXT,
        chat TEXT,
        action_dict TEXT,
        feedback TEXT
        );"""

        # create error annotation table
        create_table(conn, create_table_errors)

        create_table_survey_results = """CREATE TABLE IF NOT EXISTS survey_results (
        results TEXT
        );"""

        # create survey table
        create_table(conn, create_table_survey_results)

        crate_table_object_annotations = """CREATE TABLE IF NOT EXISTS object_annotations (
        object_name TEXT,
        object_tags TEXT,
        object_points TEXT
        );"""

        # create object annotations table
        create_table(conn, crate_table_object_annotations)
    else:
        print("Error! cannot create the database connection.")


def dict_factory(cursor, row):
    return {col[0]: row[idx] for idx, col in enumerate(cursor.description)}


def removeDuplicateCommands(rows):
    seen_ids = {}
    final_rows = []
    for row in rows:
        if row["cmd_id"] not in seen_ids:
            seen_ids[row["cmd_id"]] = True
            final_rows.append(row)
    return final_rows


def onlyFetchCommands(conn, query):
    conn.row_factory = dict_factory
    cur = conn.cursor()
    if query == "":
        cur.execute(
            """SELECT c.cmd_id,
            c.chat_message,
            c.username,
            c.block_assembly,
            c.action_dict
            FROM commands c"""
        )
        rows = cur.fetchall()
        return removeDuplicateCommands(rows)

    queries = query.split(" ")
    all_rows = []

    for q in queries:
        cur.execute(
            """SELECT c.cmd_id,
            c.chat_message,
            c.username,
            c.block_assembly,
            c.action_dict
            FROM commands c
            LEFT JOIN command_tag_bridge b ON c.cmd_id = b.cmd_id
            LEFT JOIN tags t ON b.tag_id = t.tag_id
            WHERE t.tag = ? OR c.chat_message LIKE ?""",
            (q, f"%{q}%"),
        )

        rows = cur.fetchall()
        all_rows.extend(rows)
    return removeDuplicateCommands(all_rows)


def saveAndFetchCommands(conn, postData):
    # get the data first
    conn.row_factory = dict_factory
    action_dict = postData["action_dict"] if "action_dict" in postData else ""
    chat_message = postData["chat_message"]
    username = postData["username"]
    block_assembly = (
        postData["block_assembly"] if "block_assembly" in postData else None
    )

    tags_list = postData["tags_list"] if "tags_list" in postData else []
    cur = conn.cursor()
    cur.execute(
        "select * from commands where chat_message=? and block_assembly=?",
        (chat_message, block_assembly),
    )
    rows = cur.fetchall()
    if rows:
        return "DUPLICATE"

    command_id = None
    cur.execute(
        """INSERT INTO commands(action_dict, chat_message, block_assembly, username) VALUES (?,?,?,?)""",
        (action_dict, chat_message, block_assembly, username),
    )
    command_id = cur.lastrowid
    for tag in tags_list:
        cur.execute("SELECT * FROM tags WHERE tag=?", (tag,))
        rows = cur.fetchall()
        if not rows:
            cur.execute("INSERT INTO tags(tag) VALUES (?)", (tag,))
            cur.execute(
                "INSERT INTO command_tag_bridge(tag_id, cmd_id) VALUES (?,?)",
                (cur.lastrowid, command_id),
            )
        else:
            for row in rows:
                cur.execute(
                    "INSERT INTO command_tag_bridge(tag_id, cmd_id) VALUES (?,?)",
                    (row["tag_id"], command_id),
                )

    cur.execute("SELECT cmd_id, chat_message, username, block_assembly, action_dict FROM commands")
    rows = cur.fetchall()

    return rows


def saveAnnotatedErrorToDb(conn, postData):
    # fetch relevant
    action_dict = json.dumps(postData["action_dict"])
    err_type = "PARSING_ERROR" if "parsing_error" in postData else "NOT_IDENTIFIED"
    msg = postData["msg"]
    feedback = postData["feedback"]
    # var adtt = postData['adtt_text']

    # save to database
    cur = conn.cursor()

    cur.execute(
        """INSERT INTO error_annotation_info (error_type, chat, action_dict, feedback) VALUES (?,?,?,?)""",
        (err_type, msg, action_dict, feedback),
    )
    print("successfully saved annotation info")


def saveSurveyResultsToDb(conn, postData):
    # save to database
    cur = conn.cursor()

    cur.execute("""INSERT INTO survey_results (results) VALUES (?)""", (json.dumps(postData),))
    print("successfully saved survey results")


def saveObjectAnnotationsToDb(conn, postData):
    cur = conn.cursor()

    for key, val in postData["nameMap"].items():
        object_name = val
        object_property_map = postData["propertyMap"][key]
        object_point_map = postData["pointMap"][key]
        cur.execute(
            """INSERT INTO object_annotations (object_name, object_tags, object_points) VALUES (?, ?, ?)""",
            (
                object_name,
                json.dumps(object_property_map),
                json.dumps(object_point_map),
            ),
        )
    print("successfully saved annotation info")
