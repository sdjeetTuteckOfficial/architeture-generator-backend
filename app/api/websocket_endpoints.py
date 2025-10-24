# app/api/websocket_endpoints.py
from fastapi import APIRouter, WebSocket, WebSocketDisconnect, Depends
from typing import Dict, List
import json
from datetime import datetime
from uuid import UUID
import logging
import json

from app.database import get_db, SessionLocal
from app.services import analyzer, diagram_generator
from app.services.thread_services import (
    create_thread, get_thread, create_conversation, 
    get_conversations
)
from app.api.dependencies import get_current_user_from_websocket
from app.core import models

logger = logging.getLogger(__name__)
router = APIRouter()

# Service instances
analyzer_service = analyzer.ArchitectureAnalyzer()
diagram_gen_service = diagram_generator.DiagramGenerator()


class ConnectionManager:
    """Manages WebSocket connections"""
    
    def __init__(self):
        self.active_connections: Dict[str, WebSocket] = {}
    
    async def connect(self, websocket: WebSocket, client_id: str):
        await websocket.accept()
        self.active_connections[client_id] = websocket
        logger.info(f"Client {client_id} connected")
    
    def disconnect(self, client_id: str):
        if client_id in self.active_connections:
            del self.active_connections[client_id]
            logger.info(f"Client {client_id} disconnected")
    
    async def send_message(self, client_id: str, message: dict):
        if client_id in self.active_connections:
            await self.active_connections[client_id].send_json(message)


manager = ConnectionManager()


async def load_conversation_memory(db: SessionLocal, thread_id: UUID, limit: int = 10) -> List[Dict]:
    """Load previous conversations for context"""
    conversations = get_conversations(db=db, thread_id=thread_id, skip=0, limit=limit)
    
    memory = []
    for conv in conversations:
        memory.append({
            "version": conv.version,
            "diagram_json": conv.diagram_json,
            "created_at": conv.created_at.isoformat(),
            "conversation_id": str(conv.conversation_id)
        })
    
    return sorted(memory, key=lambda x: x["version"])


async def build_context_from_memory(memory: List[Dict]) -> Dict:
    """Build enriched context from conversation history"""
    if not memory:
        return {}
    
    all_nodes = []
    all_edges = []
    technologies = set()
    
    for conv in memory:
        diagram = conv.get("diagram_json", {})
        if isinstance(diagram, dict):
            nodes = diagram.get("nodes", [])
            edges = diagram.get("edges", [])
            
            all_nodes.extend(nodes)
            all_edges.extend(edges)
            
            for node in nodes:
                if isinstance(node, dict):
                    label = node.get("data", {}).get("label", "")
                    technologies.add(label)
    
    return {
        "previous_versions": len(memory),
        "total_components": len(all_nodes),
        "total_connections": len(all_edges),
        "technologies_used": list(technologies),
        "evolution_history": [
            {
                "version": conv["version"],
                "component_count": len(conv.get("diagram_json", {}).get("nodes", [])),
                "created_at": conv["created_at"]
            }
            for conv in memory
        ]
    }


