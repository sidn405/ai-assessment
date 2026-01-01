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
    
    def generate_passage(self, topic, difficulty_level, target_words, user_interests):
        """Generate educational passage using GPT-4"""
        
        # Build prompt (same as before)
        prompt = f"""Create an educational reading passage with the following specifications:

Topic: {topic}
Difficulty Level: {difficulty_level}
Target Length: {target_words} words
User Interests: {', '.join(user_interests)}

Generate a passage that is engaging, age-appropriate, and educational.

Return your response as a JSON object with this exact structure:
{{
    "title": "Engaging title for the passage",
    "content": "The full passage text (approximately {target_words} words)",
    "key_concepts": ["concept1", "concept2", "concept3"],
    "vocabulary_words": [
        {{"word": "word1", "definition": "simple definition"}},
        {{"word": "word2", "definition": "simple definition"}}
    ]
}}"""

        try:
            # NEW API SYNTAX
            response = self.client.chat.completions.create(
                model="gpt-4-turbo-preview",  # Use your working model
                messages=[
                    {
                        "role": "system",
                        "content": "You are an expert educational content creator specializing in literacy development."
                    },
                    {"role": "user", "content": prompt}
                ],
                temperature=0.8,
                max_tokens=1500,
                timeout=60
            )
            
            # NEW API - Different response structure
            content = response.choices[0].message.content
            
            # Extract JSON (same as before)
            if "```json" in content:
                content = content.split("```json")[1].split("```")[0].strip()
            elif "```" in content:
                content = content.split("```")[1].split("```")[0].strip()
            
            passage_data = json.loads(content)
            
            # Analyze readability
            from readability import analyze_readability
            readability = analyze_readability(passage_data['content'])
            
            # Add metadata
            passage_data.update({
                "source": "AI",
                "topic_tags": self._extract_topics(topic, user_interests),
                "word_count": readability['word_count'],
                "readability_score": readability['flesch_kincaid_grade'],
                "flesch_ease": readability['flesch_reading_ease'],
                "difficulty_level": difficulty_level,
                "estimated_minutes": readability['estimated_minutes'],
                "actual_difficulty": readability['difficulty_level'],
                "grade_band": readability['grade_band']
            })
            
            return passage_data
            
        except Exception as e:
            print(f"Error generating passage: {e}")
            import traceback
            traceback.print_exc()
            # Return a fallback passage
            return self._get_fallback_passage(topic, difficulty_level)
    
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
    
    def _get_fallback_questions(self):
        """Return basic fallback questions"""
        return [
            {
                "question": "What is the main topic of this passage?",
                "type": "main_idea",
                "options": ["The topic discussed", "Something else", "Another topic", "Different subject"],
                "correct_answer": "The topic discussed",
                "explanation": "The passage focuses on this main topic.",
                "difficulty": 1
            }
        ]

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