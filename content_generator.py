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
        
    def _get_cultural_context_guidance(age, grade_band):
        """
        Provides age-appropriate cultural context guidance
        """
        contexts = {
            'elementary': {
                'settings': ['playground', 'classroom', 'community center', 'library', 'park', 'corner store'],
                'characters': ['students', 'teachers', 'parents', 'grandparents', 'librarians', 'coaches'],
                'themes': ['friendship', 'learning', 'helping others', 'trying new things', 'community'],
                'avoid': ['Keep it simple and positive', 'No complex social issues', 'Focus on everyday experiences']
            },
            'middle': {
                'settings': ['school', 'community center', 'basketball court', 'tech lab', 'after-school program', 'local business'],
                'characters': ['students', 'mentors', 'coaches', 'small business owners', 'community leaders', 'older siblings'],
                'themes': ['discovering talents', 'overcoming challenges', 'leadership', 'innovation', 'community service'],
                'avoid': ['Avoid trauma', 'No criminal justice references', 'Focus on growth and potential']
            },
            'high': {
                'settings': ['high school', 'internships', 'community college', 'local businesses', 'volunteer programs', 'STEM programs'],
                'characters': ['students', 'mentors', 'entrepreneurs', 'professionals', 'college students', 'counselors'],
                'themes': ['career exploration', 'college prep', 'leadership', 'social justice', 'entrepreneurship', 'identity'],
                'avoid': ['Respectful of complex realities', 'Focus on agency and empowerment', 'No deficit narratives']
            },
            'adult': {
                'settings': ['workplace', 'community organizations', 'professional settings', 'entrepreneurship', 'continuing education'],
                'characters': ['professionals', 'entrepreneurs', 'community leaders', 'working parents', 'returning students'],
                'themes': ['career advancement', 'community building', 'economic mobility', 'lifelong learning', 'giving back'],
                'avoid': ['Acknowledge challenges without dwelling', 'Focus on resilience and success', 'Asset-based approach']
            }
        }
        
        # Map grade to category
        if grade_band in ['pre-k', 'kindergarten', '1st', '2nd', '3rd', '4th', '5th', 'elementary']:
            category = 'elementary'
        elif grade_band in ['6th', '7th', '8th', 'middle']:
            category = 'middle'
        elif grade_band in ['9th', '10th', '11th', '12th', 'high']:
            category = 'high'
        else:
            category = 'adult'
        
        return contexts.get(category, contexts['elementary'])
    
    
        
    def _rewrite_passage_to_word_range(self, title, content, topic, difficulty_level, word_count_min, word_count_max, target_words):
        prompt = f"""
        Rewrite the passage below into a NEW VERSION.

        HARD WORD COUNT RULE:
        - The "content" field MUST be EXACTLY {target_words} words (content only).
        - Count words by splitting on spaces.
        - Before responding, self-check and adjust until exactly {target_words}.

        Hard rules:
        - Keep it a STORY (narrative), not an explanation/definition.
        - Keep the same topic focus: {topic}
        - Keep difficulty level: {difficulty_level}
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
            temperature=0.25,
            max_tokens=2500,
            timeout=60
        )
        txt = resp.choices[0].message.content
        if "```json" in txt:
            txt = txt.split("```json")[1].split("```")[0].strip()
        elif "```" in txt:
            txt = txt.split("```")[1].split("```")[0].strip()
        return json.loads(txt)
    
    def generate_passage(self, topic, difficulty_level, word_count_min, word_count_max, user_interests, age=None, grade_band=None):
        """Generate educational passage using GPT-4 with dynamic word count"""
        
        # Calculate target from range
        import random
        target_words = (word_count_min + word_count_max) // 2
        
        # Build enhanced prompt
        prompt = f"""
        Generate an engaging reading passage for a student:
        
        Student Profile:
        - Age: {age} years old
        - Grade Level: {grade_band}
        - Reading Difficulty: {difficulty_level}
        - Interests: {', '.join(user_interests) if user_interests else 'general topics'}
        - Topic: {topic}
        
        Requirements:
        - Word count: approximately {target_words} words
        - Use age-appropriate vocabulary for a {age}-year-old in {grade_band}
        - Make it engaging and relatable to their interests
        - Include vivid details and clear structure
        - Difficulty level: {difficulty_level}
        
        The passage should be educational but fun, matching their grade level expectations.
        """
        
        # Add after line 69
        cultural_context = self._get_cultural_context_guidance(age, grade_band)
        
        # Include in prompt
        prompt += f"""
        
        CULTURAL CONTEXT FOR THIS AGE/GRADE:
        Settings to use: {', '.join(cultural_context['settings'])}
        Characters to include: {', '.join(cultural_context['characters'])}
        Appropriate themes: {', '.join(cultural_context['themes'])}
        What to avoid: {', '.join(cultural_context['avoid'])}
        """
        
        # ========== UPDATED PROMPT WITH COMPREHENSIVE VOCABULARY ==========
        prompt = f"""Write a SHORT STORY (narrative) about {topic} featuring African American characters.

        Student Profile:
        - Age: {age} years old
        - Grade Level: {grade_band}
        - Reading Difficulty: {difficulty_level}
        - Interests: {', '.join(user_interests) if user_interests else 'general topics'}
        
        CULTURAL CONTEXT:
        - Set in an urban community (city neighborhood, public spaces)
        - Feature authentic Black characters with realistic names
        - Show positive community interactions and support
        - Include cultural elements (music, food, celebrations, traditions)
        - Demonstrate resilience and success
        
        HARD WORD COUNT RULE:
        - The "content" field MUST be EXACTLY {target_words} words.
        - Count words by splitting on spaces.
        - Before you respond, self-check the word count and adjust until it is exactly {target_words}.
        
        STORY STRUCTURE:
        - Character: African American protagonist facing a relatable challenge
        - Setting: Urban neighborhood, school, community center, park, library, etc.
        - Plot: Beginning → problem/challenge → resolution through creativity/effort/community
        - Include at least one line of dialogue
        - Show positive outcome and growth
        - NO criminal justice, violence, or trauma content
        - Focus on strengths, not struggles with poverty
        
        TOPIC FOCUS: {topic}
        - Stay focused on this topic only
        - Make it educational but engaging
        - Connect to their real-world experiences
        - Show how the topic matters in their community
        
        AGE-APPROPRIATE VOCABULARY:
        - Use {difficulty_level} level vocabulary
        - Include challenging academic words they can learn
        - Define any cultural references they might not know
        
        Return your response as a JSON object:
        {{
            "title": "Engaging title about {topic}",
            "content": "The full story (EXACTLY {target_words} words)",
            "key_concepts": ["concept1", "concept2", "concept3"],
            "vocabulary_words": [
                {{"word": "challenging_word1", "definition": "simple, clear definition"}},
                {{"word": "challenging_word2", "definition": "simple, clear definition"}},
                ... (minimum 5-10 words based on difficulty level)
            ]
        }}
        
        REMINDER: This story should feel real and relatable to an African American student from an urban community. Focus on positive experiences, community strength, and educational growth."""
        
        try:
            # NEW API SYNTAX
            response = self.client.chat.completions.create(
                model="gpt-4-turbo-preview",
                messages=[
                    {
                        "role": "system",
                        "content": """You are an expert educational content creator specializing in culturally relevant, trauma-informed content for African American students from underserved communities.
                        
                        CRITICAL CULTURAL GUIDELINES:
                        1. **Authentic Representation**: 
                           - Use diverse Black characters with authentic names and experiences
                           - Include positive role models from the community (teachers, coaches, entrepreneurs, artists)
                           - Show families with different structures (single parents, grandparents, extended family)
                           - Represent urban/neighborhood settings authentically and positively
                        
                        2. **TRAUMA-INFORMED - AVOID**:
                           - Police encounters or criminal justice system references
                           - Violence, gangs, or crime as plot elements
                           - Poverty as a defining characteristic (it's context, not identity)
                           - Deficit narratives or stereotypes
                           - Drug-related content
                        
                        3. **EMPOWERING THEMES**:
                           - Community strength and mutual support
                           - Overcoming challenges through creativity and resilience
                           - Cultural pride and heritage
                           - Educational and career success
                           - Arts, music, sports as pathways
                           - Entrepreneurship and innovation
                           - STEM and creative fields
                        
                        4. **RELATABLE CONTEXTS**:
                           - Urban neighborhoods, public transportation, corner stores
                           - Community centers, parks, libraries, churches
                           - Barbershops, hair salons, family gatherings
                           - Basketball courts, community gardens
                           - Local heroes and mentors
                           - Music (hip-hop, R&B), art, fashion, sports culture
                        
                        5. **VOCABULARY EXTRACTION**:
                           Extract ALL challenging words from your passage. A good passage should have AT LEAST 5-10 vocabulary words.
                           
                           Examples by level:
                           - Elementary: "ecosystem", "gravity", "nutrient", "habitat", "diverse"
                           - Intermediate: "phenomenon", "inevitable", "perspective", "substantial", "comprehensive"  
                           - High School: "culmination", "juxtaposition", "paradigm", "synthesis", "nuance"
                           - Adult: "epistemology", "hegemony", "empirical", "ubiquitous", "pragmatic"
                        
                        STORY REQUIREMENTS:
                        - Focus on ONE topic at a time
                        - Include a character, setting, and plot (beginning → problem → resolution)
                        - Make it engaging and age-appropriate
                        - Show positive outcomes through effort, creativity, or community support
                        - Include at least one line of dialogue
                        - NO articles, definitions, or lectures - tell a STORY"""
                    },
                    {"role": "user", "content": prompt}
                ],
                temperature=0.35,
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

            # Analyze readability
            readability = analyze_readability(passage_data['content'])
            wc = readability['word_count']

            # If out of range, do up to 2 rewrite passes (MUCH faster than 6 new generations)
            if wc < word_count_min or wc > word_count_max:
                print(f"⚠️ Out of range on first draft: wc={wc}. Rewriting to fit...")

                for rewrite_attempt in range(1, 3):  # 2 rewrites max
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
                    wc = readability['word_count']
                    print(f"✍️ Rewrite attempt {rewrite_attempt}: wc={wc}")

                    if word_count_min <= wc <= word_count_max:
                        break

            # (Optional but recommended) Re-check vocab after rewrite because rewrite often returns fewer vocab words
            vocab_words = passage_data.get('vocabulary_words', [])
            vocab_count = len(vocab_words)
            required_min = min_vocab.get(difficulty_level, 5)

            if vocab_count < required_min:
                passage_data['vocabulary_words'] = self._extract_additional_vocabulary(
                    passage_data['content'],
                    vocab_words,
                    difficulty_level,
                    required_min
                )
            
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