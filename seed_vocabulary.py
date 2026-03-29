import os
import psycopg2
from psycopg2.extras import execute_batch

# Get database URL from environment
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    print("❌ ERROR: DATABASE_URL environment variable not set")
    print("Set it with: $env:DATABASE_URL = \"your_postgres_url\"")
    exit(1)

# Convert postgres:// to postgresql:// if needed
if DATABASE_URL.startswith("postgres://"):
    DATABASE_URL = DATABASE_URL.replace("postgres://", "postgresql://", 1)

# Vocabulary data
vocabulary_words = [
    ('resilient', 'able to recover quickly from difficulties'),
    ('ambitious', 'having a strong desire to succeed'),
    ('innovative', 'introducing new ideas or methods'),
    ('persistent', 'continuing firmly despite difficulty'),
    ('thoughtful', 'showing careful consideration'),
    ('authentic', 'genuine and true to oneself'),
    ('diligent', 'showing care and effort in work'),
    ('confident', 'feeling certain about abilities'),
    ('curious', 'eager to learn or know something'),
    ('methodical', 'done in a systematic way'),
    ('organized', 'arranged in a systematic way'),
    ('articulate', 'able to express ideas clearly'),
    ('compassionate', 'showing sympathy and concern'),
    ('creative', 'using imagination to create'),
    ('dedicated', 'devoted to a task or purpose'),
    ('empathetic', 'able to understand others feelings'),
    ('flexible', 'able to adapt to change'),
    ('gracious', 'courteous and kind'),
    ('humble', 'modest and respectful'),
    ('insightful', 'having deep understanding'),
    ('meticulous', 'showing great attention to detail'),
    ('optimistic', 'hopeful about the future'),
    ('proactive', 'taking action before problems occur'),
    ('resourceful', 'able to find clever solutions'),
    ('strategic', 'carefully planned to achieve goals'),
    ('tenacious', 'holding firmly to goals'),
    ('versatile', 'able to adapt to different tasks'),
    ('analytical', 'skilled at examining details'),
    ('collaborative', 'working well with others'),
    ('enthusiastic', 'showing intense enjoyment'),
    ('adaptable', 'able to adjust to new conditions'),
    ('conscientious', 'wishing to do what is right'),
    ('determined', 'having made a firm decision'),
    ('efficient', 'working productively with minimal waste'),
    ('imaginative', 'having creative ideas'),
    ('observant', 'quick to notice things'),
    ('practical', 'concerned with actual use'),
    ('rational', 'based on reason and logic'),
    ('sincere', 'free from pretense'),
    ('trustworthy', 'able to be relied on'),
    ('vigorous', 'strong and energetic'),
    ('wise', 'having experience and knowledge'),
    ('zealous', 'having great energy for a cause'),
    ('astute', 'having shrewd judgment'),
    ('brilliant', 'exceptionally clever'),
    ('capable', 'having ability and competence'),
    ('diplomatic', 'skilled in dealing with people'),
    ('eloquent', 'fluent and persuasive in speaking'),
    ('faithful', 'remaining loyal and steadfast'),
    ('generous', 'showing kindness and giving'),
]

print("🔌 Connecting to database...")
try:
    conn = psycopg2.connect(DATABASE_URL)
    cursor = conn.cursor()
    print("✅ Connected!")
    
    # Check current count
    cursor.execute("SELECT COUNT(*) FROM vocabulary_tracker")
    current_count = cursor.fetchone()[0]
    print(f"📊 Current vocabulary count: {current_count}")
    
    # Insert vocabulary
    print(f"📝 Inserting {len(vocabulary_words)} vocabulary words...")
    
    # Use user_id 77 (or change this to the user you want to seed for)
    USER_ID = 77
    print(f"📌 Seeding vocabulary for user_id: {USER_ID}")
    
    inserted = 0
    for word, definition in vocabulary_words:
        try:
            # Check if word already exists for this user
            cursor.execute("""
                SELECT COUNT(*) FROM vocabulary_tracker 
                WHERE word = %s AND user_id = %s
            """, (word, USER_ID))
            
            exists = cursor.fetchone()[0] > 0
            
            if not exists:
                cursor.execute("""
                    INSERT INTO vocabulary_tracker (user_id, word, definition, encountered_count)
                    VALUES (%s, %s, %s, 0)
                """, (USER_ID, word, definition))
                inserted += 1
                print(f"  ✓ Inserted: {word}")
            else:
                print(f"  ⊘ Skipped (exists): {word}")
                
        except Exception as e:
            print(f"  ❌ Failed to insert '{word}': {e}")
            conn.rollback()  # Rollback failed transaction
            continue
    
    conn.commit()
    print(f"✅ Inserted {inserted} new words!")
    
    # Verify final count
    cursor.execute("SELECT COUNT(*) FROM vocabulary_tracker")
    final_count = cursor.fetchone()[0]
    print(f"📊 Final vocabulary count: {final_count}")
    
    # Show sample
    cursor.execute("SELECT word, definition FROM vocabulary_tracker LIMIT 5")
    sample = cursor.fetchall()
    print("\n📚 Sample vocabulary:")
    for word, definition in sample:
        print(f"  • {word}: {definition}")
    
    cursor.close()
    conn.close()
    print("\n🎉 Vocabulary seeding complete!")
    
except Exception as e:
    print(f"❌ Error: {e}")
    import traceback
    traceback.print_exc()
    exit(1)