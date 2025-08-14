from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from typing import Dict, List, Optional, Any, TypedDict, Annotated, Union
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
from constants.constants import AWS_AVAILABLE_IMAGES, AZURE_AVAILABLE_IMAGES, local_images
from dotenv import load_dotenv

load_dotenv()  # take environment variables

# Set up Gemini API key
google_api_key = os.getenv("GOOGLE_API_KEY")
if not google_api_key:
    raise ValueError("GOOGLE_API_KEY environment variable not set. Please set it to your Gemini API key.")
os.environ["GOOGLE_API_KEY"] = google_api_key

app = FastAPI(title="Dynamic Architecture Generator API", version="1.0.0")

imageList = AWS_AVAILABLE_IMAGES + AZURE_AVAILABLE_IMAGES + local_images

# Add CORS middleware
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:3000", "http://localhost:5174"],  # React dev server
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

# ReactFlow specific models

class ReactFlowNodeData(BaseModel):
    label: str
    image: Optional[str] = None
class ReactFlowNode(BaseModel):
    id: str
    data: ReactFlowNodeData
    position: Dict[str, float]
    type: Optional[str] = "custom" # Use a default type to keep it simple

class ReactFlowEdge(BaseModel):
    id: str
    source: str
    target: str

class ReactFlowDiagramResponse(BaseModel):
    nodes: List[ReactFlowNode]
    edges: List[ReactFlowEdge]
    metadata: Dict[str, Any]

# Updated request models
class ArchitectureRequest(BaseModel):
    description: str
    context: Optional[Dict[str, Any]] = {}
    clarification_responses: Optional[Dict[str, str]] = None
    diagram_type: str = "architecture"  # "architecture" or "database"

class DatabaseRequest(BaseModel):
    description: str
    context: Optional[Dict[str, Any]] = {}
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

# @tool
# def generate_reactflow_architecture(description: str, context: Dict[str, Any], user_responses: Dict[str, str]) -> Dict[str, Any]:
#     """Generate ReactFlow architecture diagram data"""
    
#     architecture_prompt = f"""
#     You are an expert software architect. Generate a ReactFlow diagram for the following project.
    
#     ORIGINAL REQUEST: {description}
#     CONTEXT: {json.dumps(context, indent=2)}
#     USER RESPONSES: {json.dumps(user_responses, indent=2)}
    
#     Create a ReactFlow diagram with nodes and edges. Return ONLY valid JSON in this exact format:
    
#     {{
#         "nodes": [
#             {{
#                 "id": "unique_id",
#                 "type": "custom",
#                 "position": {{"x": 100, "y": 100}},
#                 "data": {{
#                     "label": "Component Name",
#                     "description": "Component description",
#                     "technology": "React, Node.js, etc.",
#                     "type": "frontend/backend/database/external"
#                 }},
#                 "style": {{
#                     "width": 180,
#                     "height": 120,
#                     "backgroundColor": "#ffffff",
#                     "border": "2px solid #3b82f6",
#                     "borderRadius": 8
#                 }}
#             }}
#         ],
#         "edges": [
#             {{
#                 "id": "edge_id",
#                 "source": "source_node_id",
#                 "target": "target_node_id",
#                 "type": "smoothstep",
#                 "animated": true,
#                 "label": "API calls",
#                 "style": {{
#                     "stroke": "#6366f1",
#                     "strokeWidth": 2
#                 }}
#             }}
#         ]
#     }}
    
#     Guidelines:
#     - Create 4-8 meaningful nodes representing system components
#     - Position nodes in a logical layout (x: 0-800, y: 0-600)
#     - Use different colors for different component types:
#       * Frontend: #3b82f6 (blue)
#       * Backend: #10b981 (green)
#       * Database: #8b5cf6 (purple)
#       * External: #f59e0b (orange)
#     - Connect related components with edges
#     - Make labels descriptive and specific to the project
#     """
    
#     try:
#         response = llm.invoke([HumanMessage(content=architecture_prompt)])
#         content = response.content
        
