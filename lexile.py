# Add to your backend (server.py or routes.py)

def calculate_lexile_from_text(text):
    """
    Calculate approximate Lexile level from text using:
    - Average sentence length
    - Average word length
    - Vocabulary complexity
    """
    import re
    from textstat import flesch_kincaid_grade
    
    # Split into sentences
    sentences = re.split(r'[.!?]+', text)
    sentences = [s.strip() for s in sentences if s.strip()]
    
    # Calculate metrics
    avg_sentence_length = sum(len(s.split()) for s in sentences) / len(sentences) if sentences else 0
    words = text.split()
    avg_word_length = sum(len(w) for w in words) / len(words) if words else 0
    
    # Get Flesch-Kincaid grade level
    fk_grade = flesch_kincaid_grade(text)
    
    # Convert to Lexile (approximate formula)
    # Lexile ≈ (FK Grade × 100) + 200
    lexile = int((fk_grade * 100) + 200)
    
    # Clamp between 0 and 1600
    return max(0, min(1600, lexile))


def get_lexile_range_for_level(reading_level):
    """Map reading level to Lexile range"""
    lexile_map = {
        'beginner': (0, 300),
        'elementary': (300, 600),
        'intermediate': (600, 900),
        'middle_school': (900, 1100),
        'high_school': (1100, 1300),
        'advanced': (1300, 1600)
    }
    return lexile_map.get(reading_level, (400, 600))


def get_lexile_label(lexile):
    """Convert numeric Lexile to readable label"""
    if lexile < 300:
        return "Beginning Reader (BR-300L)"
    elif lexile < 600:
        return "Elementary (300-600L)"
    elif lexile < 900:
        return "Intermediate (600-900L)"
    elif lexile < 1100:
        return "Middle School (900-1100L)"
    elif lexile < 1300:
        return "High School (1100-1300L)"
    else:
        return "Advanced (1300L+)"


@app.route('/api/lessons/by-lexile', methods=['POST'])
async def get_lessons_by_lexile(request):
    """Get lessons matching student's Lexile level"""
    data = await request.json()
    user_id = data.get('user_id')
    target_lexile = data.get('lexile_level')
    
    # Get user's current Lexile level
    user = await db.fetch_one(
        "SELECT lexile_level, reading_level FROM users WHERE id = ?", 
        (user_id,)
    )
    
    if not user:
        return response.json({'error': 'User not found'}, status=404)
    
    lexile = target_lexile or user['lexile_level'] or 500
    
    # Find lessons within ±100L of student's level
    lessons = await db.fetch_all("""
        SELECT * FROM lessons 
        WHERE lexile_level BETWEEN ? AND ?
        ORDER BY lexile_level, id
        LIMIT 20
    """, (lexile - 100, lexile + 100))
    
    return response.json({
        'success': True,
        'lexile_level': lexile,
        'lexile_label': get_lexile_label(lexile),
        'lessons': lessons
    })


@app.route('/api/user/update-lexile', methods=['POST'])
async def update_user_lexile(request):
    """Update user's Lexile level based on performance"""
    data = await request.json()
    user_id = data.get('user_id')
    score = data.get('score')
    lesson_lexile = data.get('lesson_lexile')
    
    # Get current Lexile
    user = await db.fetch_one(
        "SELECT lexile_level FROM users WHERE id = ?", 
        (user_id,)
    )
    
    current_lexile = user['lexile_level'] or 500
    
    # Adjust Lexile based on performance
    if score >= 90:
        # Excellent - increase by 20L
        new_lexile = min(1600, current_lexile + 20)
    elif score >= 80:
        # Good - increase by 10L
        new_lexile = min(1600, current_lexile + 10)
    elif score >= 70:
        # Fair - maintain
        new_lexile = current_lexile
    else:
        # Needs improvement - decrease by 10L
        new_lexile = max(100, current_lexile - 10)
    
    # Update database
    await db.execute(
        "UPDATE users SET lexile_level = ? WHERE id = ?",
        (new_lexile, user_id)
    )
    
    return response.json({
        'success': True,
        'previous_lexile': current_lexile,
        'new_lexile': new_lexile,
        'lexile_label': get_lexile_label(new_lexile),
        'change': new_lexile - current_lexile
    })