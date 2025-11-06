"""
Gemini Agent Module
Handles all Gemini API interactions for question generation and content analysis.
"""

import os
import json
import google.generativeai as genai
from typing import Dict, Any, Optional, List
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

# Model constants
MODEL_GEMINI_FLASH = "models/gemini-2.5-flash"
MODEL_GEMINI_PRO = "models/gemini-2.5-pro"
MODEL_GEMINI_DEEP_THINK = "models/gemini-2.5-pro"  # Use Pro as Deep Think may not be available via API

class GeminiAgent:
    """
    Gemini Agent for generating educational content.
    Handles question generation, content analysis, and other AI-powered tasks.
    """
    
    def __init__(self, model_name: str = MODEL_GEMINI_PRO):
        """
        Initialize the Gemini Agent.
        
        Args:
            model_name: The Gemini model to use (default: gemini-2.5-pro)
        """
        self.api_key = os.getenv("GEMINI_API_KEY")
        if not self.api_key:
            raise ValueError("GEMINI_API_KEY not found in environment variables")
        
        genai.configure(api_key=self.api_key)
        self.model_name = model_name
        self.model = genai.GenerativeModel(model_name)
        print(f"✅ Gemini Agent initialized with model: {model_name}")
    
    def generate_questions(
        self,
        content: str,
        num_questions: int = 100,
        sections: Optional[List[Dict[str, Any]]] = None,
        **kwargs
    ) -> str:
        """
        Generate multiple choice questions from provided content.
        
        Args:
            content: The source material to generate questions from
            num_questions: Number of questions to generate
            sections: Optional list of section metadata for organizing questions
            **kwargs: Additional generation parameters
            
        Returns:
            Generated questions as a formatted string
        """
        temperature = kwargs.get("temperature", 0.1)
        max_tokens = kwargs.get("max_tokens", 16384)
        
        # Build the prompt
        prompt = self._build_question_prompt(content, num_questions, sections)
        
        # Configure generation settings
        generation_config = genai.types.GenerationConfig(
            temperature=temperature,
            top_p=0.8,
            top_k=40,
            max_output_tokens=max_tokens,
        )
        
        # Safety settings
        safety_settings = [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
        ]
        
        try:
            print(f"🤖 Generating {num_questions} questions with Gemini {self.model_name}...")
            response = self.model.generate_content(
                prompt,
                generation_config=generation_config,
                safety_settings=safety_settings
            )
            return response.text
        except Exception as e:
            error_str = str(e)
            if "429" in error_str or "quota" in error_str.lower():
                raise Exception(f"API quota exceeded: {error_str}")
            raise Exception(f"Gemini API error: {error_str}")
    
    def _build_question_prompt(
        self,
        content: str,
        num_questions: int,
        sections: Optional[List[Dict[str, Any]]] = None
    ) -> str:
        """
        Build the prompt for question generation.
        
        Args:
            content: Source material content
            num_questions: Number of questions to generate
            sections: Optional section metadata
            
        Returns:
            Formatted prompt string
        """
        # Limit content size to avoid token limits (200k chars ~50k tokens)
        content_preview = content[:200000]
        
        prompt = f"""You are an expert educational assessment designer specializing in medical education for CRNA students.

**SOURCE MATERIAL FROM ALL BARASH SECTIONS:**
{content_preview}  

**YOUR TASK:**
Perform COMPREHENSIVE DEEP RESEARCH across all provided sections and create exactly {num_questions} multiple choice questions following these guidelines:

**CRITICAL RULES:**
1. Use ONLY information from the provided section text above
2. DO NOT add information from your training data
3. All questions must be traceable to specific content in the sections
"""
        
        if sections:
            prompt += "4. Distribute questions across all sections proportionally:\n"
            for section in sections:
                prompt += f"   - Section {section.get('section_num', '?')}: ~{num_questions // len(sections)} questions\n"
            prompt += "5. Follow the exact format shown below\n\n"
        else:
            prompt += "4. Follow the exact format shown below\n\n"
        
        prompt += """**QUESTION DISTRIBUTION PER SECTION:**
- 30% Foundational/Recall (Bloom's: Remember/Understand)
- 50% Application/Analysis (Bloom's: Apply/Analyze)  
- 20% Higher-Order Thinking (Bloom's: Evaluate/Create)

**FORMAT FOR EACH QUESTION:**
```
**[Number]. [Clear, specific question stem from section content]**

**[Section X: Section Name]**

A) [Plausible but incorrect option]

B) [Plausible but incorrect option]

C) [Correct answer]

**Correct Answer:** C

**Explanation:** [2-3 sentences explaining why this is correct, citing the specific section and chapter]
```

**QUALITY REQUIREMENTS:**
- Question stems must be clear and specific
- All distractors must be plausible (someone with partial knowledge might choose them)
- Correct answer must be indisputable based on the section content
- Explanations must cite the specific section and chapter
- Cover breadth of ALL sections proportionally
- Test understanding across all domains of anesthesia practice
- Questions should demonstrate mastery across Basic Science, Cardiac, Pharmacology, Assessment, and Management

**SECTION BREAKDOWN:**
Please organize questions by section, clearly labeling which section each question comes from.

Generate all {num_questions} questions now in markdown format, organized by section."""
        
        return prompt
    
    def analyze_content(
        self,
        content: str,
        analysis_type: str = "summary",
        **kwargs
    ) -> str:
        """
        Analyze content for various purposes.
        
        Args:
            content: Content to analyze
            analysis_type: Type of analysis (summary, key_points, concepts, etc.)
            **kwargs: Additional parameters
            
        Returns:
            Analysis result as string
        """
        prompts = {
            "summary": "Summarize the key points from the following medical content:",
            "key_points": "Extract the 10 most important key points from this content:",
            "concepts": "Identify and explain the main medical concepts discussed:",
        }
        
        prompt_prefix = prompts.get(analysis_type, prompts["summary"])
        prompt = f"{prompt_prefix}\n\n{content[:50000]}"
        
        try:
            response = self.model.generate_content(prompt)
            return response.text
        except Exception as e:
            raise Exception(f"Content analysis failed: {str(e)}")
    
    def generate_explanation(
        self,
        question: str,
        answer: str,
        context: Optional[str] = None
    ) -> str:
        """
        Generate a detailed explanation for a question and answer.
        
        Args:
            question: The question text
            answer: The correct answer
            context: Optional context from source material
            
        Returns:
            Detailed explanation
        """
        prompt = f"""Generate a detailed explanation for this medical question:

Question: {question}

Correct Answer: {answer}

{f'Context from source material: {context[:2000]}' if context else ''}

Provide a 2-3 sentence explanation that:
1. Explains why this answer is correct
2. References specific concepts from the source material
3. Helps CRNA students understand the underlying principles"""
        
        try:
            response = self.model.generate_content(prompt)
            return response.text
        except Exception as e:
            raise Exception(f"Explanation generation failed: {str(e)}")
    
    def generate_scenario(
        self,
        case: Dict[str, Any],
        patient: Dict[str, Any],
        medical_content: str,
        **kwargs
    ) -> Dict[str, Any]:
        """
        Generate a clinical scenario with 2 decision options based on case, patient, and medical content.
        
        Args:
            case: Case information from cases.json
            patient: Patient information from patient_templates.json
            medical_content: Relevant medical content from Vector Search
            **kwargs: Additional generation parameters
            
        Returns:
            Dictionary with scenario, options, and analysis
        """
        temperature = kwargs.get("temperature", 0.7)
        max_tokens = kwargs.get("max_tokens", 8192)
        
        # Build patient summary
        patient_summary = f"""
Patient: {patient.get('full_name', 'Patient')}
Age: {patient.get('age', 'Unknown')} years
Weight: {patient.get('weight', {}).get('kg', 'Unknown')} kg ({patient.get('weight', {}).get('lbs', 'Unknown')} lbs)
Comorbidities: {', '.join(patient.get('comorbidities', []))}
Health Traits: {', '.join(patient.get('health_traits', []))}
Personality: {patient.get('personality', 'Standard')}
"""
        
        # Build case summary
        case_summary = f"""
Case: {case.get('name', 'Surgical Procedure')}
Description: {case.get('description', '')}
Keywords: {', '.join(case.get('keywords', []))}
"""
        
        # Limit medical content size
        medical_content_preview = medical_content[:30000]
        
        # Get student context if provided
        student_context = kwargs.get("student_context", "")
        
        prompt = f"""You are an expert CRNA clinical scenario designer. Create a realistic clinical scenario based on the following information:

**PATIENT INFORMATION:**
{patient_summary}

**SURGICAL CASE:**
{case_summary}

{student_context if student_context else ''}

**MEDICAL CONTENT FROM BARASH TEXTBOOK:**
{medical_content_preview}

**YOUR TASK:**
Create a clinical scenario with TWO decision options for the CRNA. The scenario should:
1. Present a realistic clinical situation involving this patient and case
2. Present a decision point where the CRNA must choose between two approaches
3. Both options should be plausible and defensible
4. Base all information on the provided medical content from Barash
5. Make it educational and challenging for CRNA students

**FORMAT:**
```json
{{
    "scenario": "Detailed scenario description presenting the clinical situation and decision point",
    "option_a": {{
        "title": "Brief title for option A",
        "description": "Detailed description of this approach and rationale",
        "considerations": ["Consideration 1", "Consideration 2", "Consideration 3"]
    }},
    "option_b": {{
        "title": "Brief title for option B",
        "description": "Detailed description of this approach and rationale",
        "considerations": ["Consideration 1", "Consideration 2", "Consideration 3"]
    }},
    "best_answer": {{
        "option": "A" or "B",
        "rationale": "Comprehensive explanation (3-5 sentences) explaining why this is the best answer, considering patient factors, risks, benefits, evidence-based practice, and clinical guidelines from Barash"
    }},
    "learning_points": [
        "Key learning point 1",
        "Key learning point 2",
        "Key learning point 3"
    ],
    "references": "References to specific Barash sections/chapters used"
}}
```

Generate the scenario now in valid JSON format."""
        
        # Configure generation settings
        generation_config = genai.types.GenerationConfig(
            temperature=temperature,
            top_p=0.9,
            top_k=40,
            max_output_tokens=max_tokens,
            response_mime_type="application/json"
        )
        
        # Safety settings
        safety_settings = [
            {"category": "HARM_CATEGORY_HARASSMENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
            {"category": "HARM_CATEGORY_HATE_SPEECH", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
            {"category": "HARM_CATEGORY_SEXUALLY_EXPLICIT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
            {"category": "HARM_CATEGORY_DANGEROUS_CONTENT", "threshold": "BLOCK_MEDIUM_AND_ABOVE"},
        ]
        
        try:
            print(f"🤖 Generating scenario with Gemini {self.model_name}...")
            response = self.model.generate_content(
                prompt,
                generation_config=generation_config,
                safety_settings=safety_settings
            )
            
            # Parse JSON response
            scenario_data = json.loads(response.text)
            
            # Add metadata
            scenario_data['case'] = {
                'name': case.get('name'),
                'code': case.get('code'),
                'description': case.get('description')
            }
            scenario_data['patient'] = {
                'name': patient.get('full_name'),
                'age': patient.get('age'),
                'categories': patient.get('categories', [])
            }
            
            return scenario_data
        except json.JSONDecodeError as e:
            raise Exception(f"Failed to parse scenario JSON: {e}. Response: {response.text[:500]}")
        except Exception as e:
            error_str = str(e)
            if "429" in error_str or "quota" in error_str.lower():
                raise Exception(f"API quota exceeded: {error_str}")
            raise Exception(f"Gemini API error: {error_str}")


# Convenience function for easy importing
def create_agent(model_name: str = MODEL_GEMINI_PRO) -> GeminiAgent:
    """
    Create a Gemini agent instance.
    
    Args:
        model_name: The model to use
        
    Returns:
        GeminiAgent instance
    """
    return GeminiAgent(model_name=model_name)