#         # Extract JSON from response
#         json_match = re.search(r'\{.*\}', content, re.DOTALL)
#         if json_match:
#             diagram_data = json.loads(json_match.group())
#             return diagram_data
#         else:
#             raise ValueError("No valid JSON found in response")
#     except Exception as e:
#         print(f"Error generating ReactFlow architecture: {e}")
#         # Return default architecture
#         return {
#             "nodes": [
#                 {
#                     "id": "frontend",
#                     "type": "custom",
#                     "position": {"x": 100, "y": 100},
#                     "data": {
#                         "label": "Frontend App",
#                         "description": "User interface",
#                         "technology": "React/Vue/Angular",
#                         "type": "frontend"
#                     },
#                     "style": {
#                         "width": 180,
#                         "height": 120,
#                         "backgroundColor": "#ffffff",
#                         "border": "2px solid #3b82f6",
#                         "borderRadius": 8
#                     }
#                 },
#                 {
#                     "id": "backend",
#                     "type": "custom", 
#                     "position": {"x": 400, "y": 100},
#                     "data": {
#                         "label": "Backend API",
#                         "description": "Business logic",
#                         "technology": "Node.js/Python/Java",
#                         "type": "backend"
#                     },
#                     "style": {
#                         "width": 180,
#                         "height": 120,
#                         "backgroundColor": "#ffffff", 
#                         "border": "2px solid #10b981",
#                         "borderRadius": 8
#                     }
#                 },
#                 {
#                     "id": "database",
#                     "type": "custom",
#                     "position": {"x": 400, "y": 300},
#                     "data": {
#                         "label": "Database",
#                         "description": "Data storage",
#                         "technology": "PostgreSQL/MongoDB",
#                         "type": "database"
#                     },
#                     "style": {
#                         "width": 180,
#                         "height": 120,
#                         "backgroundColor": "#ffffff",
#                         "border": "2px solid #8b5cf6", 
#                         "borderRadius": 8
#                     }
#                 }
#             ],
#             "edges": [
#                 {
#                     "id": "frontend-backend",
#                     "source": "frontend",
#                     "target": "backend", 
#                     "type": "smoothstep",
#                     "animated": True,
#                     "label": "API calls",
#                     "style": {"stroke": "#6366f1", "strokeWidth": 2}
#                 },
#                 {
#                     "id": "backend-database",
#                     "source": "backend",
#                     "target": "database",
#                     "type": "smoothstep", 
#                     "animated": True,
#                     "label": "queries",
#                     "style": {"stroke": "#6366f1", "strokeWidth": 2}
#                 }
#             ]
#         }
@tool
def generate_reactflow_architecture(description: str, context: Dict[str, Any], user_responses: Dict[str, str]) -> Dict[str, Any]:
    """Generate ReactFlow architecture diagram data"""
    print("Generating ReactFlow architecture diagram...")
   

    # Construct the new prompt
    architecture_prompt = f"""
    You are an assistant that returns React Flow-compatible architecture diagrams in JSON.

    Your task is to analyze the provided project description and generate a complete and valid JSON object for a React Flow diagram.

    The JSON **must** strictly adhere to the following schema:
    {{
        "nodes": [
            {{
                "id": "unique_id",
                "type": "custom",
                "data": {{ "label": "Component Name", "image": "image_name.png" (optional) }},
                "position": {{ "x": 0, "y": 0 }}
            }}
        ],
        "edges": [
            {{
                "id": "unique_edge_id",
                "source": "source_node_id",
                "target": "target_node_id"
            }}
        ]
    }}

    **IMPORTANT RULES:**
    1.  Nodes must be placed in a logical layout. The 'position' x and y values should be within a reasonable range (e.g., 0-800 for x, 0-600 for y) to avoid overlapping.
    2.  Use the `data.image` field to assign an icon to a node. You can only use the following image names:
        {imageList}
    3.  If a component is not represented by an image in the list, omit the `data.image` field entirely. Do not invent image names.
    4.  Do not create a node for the user prompt itself. Only create nodes for the architectural components.
    5.  Return ONLY the raw JSON object. Do not include any surrounding markdown (like ```json) or explanatory text.

    Now, generate the architecture diagram JSON for the following project description:
    "{description}"
    """

    try:
        response = llm.invoke([HumanMessage(content=architecture_prompt)])
        content = response.content

        # Robustly extract JSON from the response
        json_match = re.search(r'\{.*\}', content, re.DOTALL)
        if json_match:
            diagram_data = json.loads(json_match.group())
            return diagram_data
        else:
            raise ValueError("No valid JSON found in response")
    except Exception as e:
        print(f"Error generating ReactFlow architecture: {e}")
        # Return default architecture to ensure stability
        return {
            "nodes": [{"id": "default", "data": {"label": "Error: Could not generate diagram."}, "position": {"x": 100, "y": 100}}],
            "edges": []
        }
