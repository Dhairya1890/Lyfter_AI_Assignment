"""
Database operations (CRUD) for messages.
"""
import sqlite3
from datetime import datetime, timezone
from typing import Optional, List, Dict, Any, Tuple
from .models import get_connection


class MessageStorage:
    """Handles all database operations for messages."""
    
    @staticmethod
    def insert_message(
        message_id: str,
        from_msisdn: str,
        to_msisdn: str,
        ts: str,
        text: Optional[str] = None
    ) -> Tuple[bool, bool]:
        """
        Insert a message into the database.
        
        Returns:
            Tuple of (success, is_duplicate)
            - (True, False): New message inserted successfully
            - (True, True): Message already exists (duplicate)
            - (False, False): Error occurred
        """
        conn = get_connection()
        try:
            cursor = conn.cursor()
            created_at = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%f")[:-3] + "Z"
            
            cursor.execute(
                """
                INSERT INTO messages (message_id, from_msisdn, to_msisdn, ts, text, created_at)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (message_id, from_msisdn, to_msisdn, ts, text, created_at)
            )
            conn.commit()
            return (True, False)
        except sqlite3.IntegrityError:
            # Duplicate message_id - this is expected for idempotent calls
            return (True, True)
        except Exception:
            return (False, False)
        finally:
            conn.close()
    
    @staticmethod
    def get_messages(
        limit: int = 50,
        offset: int = 0,
        from_filter: Optional[str] = None,
        since: Optional[str] = None,
        q: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get messages with pagination and filters.
        
        Args:
            limit: Maximum number of messages to return (1-100)
            offset: Number of messages to skip
            from_filter: Filter by exact from_msisdn match
            since: Filter messages with ts >= since
            q: Case-insensitive substring search in text field
        
        Returns:
            Dict with 'data', 'total', 'limit', 'offset' keys
        """
        conn = get_connection()
        try:
            # Build WHERE clause dynamically
            conditions = []
            params: List[Any] = []
            
            if from_filter:
                conditions.append("from_msisdn = ?")
                params.append(from_filter)
            
            if since:
                conditions.append("ts >= ?")
                params.append(since)
            
            if q:
                conditions.append("LOWER(text) LIKE ?")
                params.append(f"%{q.lower()}%")
            
            where_clause = ""
            if conditions:
                where_clause = "WHERE " + " AND ".join(conditions)
            
            # Get total count (ignoring limit/offset)
            count_query = f"SELECT COUNT(*) as total FROM messages {where_clause}"
            cursor = conn.cursor()
            cursor.execute(count_query, params)
            total = cursor.fetchone()["total"]
            
            # Get paginated data with deterministic ordering
            data_query = f"""
                SELECT message_id, from_msisdn, to_msisdn, ts, text
                FROM messages
                {where_clause}
                ORDER BY ts ASC, message_id ASC
                LIMIT ? OFFSET ?
            """
            data_params = params + [limit, offset]
            cursor.execute(data_query, data_params)
            
            rows = cursor.fetchall()
            data = [
                {
                    "message_id": row["message_id"],
                    "from": row["from_msisdn"],
                    "to": row["to_msisdn"],
                    "ts": row["ts"],
                    "text": row["text"]
                }
                for row in rows
            ]
            
            return {
                "data": data,
                "total": total,
                "limit": limit,
                "offset": offset
            }
        finally:
            conn.close()
    
    @staticmethod
    def get_stats() -> Dict[str, Any]:
        """
        Get message statistics.
        
        Returns:
            Dict with total_messages, senders_count, messages_per_sender,
            first_message_ts, last_message_ts
        """
        conn = get_connection()
        try:
            cursor = conn.cursor()
            
            # Total messages
            cursor.execute("SELECT COUNT(*) as total FROM messages")
            total_messages = cursor.fetchone()["total"]
            
            # Unique senders count
            cursor.execute("SELECT COUNT(DISTINCT from_msisdn) as count FROM messages")
            senders_count = cursor.fetchone()["count"]
            
            # Top 10 senders by message count
            cursor.execute("""
                SELECT from_msisdn, COUNT(*) as count
                FROM messages
                GROUP BY from_msisdn
                ORDER BY count DESC
                LIMIT 10
            """)
            messages_per_sender = [
                {"from": row["from_msisdn"], "count": row["count"]}
                for row in cursor.fetchall()
            ]
            
            # First and last message timestamps
            cursor.execute("SELECT MIN(ts) as first_ts, MAX(ts) as last_ts FROM messages")
            row = cursor.fetchone()
            first_message_ts = row["first_ts"]
            last_message_ts = row["last_ts"]
            
            return {
                "total_messages": total_messages,
                "senders_count": senders_count,
                "messages_per_sender": messages_per_sender,
                "first_message_ts": first_message_ts,
                "last_message_ts": last_message_ts
            }
        finally:
            conn.close()
