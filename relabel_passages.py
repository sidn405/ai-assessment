# relabel_passages.py
from app import get_db, get_cursor, USE_POSTGRES


conn = get_db()
cursor = get_cursor(conn)

# Get all passages
cursor.execute("SELECT id, word_count, difficulty_level FROM passages")
passages = cursor.fetchall()

relabeled = 0

for p in passages:
    pid = p['id'] if hasattr(p, 'keys') else p[0]
    wc = p['word_count'] if hasattr(p, 'keys') else p[1]
    old_level = p['difficulty_level'] if hasattr(p, 'keys') else p[2]
    
    # Determine correct level based on word count
    if wc < 200:
        new_level = 'beginner'
    elif wc < 250:
        new_level = 'intermediate'
    else:
        new_level = 'advanced'
    
    if old_level != new_level:
        print(f"Passage {pid}: {wc} words, {old_level} → {new_level}")
        
        if USE_POSTGRES:
            cursor.execute(
                "UPDATE passages SET difficulty_level = %s WHERE id = %s",
                (new_level, pid)
            )
        else:
            cursor.execute(
                "UPDATE passages SET difficulty_level = ? WHERE id = ?",
                (new_level, pid)
            )
        
        relabeled += 1

conn.commit()
conn.close()

print(f"\n✅ Relabeled {relabeled} passages")