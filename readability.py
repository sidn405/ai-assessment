# Readability Scoring Utilities
# Implements Flesch-Kincaid and other readability formulas

import re
import math
from typing import Dict, Tuple

def count_syllables(word: str) -> int:
    """
    Count syllables in a word using a simple heuristic.
    """
    word = word.lower()
    vowels = "aeiouy"
    syllable_count = 0
    previous_was_vowel = False
    
    for char in word:
        is_vowel = char in vowels
        if is_vowel and not previous_was_vowel:
            syllable_count += 1
        previous_was_vowel = is_vowel
    
    # Adjust for silent 'e'
    if word.endswith('e'):
        syllable_count -= 1
    
    # Every word has at least one syllable
    if syllable_count == 0:
        syllable_count = 1
    
    return syllable_count

def count_sentences(text: str) -> int:
    """Count sentences in text."""
    # Split on sentence-ending punctuation
    sentences = re.split(r'[.!?]+', text)
    # Filter out empty strings
    sentences = [s.strip() for s in sentences if s.strip()]
    return max(len(sentences), 1)  # At least 1 sentence

def count_words(text: str) -> int:
    """Count words in text."""
    words = re.findall(r'\b\w+\b', text)
    return len(words)

def flesch_reading_ease(text: str) -> float:
    """
    Calculate Flesch Reading Ease score (0-100).
    Higher score = easier to read.
    
    90-100: Very easy (5th grade)
    80-90: Easy (6th grade)
    70-80: Fairly easy (7th grade)
    60-70: Standard (8th-9th grade)
    50-60: Fairly difficult (10th-12th grade)
    30-50: Difficult (college)
    0-30: Very difficult (college graduate)
    """
    words = re.findall(r'\b\w+\b', text)
    word_count = len(words)
    sentence_count = count_sentences(text)
    syllable_count = sum(count_syllables(word) for word in words)
    
    if word_count == 0 or sentence_count == 0:
        return 0
    
    avg_syllables_per_word = syllable_count / word_count
    avg_words_per_sentence = word_count / sentence_count
    
    score = 206.835 - (1.015 * avg_words_per_sentence) - (84.6 * avg_syllables_per_word)
    
    # Clamp between 0 and 100
    return max(0, min(100, score))

def flesch_kincaid_grade(text: str) -> float:
    """
    Calculate Flesch-Kincaid Grade Level.
    Returns the US grade level needed to understand the text.
    
    5.0 = 5th grade level
    8.0 = 8th grade level
    12.0 = 12th grade (high school senior)
    13+ = College level
    """
    words = re.findall(r'\b\w+\b', text)
    word_count = len(words)
    sentence_count = count_sentences(text)
    syllable_count = sum(count_syllables(word) for word in words)
    
    if word_count == 0 or sentence_count == 0:
        return 0
    
    avg_syllables_per_word = syllable_count / word_count
    avg_words_per_sentence = word_count / sentence_count
    
    grade = (0.39 * avg_words_per_sentence) + (11.8 * avg_syllables_per_word) - 15.59
    
    return max(0, grade)

def analyze_readability(text: str) -> Dict[str, any]:
    """
    Comprehensive readability analysis.
    Returns multiple metrics for the text.
    """
    word_count = count_words(text)
    sentence_count = count_sentences(text)
    
    words = re.findall(r'\b\w+\b', text)
    syllable_count = sum(count_syllables(word) for word in words)
    
    flesch_ease = flesch_reading_ease(text)
    fk_grade = flesch_kincaid_grade(text)
    
    # Estimate reading time (average 200-250 words per minute for adults)
    # Use 150 wpm for learners
    estimated_minutes = max(1, round(word_count / 150))
    
    # Determine difficulty level
    if fk_grade <= 5:
        difficulty = "beginner"
    elif fk_grade <= 8:
        difficulty = "intermediate"
    else:
        difficulty = "advanced"
    
    # Determine grade band
    if fk_grade <= 5:
        grade_band = "elementary"
    elif fk_grade <= 8:
        grade_band = "middle"
    elif fk_grade <= 12:
        grade_band = "high"
    else:
        grade_band = "adult"
    
    return {
        "word_count": word_count,
        "sentence_count": sentence_count,
        "syllable_count": syllable_count,
        "avg_words_per_sentence": round(word_count / sentence_count, 1) if sentence_count > 0 else 0,
        "avg_syllables_per_word": round(syllable_count / word_count, 2) if word_count > 0 else 0,
        "flesch_reading_ease": round(flesch_ease, 1),
        "flesch_kincaid_grade": round(fk_grade, 1),
        "difficulty_level": difficulty,
        "grade_band": grade_band,
        "estimated_minutes": estimated_minutes,
        "readability_description": get_readability_description(flesch_ease)
    }

def get_readability_description(flesch_ease: float) -> str:
    """Get human-readable description of Flesch Reading Ease score."""
    if flesch_ease >= 90:
        return "Very Easy - 5th grade level"
    elif flesch_ease >= 80:
        return "Easy - 6th grade level"
    elif flesch_ease >= 70:
        return "Fairly Easy - 7th grade level"
    elif flesch_ease >= 60:
        return "Standard - 8th-9th grade level"
    elif flesch_ease >= 50:
        return "Fairly Difficult - 10th-12th grade level"
    elif flesch_ease >= 30:
        return "Difficult - College level"
    else:
        return "Very Difficult - Graduate level"

def get_difficulty_for_user(user_level: str, target_challenge: str = "appropriate") -> Tuple[float, float]:
    """
    Get grade level range for content selection based on user level.
    
    Args:
        user_level: 'beginner', 'intermediate', 'advanced'
        target_challenge: 'easier', 'appropriate', 'challenging'
    
    Returns:
        Tuple of (min_grade, max_grade)
    """
    base_ranges = {
        "beginner": (2, 5),
        "intermediate": (6, 8),
        "advanced": (9, 12)
    }
    
    min_grade, max_grade = base_ranges.get(user_level, (6, 8))
    
    if target_challenge == "easier":
        # Drop by 2 grade levels
        min_grade = max(1, min_grade - 2)
        max_grade = max(3, max_grade - 2)
    elif target_challenge == "challenging":
        # Raise by 2 grade levels
        min_grade = min_grade + 2
        max_grade = max_grade + 2
    
    return (min_grade, max_grade)

# Example usage and testing
if __name__ == "__main__":
    sample_text = """
    The sun was shining brightly in the clear blue sky. Birds were singing in the trees.
    It was a perfect day for a picnic in the park.
    """
    
    analysis = analyze_readability(sample_text)
    print("Readability Analysis:")
    for key, value in analysis.items():
        print(f"  {key}: {value}")