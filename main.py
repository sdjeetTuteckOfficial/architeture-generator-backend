from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, List, Optional, Any, TypedDict, Annotated
import os
import json
import re
from datetime import datetime
import asyncio
import uvicorn

# Import your existing classes and functions
from langgraph.graph import StateGraph, END
from langgraph.graph.message import add_messages
from langchain_core.messages import HumanMessage, AIMessage, SystemMessage
from langchain_google_genai import ChatGoogleGenerativeAI
from langchain_core.tools import tool
from langchain_core.prompts import ChatPromptTemplate

from dotenv import load_dotenv

load_dotenv()  # take environment variables

# Set up Gemini API key
google_api_key = os.getenv("GOOGLE_API_KEY")
if not google_api_key:
    raise ValueError("GOOGLE_API_KEY environment variable not set. Please set it to your Gemini API key.")
os.environ["GOOGLE_API_KEY"] = google_api_key

app = FastAPI(title="Dynamic Architecture Generator API", version="1.0.0")

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:3000"],  # React dev server
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Pydantic models for API
class ProjectRequest(BaseModel):
    description: str

class AnalysisResponse(BaseModel):
    project_domain: str
    completeness_score: float
    needs_clarification: bool
    clarification_questions: List[str]
    extracted_context: Dict[str, Any]

# New Pydantic model to correctly handle the request body for /generate-architecture
class ArchitectureRequest(BaseModel):
    description: str
    context: Dict[str, Any]
    clarification_responses: Optional[Dict[str, str]] = None

class ArchitectureResponse(BaseModel):
    architecture: str
    domain: str
    timestamp: str

# Copy your existing AgentState and tools here
class AgentState(TypedDict):
    """State that gets passed between agents"""
    messages: Annotated[List, add_messages]
    original_prompt: str
    extracted_context: Dict[str, Any]
    user_responses: Dict[str, str]
    needs_clarification: bool
    clarification_questions: List[str]
    architecture_generated: bool
    final_architecture: str
    current_agent: str
    project_domain: str
    completeness_score: float

# Initialize Gemini model
llm = ChatGoogleGenerativeAI(
    model="gemini-2.0-flash",
    temperature=0.7,
    max_tokens=4000
)

@tool
def analyze_prompt_context(prompt: str) -> Dict[str, Any]:
    """Dynamically analyze any prompt to extract context and domain"""
    
    analysis_prompt = f"""
    Analyze the following user prompt and extract key information in JSON format:
    
    User Prompt: "{prompt}"
    
    Please provide a JSON response with the following structure:
    {{
        "project_domain": "the main domain/type of project (e.g., web application, mobile app, AI system, IoT platform, etc.)",
        "project_purpose": "what the system is supposed to do",
        "scale_indicators": ["any mentions of scale, users, performance requirements"],
        "technical_mentions": ["any specific technologies, frameworks, or tools mentioned"],
        "business_requirements": ["any business-related requirements mentioned"],
        "functional_requirements": ["specific features or functionalities mentioned"],
        "non_functional_requirements": ["performance, security, scalability, etc. requirements"],
        "constraints": ["budget, timeline, technology constraints mentioned"],
        "stakeholders": ["target users, user types, or stakeholders mentioned"],
        "integration_needs": ["external systems or APIs mentioned"],
        "deployment_environment": ["cloud, on-premise, hybrid, specific platforms mentioned"],
        "completeness_indicators": {{
            "has_clear_purpose": true/false,
            "has_scale_info": true/false,
            "has_technical_details": true/false,
            "has_constraints": true/false,
            "word_count": number,
            "detail_level": "high/medium/low"
        }}
    }}
    
    Be thorough but concise. Extract actual mentions, don't make assumptions.
    """
    
    try:
        response = llm.invoke([HumanMessage(content=analysis_prompt)])
        content = response.content
        
        json_match = re.search(r'\{.*\}', content, re.DOTALL)
        if json_match:
            return json.loads(json_match.group())
        else:
            return {
                "project_domain": "general software system",
                "project_purpose": "not clearly specified",
                "completeness_indicators": {"detail_level": "low", "word_count": len(prompt.split())}
            }
    except Exception as e:
        print(f"Error in context analysis: {e}")
        return {
            "project_domain": "general software system",
            "project_purpose": "not clearly specified",
            "completeness_indicators": {"detail_level": "low", "word_count": len(prompt.split())}
        }

@tool
def calculate_completeness_score(context: Dict[str, Any]) -> float:
    """Calculate how complete the user prompt is (0.0 to 1.0)"""
    
    score = 0.0
    indicators = context.get("completeness_indicators", {})
    
    word_count = indicators.get("word_count", 0)
    if word_count > 100:
        score += 0.2
    elif word_count > 50:
        score += 0.15
    elif word_count > 20:
        score += 0.1
    
    if indicators.get("has_clear_purpose"):
        score += 0.2
    elif context.get("project_purpose") != "not clearly specified":
        score += 0.1
    
    if len(context.get("technical_mentions", [])) > 0:
        score += 0.15
    
    func_reqs = len(context.get("functional_requirements", []))
    non_func_reqs = len(context.get("non_functional_requirements", []))
    if func_reqs > 2 or non_func_reqs > 2:
        score += 0.15
    elif func_reqs > 0 or non_func_reqs > 0:
        score += 0.1
    
    if len(context.get("constraints", [])) > 0:
        score += 0.1
    
    if len(context.get("scale_indicators", [])) > 0:
        score += 0.1
    
    if len(context.get("stakeholders", [])) > 0:
        score += 0.1
    
    return min(score, 1.0)