@tool
def generate_reactflow_database(description: str, context: Dict[str, Any], user_responses: Dict[str, str]) -> Dict[str, Any]:
    """Generate ReactFlow database diagram data"""
    
    database_prompt = f"""
    You are an expert database architect. Generate a ReactFlow database diagram for the following project.
    
    ORIGINAL REQUEST: {description}
    CONTEXT: {json.dumps(context, indent=2)}
    USER RESPONSES: {json.dumps(user_responses, indent=2)}
    
    Create a database diagram with tables and relationships. Return ONLY valid JSON in this exact format:
    
    {{
        "nodes": [
            {{
                "id": "table_name",
                "type": "dbTableNode",
                "position": {{"x": 100, "y": 100}},
                "data": {{
                    "tableName": "users",
                    "columns": [
                        {{
                            "name": "id",
                            "type": "INTEGER",
                            "isPrimary": true,
                            "isNullable": false,
                            "isUnique": true
                        }},
                        {{
                            "name": "email",
                            "type": "VARCHAR(255)",
                            "isPrimary": false,
                            "isNullable": false,
                            "isUnique": true
                        }}
                    ],
                    "description": "User accounts table"
                }},
                "style": {{
                    "width": 250,
                    "minHeight": 150,
                    "backgroundColor": "#ffffff",
                    "border": "2px solid #8b5cf6",
                    "borderRadius": 8
                }}
            }}
        ],
        "edges": [
            {{
                "id": "relationship_id",
                "source": "source_table",
                "target": "target_table",
                "type": "straight",
                "label": "FK",
                "style": {{
                    "stroke": "#8b5cf6",
                    "strokeWidth": 2
                }}
            }}
        ]
    }}
    
    Guidelines:
    - Create 3-6 tables based on the project requirements
    - Each table should have realistic columns with proper data types
    - Include primary keys, foreign keys, and common fields
    - Position tables in a logical layout
    - Connect related tables with foreign key relationships
    - Use descriptive table and column names
    """
    
    try:
        response = llm.invoke([HumanMessage(content=database_prompt)])
        content = response.content
        
        # Extract JSON from response
        json_match = re.search(r'\{.*\}', content, re.DOTALL)
        if json_match:
            diagram_data = json.loads(json_match.group())
            return diagram_data
        else:
            raise ValueError("No valid JSON found in response")
    except Exception as e:
        print(f"Error generating ReactFlow database: {e}")
        # Return default database schema
        return {
            "nodes": [
                {
                    "id": "users",
                    "type": "dbTableNode",
                    "position": {"x": 100, "y": 100},
                    "data": {
                        "tableName": "users",
                        "columns": [
                            {"name": "id", "type": "INTEGER", "isPrimary": True, "isNullable": False, "isUnique": True},
                            {"name": "email", "type": "VARCHAR(255)", "isPrimary": False, "isNullable": False, "isUnique": True},
                            {"name": "password", "type": "VARCHAR(255)", "isPrimary": False, "isNullable": False, "isUnique": False},
                            {"name": "created_at", "type": "TIMESTAMP", "isPrimary": False, "isNullable": False, "isUnique": False}
                        ],
                        "description": "User accounts"
                    },
                    "style": {"width": 250, "minHeight": 150, "backgroundColor": "#ffffff", "border": "2px solid #8b5cf6", "borderRadius": 8}
                }
            ],
            "edges": []
        }

# API Routes
@app.post("/analyze", response_model=AnalysisResponse)
async def analyze_project(request: ProjectRequest):
    """Analyze project description and return initial assessment"""
    try:
        context = analyze_prompt_context.invoke({'prompt': request.description})
        completeness_score = calculate_completeness_score.invoke({'context': context})
        needs_clarification = completeness_score < 0.6
        
        clarification_questions = []
        if needs_clarification:
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

@app.post("/generate-diagram", response_model=ReactFlowDiagramResponse)
async def generate_diagram(request: ArchitectureRequest):
    """Generate ReactFlow diagram based on description and type"""
    try:
        user_responses = request.clarification_responses or {}
        
        if request.diagram_type == "database":
            diagram_data = generate_reactflow_database.invoke({
                'description': request.description,
                'context': request.context,
                'user_responses': user_responses
            })
        else:
            diagram_data = generate_reactflow_architecture.invoke({
                'description': request.description, 
                'context': request.context,
                'user_responses': user_responses
            })
        
        return ReactFlowDiagramResponse(
            nodes=[ReactFlowNode(**node) for node in diagram_data["nodes"]],
            edges=[ReactFlowEdge(**edge) for edge in diagram_data["edges"]],
            metadata={
                "diagram_type": request.diagram_type,
                "domain": request.context.get("project_domain", "general system"),
                "timestamp": datetime.now().isoformat(),
                "description": request.description
            }
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error generating diagram: {str(e)}")

@app.post("/generate-architecture", response_model=ArchitectureResponse)
async def generate_architecture(request: ArchitectureRequest):
    """Generate detailed text architecture (legacy endpoint)"""
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