@router.websocket("/ws/architecture/{client_id}")
async def websocket_architecture_endpoint(
    websocket: WebSocket,
    client_id: str,
    db: SessionLocal = Depends(get_db)
):
    """WebSocket endpoint for real-time architecture diagram generation with memory"""
    
    await manager.connect(websocket, client_id)
    
    # Session state
    current_user = None
    current_thread_id = None
    current_version = 0
    current_analysis = None
    clarification_responses = {}
    awaiting_clarification = False
    conversation_memory = []
    
    try:
        await manager.send_message(client_id, {
            "type": "connected",
            "message": "✨ WebSocket connected! I'm your AI architect with memory.",
            "timestamp": datetime.now().isoformat()
        })
        
        while True:
            data = await websocket.receive_json()
            message_type = data.get("type")
            
            # Handle authentication
            if message_type == "auth":
                token = data.get("token")
                if not token:
                    await manager.send_message(client_id, {
                        "type": "error",
                        "message": "Authentication token required"
                    })
                    continue
                
                current_user = await get_current_user_from_websocket(token, db)
                if not current_user:
                    await manager.send_message(client_id, {
                        "type": "error",
                        "message": "Invalid authentication token"
                    })
                    continue
                
                await manager.send_message(client_id, {
                    "type": "authenticated",
                    "user_id": str(current_user.id),
                    "message": f"🔐 Authenticated as {current_user.email}"
                })
            
            # Handle thread creation
            elif message_type == "create_thread":
                if not current_user:
                    await manager.send_message(client_id, {
                        "type": "error",
                        "message": "Please authenticate first"
                    })
                    continue
                
                thread_name = data.get("thread_name", f"Architecture Chat {datetime.now().strftime('%Y-%m-%d %H:%M')}")
                
                thread_data = models.ThreadCreate(
                    user_id=current_user.id,
                    thread_name=thread_name
                )
                
                thread = create_thread(db=db, thread_data=thread_data)
                current_thread_id = thread.thread_id
                current_version = 0
                conversation_memory = []
                
                await manager.send_message(client_id, {
                    "type": "thread_created",
                    "thread_id": str(current_thread_id),
                    "thread_name": thread_name,
                    "message": f"📝 New thread created: {thread_name}"
                })
            
            # Handle thread loading
            elif message_type == "load_thread":
                if not current_user:
                    await manager.send_message(client_id, {
                        "type": "error",
                        "message": "Please authenticate first"
                    })
                    continue
                
                thread_id = UUID(data.get("thread_id"))
                thread = get_thread(db=db, thread_id=thread_id)
                
                if not thread or thread.user_id != current_user.id:
                    await manager.send_message(client_id, {
                        "type": "error",
                        "message": "Thread not found or access denied"
                    })
                    continue
                
                conversation_memory = await load_conversation_memory(db, thread_id, limit=20)
                memory_context = await build_context_from_memory(conversation_memory)
                
                current_thread_id = thread_id
                current_version = len(conversation_memory)
                
                await manager.send_message(client_id, {
                    "type": "thread_loaded",
                    "thread_id": str(thread_id),
                    "thread_name": thread.thread_name,
                    "version": current_version,
                    "memory_context": memory_context,
                    "conversations": conversation_memory,
                    "message": f"🔄 Loaded thread with {len(conversation_memory)} previous versions"
                })
            
            # Handle analysis request
            elif message_type == "analyze":
                if not current_user:
                    await manager.send_message(client_id, {
                        "type": "error",
                        "message": "Please authenticate first"
                    })
                    continue
                
                description = data.get("description", "")
                diagram_type = data.get("diagram_type", "architecture")
                
                await manager.send_message(client_id, {
                    "type": "processing",
                    "message": "🔍 Analyzing your project..."
                })
                
                # Build context with memory
                memory_context = await build_context_from_memory(conversation_memory)
                enhanced_description = description
                
                if memory_context:
                    enhanced_description = f"""
Current Request: {description}

Previous Context:
- Total versions: {memory_context.get('previous_versions', 0)}
- Technologies used: {', '.join(memory_context.get('technologies_used', [])[:10])}
- Previous components: {memory_context.get('total_components', 0)}

Please consider the evolution history and build upon previous designs.
"""
                
                context = analyzer_service.analyze_context(enhanced_description)
                context["memory_context"] = memory_context
                
                completeness = analyzer_service.calculate_completeness(context, enhanced_description)
                needs_clarification = completeness < 0.6
                
                current_analysis = {
                    "original_description": description,
                    "extracted_context": context,
                    "completeness_score": completeness,
                    "needs_clarification": needs_clarification,
                    "diagram_type": diagram_type
                }
                
                if needs_clarification:
                    questions = analyzer_service.generate_questions(context, completeness)
                    current_analysis["clarification_questions"] = questions
                    awaiting_clarification = True
                    clarification_responses = {}
                    
                    await manager.send_message(client_id, {
                        "type": "clarification_needed",
                        "analysis": current_analysis,
                        "questions": questions,
                        "message": f"🎯 I need some clarifications (Completeness: {int(completeness*100)}%)"
                    })
                else:
                    await manager.send_message(client_id, {
                        "type": "generating",
                        "message": "🎨 Generating your diagram..."
                    })
                    
                    if diagram_type == "db_diagram":
                        diagram_data = diagram_gen_service.generate_database_diagram(
                            description, context, {}
                        )
                    else:
                        diagram_data = diagram_gen_service.generate_architecture_diagram(
                            description, context, {}
                        )
                    
                    if current_thread_id:
                        conversation_data = models.ConversationCreate(
                            version=current_version,
                            diagram_json=diagram_data
                        )
                        conversation = create_conversation(
                            db=db,
                            thread_id=current_thread_id,
                            conversation_data=conversation_data
                        )
                        current_version += 1
                        
                        conversation_memory.append({
                            "version": conversation.version,
                            "diagram_json": diagram_data,
                            "created_at": conversation.created_at.isoformat(),
                            "conversation_id": str(conversation.conversation_id)
                        })
                    
                    await manager.send_message(client_id, {
                        "type": "diagram_generated",
                        "diagram": diagram_data,
                        "version": current_version - 1,
                        "metadata": {
                            "node_count": len(diagram_data.get("nodes", [])),
                            "edge_count": len(diagram_data.get("edges", [])),
                            "diagram_type": diagram_type
                        },
                        "message": f"✅ Diagram generated! Version {current_version - 1}"
                    })
            
            # Handle clarification response
            elif message_type == "clarification_response":
                if not awaiting_clarification or not current_analysis:
                    await manager.send_message(client_id, {
                        "type": "error",
                        "message": "No clarification pending"
                    })
                    continue
                
                response = data.get("response", "")
                question_index = len(clarification_responses)
                clarification_responses[f"question_{question_index}"] = response
                
                questions = current_analysis.get("clarification_questions", [])
                
                if len(clarification_responses) >= len(questions):
                    awaiting_clarification = False
                    
                    await manager.send_message(client_id, {
                        "type": "generating",
                        "message": "🎨 All clarifications received! Generating..."
                    })
                    
                    diagram_type = current_analysis.get("diagram_type", "architecture")
                    
                    if diagram_type == "db_diagram":
                        diagram_data = diagram_gen_service.generate_database_diagram(
                            current_analysis["original_description"],
                            current_analysis["extracted_context"],
                            clarification_responses
                        )
                    else:
                        diagram_data = diagram_gen_service.generate_architecture_diagram(
                            current_analysis["original_description"],
                            current_analysis["extracted_context"],
                            clarification_responses
                        )
                    
                    if current_thread_id:
                        conversation_data = models.ConversationCreate(
                            version=current_version,
                            diagram_json=diagram_data
                        )
                        conversation = create_conversation(
                            db=db,
                            thread_id=current_thread_id,
                            conversation_data=conversation_data
                        )
                        current_version += 1
                        
                        conversation_memory.append({
                            "version": conversation.version,
                            "diagram_json": diagram_data,
                            "created_at": conversation.created_at.isoformat(),
                            "conversation_id": str(conversation.conversation_id)
                        })
                    
                    await manager.send_message(client_id, {
                        "type": "diagram_generated",
                        "diagram": diagram_data,
                        "version": current_version - 1,
                        "metadata": {
                            "node_count": len(diagram_data.get("nodes", [])),
                            "edge_count": len(diagram_data.get("edges", [])),
                            "diagram_type": diagram_type
                        },
                        "message": f"✅ Diagram generated! Version {current_version - 1}"
                    })
                else:
                    next_question = questions[len(clarification_responses)]
                    await manager.send_message(client_id, {
                        "type": "next_question",
                        "question": next_question,
                        "progress": {
                            "current": len(clarification_responses) + 1,
                            "total": len(questions)
                        },
                        "message": f"💡 Question {len(clarification_responses) + 1}/{len(questions)}"
                    })
            
            elif message_type == "ping":
                await manager.send_message(client_id, {
                    "type": "pong",
                    "timestamp": datetime.now().isoformat()
                })
    
    except WebSocketDisconnect:
        manager.disconnect(client_id)
        logger.info(f"Client {client_id} disconnected")
    
    except Exception as e:
        logger.error(f"WebSocket error for client {client_id}: {str(e)}")
        try:
            await manager.send_message(client_id, {
                "type": "error",
                "message": f"Server error: {str(e)}"
            })
        except:
            pass
        manager.disconnect(client_id)