# AI Content Generation Pipeline
# Generates reading passages and comprehension questions using OpenAI

from openai import OpenAI
import json
import os
from typing import List, Dict, Optional
from readability import analyze_readability


class ContentGenerator:
    def __init__(self, api_key=None):
        """Initialize with OpenAI API key"""
        self.api_key = api_key or os.getenv('OPENAI_API_KEY')
        if not self.api_key:
            raise ValueError("OpenAI API key is required")
        
        # NEW API - Create client
        self.client = OpenAI(api_key=self.api_key)
        
    def _rewrite_passage_to_word_range(self, title, content, topic, difficulty_level, word_count_min, word_count_max, target_words):
        prompt = f"""
Rewrite the passage below into a NEW VERSION that is BETWEEN {word_count_min} and {word_count_max} words
(aim for about {target_words} words).

Hard rules:
- Keep it a STORY (narrative), not an explanation/definition.
- Keep the same topic focus: {topic}
- Keep difficulty level: {difficulty_level}
- Same main character(s) and setting, but you may add 1-2 new details to reach the word count naturally.
- No headings, no bullet points.

Return ONLY valid JSON with:
{{
  "title": "{title}",
  "content": "...",
  "key_concepts": ["...", "...", "..."],
  "vocabulary_words": [{{"word":"...","definition":"..."}}, ...]
}}

PASSAGE TO REWRITE:
{content}
"""
        resp = self.client.chat.completions.create(
            model="gpt-4-turbo-preview",
            messages=[
                {"role": "system", "content": "You rewrite reading passages to match an exact word range while keeping a narrative story style."},
                {"role": "user", "content": prompt},
            ],
            temperature=0.5,
            max_tokens=2500,
            timeout=60
        )
        txt = resp.choices[0].message.content
        if "```json" in txt:
            txt = txt.split("```json")[1].split("```")[0].strip()
        elif "```" in txt:
            txt = txt.split("```")[1].split("```")[0].strip()
        return json.loads(txt)
    
    def generate_passage(self, topic, difficulty_level, word_count_min, word_count_max, user_interests):
        """Generate educational passage using GPT-4 with dynamic word count"""
        
        # Calculate target from range
        import random
        target_words = random.randint(word_count_min, word_count_max)
        
        # ========== UPDATED PROMPT WITH COMPREHENSIVE VOCABULARY ==========
        prompt = f"""Write a SHORT STORY (narrative) about {topic}.
    Difficulty Level: {difficulty_level}
    Word Count: Between {word_count_min} and {word_count_max} words (aim for approximately {target_words} words)
    
    DIFFICULTY GUIDELINES:
    - elementary: 4th-6th grade level, simple sentences, common words
    - intermediate: 7th-9th grade level, moderate complexity
    - high_school: 10th-12th grade level, complex sentences, academic vocabulary
    - adult: College+ level, sophisticated vocabulary, abstract concepts, nuanced ideas

    {'''For HIGH_SCHOOL and ADULT levels:
    - Use complex sentence structures (20-30 words)
    - Include sophisticated, academic vocabulary
    - Discuss abstract or multi-layered concepts
    - Use literary devices (metaphors, analogies)
    - Assume strong reading comprehension
    ''' if difficulty_level in ['high_school', 'adult'] else ''}

    Topic: {topic}
    Make this story interesting for someone who likes {topic}.
    Use {topic}-related scenarios, settings, and examples.

    IMPORTANT: 
    - Focus ONLY on {topic}
    - Do NOT try to combine with other topics
    - Make it engaging and age-appropriate
    - Use clear, accessible language

    CRITICAL - VOCABULARY EXTRACTION:
    - Identify ALL potentially challenging words in the passage
    - Include words that a {difficulty_level} reader might not know
    - For each word, provide a simple, age-appropriate definition
    - Include at least 5-8 vocabulary words (more for longer passages)
    - Look for: academic terms, technical words, advanced vocabulary, subject-specific jargon
    - Examples: "phenomenon", "transformation", "immersive", "gratification", "tangible", "palpable", etc.
    
    Hard rules:
    - This MUST be a story with a character, setting, and a small plot (beginning → problem → resolution)
    - Do NOT write an article, definition, or history lesson
    - Do NOT explain the topic directly; SHOW the topic through what happens in the story
    - Include at least one line of dialogue
    - Keep it realistic/relatable and age-appropriate

    Generate a passage that explores {topic} in an interesting way.

    Return your response as a JSON object with this exact structure:
    {{
        "title": "Specific title about {topic}",
        "content": "The full passage text (approximately {target_words} words, focused on {topic})",
        "key_concepts": ["concept1", "concept2", "concept3"],
        "vocabulary_words": [
            {{"word": "challenging_word1", "definition": "simple, clear definition"}},
            {{"word": "challenging_word2", "definition": "simple, clear definition"}},
            {{"word": "challenging_word3", "definition": "simple, clear definition"}},
            {{"word": "challenging_word4", "definition": "simple, clear definition"}},
            {{"word": "challenging_word5", "definition": "simple, clear definition"}},
            {{"word": "challenging_word6", "definition": "simple, clear definition"}},
            {{"word": "challenging_word7", "definition": "simple, clear definition"}},
            {{"word": "challenging_word8", "definition": "simple, clear definition"}}
        ]
    }}

    VOCABULARY GUIDELINES BY LEVEL:
    - elementary: Words at 4th-6th grade level (5-7 words minimum)
    - intermediate: Words at 7th-9th grade level (6-8 words minimum)
    - high_school: College-prep vocabulary (7-10 words minimum)
    - adult: Advanced academic vocabulary (8-12 words minimum)"""
        
        try:
            # NEW API SYNTAX
            response = self.client.chat.completions.create(
                model="gpt-4-turbo-preview",
                messages=[
                    {
                        "role": "system",
                        "content": """You are an expert educational content creator. 

    CRITICAL VOCABULARY INSTRUCTION:
    Extract ALL words from your passage that might be challenging for the target reading level. 
    Don't limit yourself to just 2-3 words - identify EVERY word that a student might need help understanding.
    A good passage should have AT LEAST 5-10 vocabulary words, more for longer passages.

    Examples of words to include:
    - Elementary: "ecosystem", "gravity", "nutrient", "habitat", "diverse"
    - Intermediate: "phenomenon", "inevitable", "perspective", "substantial", "comprehensive"  
    - High School: "culmination", "juxtaposition", "paradigm", "synthesis", "nuance"
    - Adult: "epistemology", "hegemony", "empirical", "ubiquitous", "pragmatic"

    Focus on ONE topic at a time. Do not blend multiple topics together."""
                    },
                    {"role": "user", "content": prompt}
                ],
                temperature=0.8,
                max_tokens=2500,
                timeout=60
            )
            
            content = response.choices[0].message.content
            
            # Extract JSON
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()
            
            passage_data = json.loads(content)
            
            # ========== VALIDATE & ENHANCE VOCABULARY ==========
            vocab_words = passage_data.get('vocabulary_words', [])
            vocab_count = len(vocab_words)
            
            print(f"📚 Initial vocabulary words: {vocab_count}")
            
            # Minimum vocabulary requirements by level
            min_vocab = {
                'elementary': 5,
                'intermediate': 6,
                'high_school': 7,
                'adult': 8
            }
            
            required_min = min_vocab.get(difficulty_level, 5)
            
            if vocab_count < required_min:
                print(f"⚠️ Only {vocab_count} words found. Need at least {required_min}. Extracting more...")
                passage_data['vocabulary_words'] = self._extract_additional_vocabulary(
                    passage_data['content'], 
                    vocab_words,
                    difficulty_level,
                    required_min
                )
                print(f"✅ Enhanced to {len(passage_data['vocabulary_words'])} vocabulary words")
            # ==================================================
            
            # Analyze readability
            from readability import analyze_readability
            readability = analyze_readability(passage_data['content'])
            
            def _rewrite_passage_to_word_range(self, title, content, topic, difficulty_level, word_count_min, word_count_max, target_words):
                prompt = f"""
            Rewrite the passage below into a NEW VERSION that is BETWEEN {word_count_min} and {word_count_max} words
            (aim for about {target_words} words).

            Return ONLY valid JSON with:
            {{
            "title": "{title}",
            "content": "...",
            "key_concepts": ["...", "...", "..."],
            "vocabulary_words": [{{"word":"...","definition":"..."}}, ...]
            }}

            PASSAGE TO REWRITE:
            {content}
            """
                resp = self.client.chat.completions.create(
                    model="gpt-4-turbo-preview",
                    messages=[
                        {"role": "system", "content": "You rewrite reading passages to match an exact word range while keeping a narrative story style."},
                        {"role": "user", "content": prompt},
                    ],
                    temperature=0.5,
                    max_tokens=2500,
                    timeout=60
                )
                txt = resp.choices[0].message.content
                if "```json" in txt:
                    txt = txt.split("```json")[1].split("```")[0].strip()
                elif "```" in txt:
                    txt = txt.split("```")[1].split("```")[0].strip()
                return json.loads(txt)   
            
            wc = readability['word_count']
            if wc < word_count_min or wc > word_count_max:
                passage_data = self._rewrite_passage_to_word_range(
                    title=passage_data.get("title", f"{topic}"),
                    content=passage_data["content"],
                    topic=topic,
                    difficulty_level=difficulty_level,
                    word_count_min=word_count_min,
                    word_count_max=word_count_max,
                    target_words=target_words
                )
                readability = analyze_readability(passage_data['content'])
                
            
            # Add metadata
            passage_data.update({
                "source": "AI",
                "topic_tags": [topic],
                "word_count": readability['word_count'],
                "readability_score": readability['flesch_kincaid_grade'],
                "flesch_ease": readability['flesch_reading_ease'],
                "difficulty_level": difficulty_level,
                "estimated_minutes": readability['estimated_minutes'],
                "actual_difficulty": readability['difficulty_level'],
                "grade_band": readability['grade_band'],
                "target_word_range": f"{word_count_min}-{word_count_max}",
                "vocabulary_count": len(passage_data['vocabulary_words'])
            })
            
            print(f"✅ Generated passage: '{passage_data['title']}'")
            print(f"✅ Word count: {readability['word_count']} (target: {word_count_min}-{word_count_max})")
            print(f"✅ Vocabulary words: {len(passage_data['vocabulary_words'])}")
            
            return passage_data
            
        except Exception as e:
            print(f"Error generating passage: {e}")
            import traceback
            traceback.print_exc()
            return self._get_fallback_passage(topic, difficulty_level)

    def _extract_additional_vocabulary(self, passage_text, existing_vocab, difficulty_level, min_required=5):
        """
        Use AI to extract more vocabulary words if initial extraction was insufficient
        
        Args:
            passage_text: The full passage content
            existing_vocab: List of already identified vocabulary dicts
            difficulty_level: Target difficulty (elementary, intermediate, etc.)
            min_required: Minimum number of total vocabulary words needed
        """
        existing_words = [v['word'].lower() for v in existing_vocab]
        words_needed = max(min_required - len(existing_vocab), 3)
        
        print(f"🔍 Extracting {words_needed} more vocabulary words...")
        
        prompt = f"""Analyze this passage and extract {words_needed} MORE challenging vocabulary words for a {difficulty_level} level reader.

    Passage:
    {passage_text}

    Already identified: {', '.join(existing_words) if existing_words else 'none'}

    Find {words_needed} MORE challenging words from this passage that students at {difficulty_level} level might not know.

    Focus on:
    - Academic vocabulary
    - Technical terms
    - Uncommon words
    - Subject-specific terminology
    - Advanced descriptive words

    Provide simple, age-appropriate definitions.

    Return ONLY a JSON array (no other text):
    [
        {{"word": "word1", "definition": "simple definition"}},
        {{"word": "word2", "definition": "simple definition"}},
        {{"word": "word3", "definition": "simple definition"}}
    ]"""

        try:
            response = self.client.chat.completions.create(
                model="gpt-4-turbo-preview",
                messages=[
                    {
                        "role": "system",
                        "content": f"Extract challenging vocabulary for {difficulty_level} readers. Provide simple definitions."
                    },
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=1000,
                timeout=30
            )
            
            content = response.choices[0].message.content
            
            # Extract JSON
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()
            
            additional_vocab = json.loads(content)
            
            # Combine with existing, avoid duplicates
            all_vocab = existing_vocab.copy()
            added_count = 0
            
            for new_word in additional_vocab:
                word_lower = new_word['word'].lower()
                if word_lower not in existing_words:
                    all_vocab.append(new_word)
                    existing_words.append(word_lower)
                    added_count += 1
            
            print(f"✅ Added {added_count} new vocabulary words")
            return all_vocab
            
        except Exception as e:
            print(f"❌ Error extracting additional vocabulary: {e}")
            import traceback
            traceback.print_exc()
            # Return existing vocabulary if extraction fails
            return existing_vocab

    def _get_fallback_passage(self, topic, difficulty):
        """Return a basic fallback passage if AI generation fails"""
        return {
            "title": f"Introduction to {topic}",
            "content": f"This is a {difficulty} passage about {topic}. [AI generation unavailable - please try again or contact administrator]",
            "source": "fallback",
            "topic_tags": [topic],
            "word_count": 50,
            "readability_score": 5.0,
            "flesch_ease": 70.0,
            "difficulty_level": difficulty,
            "estimated_minutes": 1,
            "key_concepts": [topic],
            "vocabulary_words": [
                {"word": "topic", "definition": "The main subject being discussed"},
                {"word": "passage", "definition": "A section of written text"},
                {"word": "educational", "definition": "Related to learning and teaching"}
            ],
            "vocabulary_count": 3
        }
            
    def generate_comprehension_questions(self, passage_text, passage_title, num_questions=3):
        """Generate comprehension questions using GPT-4"""
        
        prompt = f"""Based on the following passage, create {num_questions} comprehension questions.

Passage Title: {passage_title}

Passage:
{passage_text}

Generate questions that test understanding at different levels (recall, inference, analysis).

Return your response as a JSON array with this exact structure:
[
    {{
        "question": "Question text here?",
        "type": "main_idea|detail|inference|vocabulary",
        "options": ["Option A", "Option B", "Option C", "Option D"],
        "correct_answer": "The correct option text",
        "explanation": "Why this is correct",
        "difficulty": 1-3
    }}
]"""

        try:
            # NEW API SYNTAX
            response = self.client.chat.completions.create(
                model="gpt-4-turbo-preview",
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert at creating educational assessment questions."
                    },
                    {"role": "user", "content": prompt}
                ],
                temperature=0.7,
                max_tokens=1000,
                timeout=60
            )
            
            content = response.choices[0].message.content
            
            # Extract JSON
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()
            
            questions = json.loads(content)
            # ========== ADD THIS SECTION ==========
            # Shuffle options for each question to randomize correct answer position
            import random
            for q in questions:
                if 'options' in q and isinstance(q['options'], list):
                    # Shuffle the options
                    random.shuffle(q['options'])
            # =====================================
            
            return questions
            
        except Exception as e:
            print(f"Error generating questions: {e}")
            import traceback
            traceback.print_exc()
            return self._get_fallback_questions()
    
    def _extract_topics(self, main_topic, interests):
        """Extract relevant topic tags"""
        topics = [main_topic]
        topics.extend(interests[:3])
        return topics
    
    def _get_fallback_passage(self, topic, difficulty):
        """Return a basic fallback passage if AI generation fails"""
        return {
            "title": f"Introduction to {topic}",
            "content": f"This is a {difficulty} passage about {topic}. [AI generation unavailable - please try again or contact administrator]",
            "source": "fallback",
            "topic_tags": [topic],
            "word_count": 50,
            "readability_score": 5.0,
            "flesch_ease": 70.0,
            "difficulty_level": difficulty,
            "estimated_minutes": 1,
            "key_concepts": [topic],
            "vocabulary_words": []
        }

# Example usage
if __name__ == "__main__":
    # Test the content generator
    generator = ContentGenerator(api_key="your-key-here")
    
    passage = generator.generate_passage(
        topic="space exploration",
        difficulty_level="intermediate",
        target_words=250,
        user_interests=["science", "technology"]
    )
    
    print("Generated Passage:")
    print(f"Title: {passage['title']}")
    print(f"Word Count: {passage['word_count']}")
    print(f"Difficulty: {passage['difficulty_level']}")
    print(f"Readability Score: {passage['readability_score']}")