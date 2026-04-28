from sqlalchemy import Column, Integer, MetaData, String, TIMESTAMP, Table, Text


# placeholder row written by the SDK bootstrap in database.py
BOOTSTRAP_SESSION_ID = "__bootstrap__"

# minimal projection of the SDK-managed session storage tables
metadata = MetaData()

agent_sessions = Table(
    "agent_sessions",
    metadata,
    Column("session_id", String, primary_key=True),
    Column("created_at", TIMESTAMP(timezone=False), nullable=False),
    Column("updated_at", TIMESTAMP(timezone=False), nullable=False),
)

agent_messages = Table(
    "agent_messages",
    metadata,
    Column("id", Integer, primary_key=True),
    Column("session_id", String, nullable=False),
    Column("message_data", Text, nullable=False),
    Column("created_at", TIMESTAMP(timezone=False), nullable=False),
)
