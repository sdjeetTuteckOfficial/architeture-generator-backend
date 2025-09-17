
from fastapi import APIRouter, HTTPException, Depends, File, UploadFile, Form
from fastapi import Request
from typing import Dict, Optional
from datetime import datetime
import io
import PyPDF2
from typing import List, Optional, Dict, Any
from app.core import models
from app.database import get_db, SessionLocal
from app.services.thread_services import create_thread, get_thread, get_threads, create_conversation, get_conversation, get_conversations
from uuid import UUID

from app.core import models
from app.services import analyzer, diagram_generator, text_generator
router = APIRouter()


# Initialize service classes
analyzer_service = analyzer.ArchitectureAnalyzer()
diagram_gen_service = diagram_generator.DiagramGenerator()
text_gen_service = text_generator.TextArchitectureGenerator()


@router.post("/analyze", response_model=models.AnalysisResponse)
async def analyze_project(request: Request):
    """Analyze project and determine if clarification is needed. Supports JSON and file uploads."""
    try:
        description = ""
        pdf_text = ""
        content_type = request.headers.get('content-type')

        if content_type and 'application/json' in content_type:
            data = await request.json()
            description = data.get("description", "")
        elif content_type and 'multipart/form-data' in content_type:
            form = await request.form()
            description = form.get("description", "")
            file = form.get("file")
            if file and isinstance(file, UploadFile) and file.filename and file.filename.lower().endswith(".pdf"):
                # Read PDF and extract text
                pdf_bytes = await file.read()
                pdf_stream = io.BytesIO(pdf_bytes)
                reader = PyPDF2.PdfReader(pdf_stream)
                for page in reader.pages:
                    pdf_text += page.extract_text() or ""
        else:
            raise HTTPException(status_code=415, detail="Unsupported Media Type. Use application/json or multipart/form-data.")

        # Combine description and PDF text
        combined_description = description or ""
        if pdf_text:
            combined_description += "\n\nPDF Content:\n" + pdf_text
        
        if not combined_description.strip():
             raise HTTPException(status_code=400, detail="No description or file provided.")

        context = analyzer_service.analyze_context(combined_description)
        completeness = analyzer_service.calculate_completeness(context, combined_description)
        needs_clarification = completeness < 0.6

        questions = []
        if needs_clarification:
            questions = analyzer_service.generate_questions(context, completeness)

        return models.AnalysisResponse(
            project_domain=context.get("project_domain", "software system"),
            completeness_score=completeness,
            needs_clarification=needs_clarification,
            clarification_questions=questions,
            extracted_context=context,
        )
    except HTTPException as e:
        raise e
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Analysis error: {str(e)}")

@router.post("/generate-diagram", response_model=models.DiagramResponse)
async def generate_diagram(request: models.ArchitectureRequest):
    """Generate ReactFlow diagram"""
    try:
        user_responses = request.clarification_responses or {}
        
        if request.diagram_type == "db_diagram":
            diagram_data = diagram_gen_service.generate_database_diagram(
                request.description, request.context, user_responses
            )
            nodes = [
                models.DBTableNode(
                    id=node_data["id"],
                    data=models.DBTableNodeData(
                        label=node_data["data"]["label"],
                        fields=[models.DBTableField(**f) for f in node_data["data"]["fields"]],
                    ),
                    position=node_data["position"],
                )
                for node_data in diagram_data["nodes"]
            ]
            edges = [models.DBEdge(**edge) for edge in diagram_data["edges"]]
        else:
            diagram_data = diagram_gen_service.generate_architecture_diagram(
                request.description, request.context, user_responses
            )
            nodes = [models.ReactFlowNode(**node) for node in diagram_data["nodes"]]
            edges = [models.ReactFlowEdge(**edge) for edge in diagram_data["edges"]]
        
        return models.DiagramResponse(
            nodes=nodes,
            edges=edges,
            metadata={
                "diagram_type": request.diagram_type,
                "domain": request.context.get("project_domain", "software system"),
                "timestamp": datetime.now().isoformat(),
                "node_count": len(diagram_data["nodes"]),
                "edge_count": len(diagram_data["edges"]),
            },
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Diagram generation error: {str(e)}")

@router.post("/generate-text-architecture", response_model=models.TextArchitectureResponse)
async def generate_text_architecture(request: models.ArchitectureRequest):
    """Generate detailed text architecture document"""
    try:
        user_responses = request.clarification_responses or {}
        result = text_gen_service.generate_detailed_architecture(
            request.description, request.context, user_responses
        )
        
        return models.TextArchitectureResponse(
            architecture=result["architecture"],
            domain=request.context.get("project_domain", "software system"),
            recommendations=result["recommendations"],
            timestamp=datetime.now().isoformat(),
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Text architecture error: {str(e)}")
    
@router.post("/threads", response_model=models.ThreadResponse, status_code=201)
def create_new_thread(thread_data: models.ThreadCreate, db: SessionLocal = Depends(get_db)):
    """Creates a new conversation thread."""
    return create_thread(db=db, thread_data=thread_data)

@router.get("/threads/{thread_id}", response_model=models.ThreadResponse)
def read_thread(thread_id: UUID, db: SessionLocal = Depends(get_db)):
    """Retrieves a specific conversation thread by its ID."""
    thread = get_thread(db=db, thread_id=thread_id)
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")
    return thread

@router.get("/threads", response_model=List[models.ThreadResponse])
def read_threads(user_id: UUID, skip: int = 0, limit: int = 100, db: SessionLocal = Depends(get_db)):
    """Retrieves all conversation threads for a specific user."""
    threads = get_threads(db=db, user_id=user_id, skip=skip, limit=limit)
    return threads

@router.post("/threads/{thread_id}/conversations", response_model=models.ConversationResponse, status_code=201)
def create_new_conversation(thread_id: UUID, conversation_data: models.ConversationCreate, db: SessionLocal = Depends(get_db)):
    """Adds a new conversation entry to a specific thread."""
    thread = get_thread(db=db, thread_id=thread_id)
    if not thread:
        raise HTTPException(status_code=404, detail="Thread not found")
    
    return create_conversation(db=db, thread_id=thread_id, conversation_data=conversation_data)

@router.get("/conversations/{conversation_id}", response_model=models.ConversationResponse)
def read_conversation(conversation_id: UUID, db: SessionLocal = Depends(get_db)):
    """Retrieves a specific conversation entry by its ID."""
    conversation = get_conversation(db=db, conversation_id=conversation_id)
    if not conversation:
        raise HTTPException(status_code=404, detail="Conversation not found")
    return conversation

@router.get("/threads/{thread_id}/conversations", response_model=List[models.ConversationResponse])
def read_conversations_in_thread(thread_id: UUID, skip: int = 0, limit: int = 100, db: SessionLocal = Depends(get_db)):
    """Retrieves all conversations within a specific thread."""
    conversations = get_conversations(db=db, thread_id=thread_id, skip=skip, limit=limit)
    return conversations
