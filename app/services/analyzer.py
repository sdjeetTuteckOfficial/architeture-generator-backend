import json
import re
from typing import Dict, List, Any
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.messages import HumanMessage
from dotenv import load_dotenv
import os

load_dotenv()

# Initialize Gemini
google_api_key = os.getenv("GOOGLE_API_KEY")
if not google_api_key:
    raise ValueError("GOOGLE_API_KEY environment variable not set")
os.environ["GOOGLE_API_KEY"] = google_api_key
llm = ChatGoogleGenerativeAI(model="gemini-2.0-flash", temperature=0.7, max_tokens=4000)

class ArchitectureAnalyzer:
    """Core analyzer for extracting context from project descriptions"""

    def analyze_context(self, prompt: str) -> Dict[str, Any]:
        """Extract structured context from user prompt"""
        analysis_prompt = f"""
        Analyze this project description and extract key information in JSON format:
        
        "{prompt}"
        
        Extract all relevant details and return JSON with this structure:
        {{
            "project_domain": "primary domain (e-commerce, social media, fintech, healthcare, education, enterprise, etc.)",
            "project_type": "specific system type (web app, mobile app, API platform, data pipeline, AI system, etc.)",
            "project_scale": "estimated scale (startup/small/medium/large/enterprise)",
            "user_types": ["different user categories mentioned"],
            "cloud_services": ["azure, aws, gcp, etc. if specified"],
            "core_features": ["main features and functionalities"],
            "technical_stack": ["specific technologies, frameworks, languages mentioned"],
            "data_requirements": ["data types, storage needs, processing requirements"],
            "integration_needs": ["external services, APIs, third-party systems"],
            "performance_requirements": ["speed, throughput, latency requirements"],
            "security_requirements": ["authentication, authorization, compliance needs"],
            "scalability_needs": ["growth expectations, scaling requirements"],
            "deployment_environment": ["cloud providers, infrastructure preferences"],
            "business_constraints": ["budget, timeline, compliance requirements"],
            "industry_specific": ["domain-specific requirements like HIPAA, PCI-DSS, etc."],
            "complexity_indicators": {{
                "feature_count": "estimated number of major features",
                "integration_complexity": "low/medium/high based on external dependencies",
                "data_complexity": "simple/moderate/complex based on data requirements",
                "user_complexity": "single/multiple user types and permissions"
            }},
            "architectural_patterns": ["microservices, monolith, serverless, event-driven patterns suggested"],
            "estimated_team_size": "suggested team size based on complexity",
            "development_timeline": "estimated timeline based on scope"
        }}
        
        Analyze the prompt thoroughly and extract specific details. If something isn't mentioned, use empty arrays or "not specified".
        Consider the complexity and suggest appropriate architectural approaches.
        
        Be precise and extract only what's explicitly mentioned.
        """
        
        try:
            response = llm.invoke([HumanMessage(content=analysis_prompt)])
            json_match = re.search(r'\{.*\}', response.content, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
        except Exception as e:
            print(f"Context analysis error: {e}")
        
        return {
            "project_domain": "web application",
            "project_type": "custom software system",
            "completeness_score": 0.3
        }

    def calculate_completeness(self, context: Dict[str, Any], prompt: str) -> float:
        """Calculate how complete the requirements are"""
        score = 0.0
        word_count = len(prompt.split())
        
        # Word count scoring
        if word_count > 100: score += 0.2
        elif word_count > 50: score += 0.15
        elif word_count > 20: score += 0.1
        
        # Content scoring
        if len(context.get("technologies", [])) > 0: score += 0.15
        if len(context.get("functional_requirements", [])) > 2: score += 0.15
        if len(context.get("non_functional_requirements", [])) > 1: score += 0.15
        if len(context.get("business_requirements", [])) > 0: score += 0.1
        if len(context.get("integrations", [])) > 0: score += 0.1
        if len(context.get("scale_indicators", [])) > 0: score += 0.15
        
        return min(score, 1.0)
    
    def generate_questions(self, context: Dict[str, Any], completeness: float) -> List[str]:
        """Generate targeted clarification questions"""
        domain = context.get("project_domain", "system")
        
        questions_prompt = f"""
        Based on this project analysis for a {domain}, generate 4-6 specific clarification questions:
        
        Context: {json.dumps(context, indent=2)}
        Completeness: {completeness:.2f}
        
        Focus on missing critical information for architecture design.
        Return a JSON array of questions: ["question1", "question2", ...]
        """
        
        try:
            response = llm.invoke([HumanMessage(content=questions_prompt)])
            json_match = re.search(r'\[.*\]', response.content, re.DOTALL)
            if json_match:
                return json.loads(json_match.group())
        except Exception as e:
            print(f"Question generation error: {e}")
        
        return [
            f"What are the key functional requirements for your {domain}?",
            "What is the expected user scale and performance requirements?",
            "Do you have specific technology preferences or constraints?",
            "What external systems need integration?",
            "What are your deployment and infrastructure preferences?"
        ]