@tool
def generate_dynamic_questions(context: Dict[str, Any], completeness_score: float) -> List[str]:
    """Generate relevant clarification questions based on any domain"""
    
    questions_prompt = f"""
    Based on the following project analysis, generate 3-6 targeted clarification questions to gather missing critical information for architecture design.
    
    Project Analysis:
    {json.dumps(context, indent=2)}
    
    Completeness Score: {completeness_score:.2f} (0.0 = very incomplete, 1.0 = very complete)
    
    Generate questions that would help create a comprehensive architecture. Focus on:
    1. Missing critical business/functional requirements
    2. Technical constraints and preferences  
    3. Scale and performance expectations
    4. Integration and deployment needs
    5. Budget and timeline constraints
    
    Return ONLY a JSON array of question strings:
    ["question 1", "question 2", ...]
    
    Make questions specific to the project domain and avoid generic questions.
    """
    
    try:
        response = llm.invoke([HumanMessage(content=questions_prompt)])
        content = response.content
        
        json_match = re.search(r'\[.*\]', content, re.DOTALL)
        if json_match:
            return json.loads(json_match.group())
        else:
            domain = context.get("project_domain", "system")
            return [
                f"What are the main functional requirements for your {domain}?",
                "What is the expected scale (number of users, data volume, etc.)?",
                "Do you have any specific technology preferences or constraints?",
                "What is your budget and timeline for this project?",
                "Are there any external systems you need to integrate with?"
            ]
    except Exception as e:
        print(f"Error generating questions: {e}")
        return [
            "What are the main functional requirements for your system?",
            "What is the expected scale and performance requirements?",
            "Do you have any technology preferences or constraints?"
        ]

# API Routes
@app.post("/analyze", response_model=AnalysisResponse)
async def analyze_project(request: ProjectRequest):
    """Analyze project description and return initial assessment"""
    try:
        # Corrected tool invocation
        context = analyze_prompt_context.invoke({'prompt': request.description})
        completeness_score = calculate_completeness_score.invoke({'context': context})
        needs_clarification = completeness_score < 0.6
        
        clarification_questions = []
        if needs_clarification:
            # Corrected tool invocation
            clarification_questions = generate_dynamic_questions.invoke({'context': context, 'completeness_score': completeness_score})
        
        return AnalysisResponse(
            project_domain=context.get("project_domain", "general system"),
            completeness_score=completeness_score,
            needs_clarification=needs_clarification,
            clarification_questions=clarification_questions,
            extracted_context=context
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error analyzing project: {str(e)}")

@app.post("/generate-architecture", response_model=ArchitectureResponse)
async def generate_architecture(
    request: ArchitectureRequest # Changed from individual parameters to a Pydantic model
):
    """Generate detailed architecture based on description and clarifications"""
    try:
        domain = request.context.get("project_domain", "general system")
        user_responses = request.clarification_responses or {}
        
        architecture_prompt = f"""
        You are an expert software architect specializing in {domain} projects. 
        Generate a comprehensive, detailed architecture document based on the requirements below.
        
        ORIGINAL REQUEST:
        {request.description}
        
        EXTRACTED CONTEXT:
        {json.dumps(request.context, indent=2)}
        
        ADDITIONAL USER RESPONSES:
        {json.dumps(user_responses, indent=2)}
        
        Please create a detailed architecture document that includes:
        
        1. **Executive Summary & Project Overview**
        2. **System Architecture Overview** (high-level design)
        3. **Technology Stack Recommendations** (with justifications)
        4. **System Components & Services** (detailed breakdown)
        5. **Data Architecture & Storage Strategy**
        6. **Security Architecture & Compliance**
        7. **Scalability & Performance Strategy**
        8. **Integration Architecture** (APIs, third-party services)
        9. **Deployment & Infrastructure Strategy**
        10. **Monitoring, Logging & Observability**
        11. **Development & DevOps Strategy**
        12. **Risk Assessment & Mitigation**
        13. **Cost Estimation & Optimization**
        14. **Implementation Roadmap & Phases**
        15. **Maintenance & Evolution Strategy**
        
        Make your response:
        - Specific to the {domain} domain
        - Technically detailed and actionable
        - Include specific technology recommendations
        - Address the specific requirements mentioned
        - Provide reasoning for architectural decisions
        - Include diagrams descriptions where helpful
        - Consider industry best practices for {domain}
        
        Format the response with clear headers and detailed explanations for each section.
        """
        
        response = llm.invoke([HumanMessage(content=architecture_prompt)])
        architecture_content = response.content
        
        return ArchitectureResponse(
            architecture=architecture_content,
            domain=domain,
            timestamp=datetime.now().isoformat()
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating architecture: {str(e)}")

@app.get("/")
async def root():
    return {"message": "Dynamic Architecture Generator API is running"}

@app.get("/health")
async def health_check():
    return {"status": "healthy", "timestamp": datetime.now().isoformat()}

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)
