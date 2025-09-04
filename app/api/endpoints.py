
from fastapi import APIRouter, HTTPException, Depends, File, UploadFile, Form
from fastapi import Request
from typing import Dict, Optional
from datetime import datetime
import io
import PyPDF2


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